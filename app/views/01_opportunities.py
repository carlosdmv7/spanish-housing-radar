"""
Opportunities — listings ranked by opportunity score, with filters, map and cards.

The page is built so the *first* screen is already the answer: it loads with
Valencia sale listings at full price range and shows the top ten straight away.
A visitor who touches no filter still sees the product work.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from components.charts import bar_deal_tiers, scatter_size_vs_price
from components.filters import (
    municipality_filter,
    operation_filter,
    price_range_filter,
    property_type_filter,
)
from components.listing_card import listing_card
from components.map_view import listings_map
from config import DEAL_TIER_LABELS
from connection import query
import streamlit as st
from theme import altair_chart, page_hero, section

TOP_N_DEFAULT = 10

page_hero(
    "Opportunities",
    "Every listing is scored 0–100 against comparable flats — its own barrio when "
    "there are enough, otherwise its district or city. Higher means better deal.",
)


@st.cache_data(ttl=3600)
def load_municipalities() -> list[str]:
    df = query(
        "SELECT DISTINCT municipality "
        "FROM spanish_housing_radar.main_silver.int_listings_current ORDER BY 1"
    )
    return df["municipality"].tolist()


try:
    munis = load_municipalities()
except Exception as exc:
    st.error(
        "**Can't reach the warehouse, so there is nothing to rank.** The app reads "
        "from MotherDuck; if you're running it locally, check that `MOTHERDUCK_TOKEN` "
        "is set in `.env`. On Streamlit Cloud it comes from the app's Secrets."
    )
    st.caption(f"Underlying error: {exc}")
    st.stop()

# ── Filters ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Filters")
    op = operation_filter()
    muni = municipality_filter(munis)
    prop = property_type_filter()
    min_p, max_p = price_range_filter(
        min_val=0,
        max_val=2_000_000 if op == "sale" else 5_000,
        step=10_000 if op == "sale" else 100,
        label="Price (€)" if op == "sale" else "Monthly rent (€)",
    )
    min_score = st.slider("Min opportunity score", 0, 100, 0)
    hide_low_conf = st.toggle(
        "Hide low-confidence scores",
        value=False,
        help="Hides listings whose benchmark had too few comparable flats. Off by "
             "default: a weak score is still a fact about the market (ADR-0005).",
    )
    motivated_only = st.toggle(
        "Only motivated sellers",
        value=False,
        help="Keeps listings long on the market or with price cuts — a stronger "
             "signal of a negotiable deal. Fills in as snapshot history accumulates.",
    )

# ── Load data ─────────────────────────────────────────────────────────────────
sql = (Path(__file__).parent.parent / "queries" / "opportunities.sql").read_text()


@st.cache_data(ttl=600, show_spinner="Loading listings…")
def load_opportunities(op, prop, muni, min_p, max_p):
    return query(sql, operation_type=op, property_type=prop,
                 municipality=muni, min_price=min_p, max_price=max_p)


try:
    unfiltered = load_opportunities(op, prop, muni, min_p, max_p)
except Exception as exc:
    st.error(
        "**The listings query failed.** The gold model `rpt_opportunities` may not "
        "have been built yet — run `make transform` to populate it."
    )
    st.caption(f"Underlying error: {exc}")
    st.stop()

if unfiltered.empty:
    st.info(
        f"**No {'listings' if op == 'sale' else 'rentals'} scraped for this city and "
        "property type yet.** Coverage is deepest in **Valencia** for **sale** — pick "
        "those in the sidebar, or choose *All cities* to see everything in the warehouse."
    )
    st.stop()

df = unfiltered[unfiltered["opportunity_score"] >= min_score]
if hide_low_conf:
    df = df[~df["low_confidence_flag"].astype(bool)]
if motivated_only:
    df = df[df["seller_motivation"].isin(["medium", "high"])]

if df.empty:
    # The data exists — the filters excluded it. Say which one is most likely, so
    # the visitor has something to undo rather than a dead end.
    culprits = []
    if min_score > 0:
        culprits.append(f"minimum score of **{min_score}**")
    if hide_low_conf:
        culprits.append("**hide low-confidence** toggle")
    if motivated_only:
        culprits.append("**motivated sellers only** toggle")
    reason = " or the ".join(culprits) if culprits else "**price range**"
    st.warning(
        f"**{len(unfiltered):,} listings match this city and type, but none survive "
        f"your filters.** Try relaxing the {reason}."
    )
    st.stop()

# ── Summary metrics ───────────────────────────────────────────────────────────
unit = "€" if op == "sale" else "€/mo"
great = int((df["deal_tier"] == "great_deal").sum())
motivated = int(df["seller_motivation"].isin(["medium", "high"]).sum())
barrio_grain = float((df["benchmark_level"] == "neighbourhood").mean() * 100)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Listings", f"{len(df):,}")
c2.metric("Median price", f"{df['price_eur'].median():,.0f} {unit}")
c3.metric("Median €/m²", f"€{df['price_per_sqm'].median():,.0f}")
c4.metric("Great deals", great, help="Listings scoring ≥ 75 — clearly below their benchmark.")
st.markdown(
    f":small[**{barrio_grain:.0f}%** of these scores were computed at barrio grain; "
    f"the rest fall back to district or city. **{motivated:,}** show a motivated-seller "
    "signal (long on market or price cuts).]"
)

st.markdown("")
tab_list, tab_explore, tab_map = st.tabs(["Best deals", "Explore", "Map"])

# ── Best deals ────────────────────────────────────────────────────────────────
with tab_list:
    section(f"Top {TOP_N_DEFAULT} right now")
    st.markdown(
        ":small[Sorted by opportunity score. Every card shows the benchmark it was "
        "scored against and how many comparables backed it.]"
    )
    for _, row in df.head(TOP_N_DEFAULT).iterrows():
        listing_card(row.to_dict())

    section("Deal tier breakdown")
    altair_chart(bar_deal_tiers(df))

    section(f"All {len(df):,} results")
    table = df.assign(
        tier=df["deal_tier"].map(DEAL_TIER_LABELS).fillna(df["deal_tier"]),
        area=df["neighborhood"].str.title(),
        district_name=df["district"].str.title(),
        delta_pct=(df["ppsqm_vs_median"] / df["neighborhood_median_ppsqm"] * 100),
    )[[
        "area", "district_name", "price_eur", "size_sqm", "rooms",
        "price_per_sqm", "neighborhood_median_ppsqm", "delta_pct",
        "opportunity_score", "tier", "benchmark_level", "benchmark_comp_count",
        "low_confidence_flag", "days_on_market", "n_price_changes", "url",
    ]]
    st.dataframe(
        table,
        width="stretch",
        hide_index=True,
        column_config={
            "area": st.column_config.TextColumn("Barrio", pinned=True),
            "district_name": st.column_config.TextColumn("District"),
            "price_eur": st.column_config.NumberColumn(
                "Price", format="€%,d",
                help="Asking price, not a transaction price.",
            ),
            "size_sqm": st.column_config.NumberColumn("Size", format="%.0f m²"),
            "rooms": st.column_config.NumberColumn("Beds", format="%.0f"),
            "price_per_sqm": st.column_config.NumberColumn("€/m²", format="€%,d"),
            "neighborhood_median_ppsqm": st.column_config.NumberColumn(
                "Benchmark €/m²", format="€%,d",
                help="Median €/m² of the comparables this listing was scored against.",
            ),
            "delta_pct": st.column_config.NumberColumn(
                "Δ vs benchmark", format="%+.1f%%",
                help="Negative means cheaper per m² than its comparables.",
            ),
            "opportunity_score": st.column_config.ProgressColumn(
                "Score", min_value=0, max_value=100, format="%.0f",
                help="0–100. 50 sits exactly at the benchmark median.",
            ),
            "tier": st.column_config.TextColumn("Tier"),
            "benchmark_level": st.column_config.TextColumn(
                "Scored vs",
                help="Grain of the comparison: barrio, district or city. "
                     "Coarser means less local, so less confident.",
            ),
            "benchmark_comp_count": st.column_config.NumberColumn(
                "Comparables", format="%.0f",
                help="How many listings formed the benchmark. Below 8 at city "
                     "grain is flagged low-confidence.",
            ),
            "low_confidence_flag": st.column_config.CheckboxColumn(
                "Low confidence", help="Thin city-wide benchmark — read the score as a hint.",
            ),
            "days_on_market": st.column_config.NumberColumn("Days listed", format="%.0f"),
            "n_price_changes": st.column_config.NumberColumn("Price cuts", format="%.0f"),
            "url": st.column_config.LinkColumn("Listing", display_text="Open ↗"),
        },
    )

# ── Explore ───────────────────────────────────────────────────────────────────
with tab_explore:
    section("Size vs price")
    st.markdown(
        ":small[Each dot is a listing, coloured by deal tier. Flats that are cheap "
        "for their size sit below the cloud. Drag to pan, scroll to zoom.]"
    )
    altair_chart(scatter_size_vs_price(df))

# ── Map ───────────────────────────────────────────────────────────────────────
with tab_map:
    section("Geographic view")
    listings_map(df)
