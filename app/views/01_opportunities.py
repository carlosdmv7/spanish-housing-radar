"""
Opportunities — listings ranked by opportunity score, with filters, map and cards.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from components.charts import scatter_size_vs_price
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
from styles import page_hero, section

page_hero(
    "🔍",
    "Opportunities",
    "Every listing is scored 0–100 against comparable flats — its neighbourhood "
    "if there are enough, otherwise its district or city. Higher = better deal.",
)


# ── Filters ───────────────────────────────────────────────────────────────────
@st.cache_data(ttl=3600)
def load_municipalities() -> list[str]:
    df = query("SELECT DISTINCT municipality FROM spanish_housing_radar.main_silver.int_listings_current ORDER BY 1")
    return df["municipality"].tolist()


munis = load_municipalities()

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
        help="Hides listings whose neighbourhood has too few comparable flats for a reliable score.",
    )

# ── Load data ─────────────────────────────────────────────────────────────────
sql = (Path(__file__).parent.parent / "queries" / "opportunities.sql").read_text()


@st.cache_data(ttl=600, show_spinner="Loading listings…")
def load_opportunities(op, prop, muni, min_p, max_p):
    return query(sql, operation_type=op, property_type=prop,
                 municipality=muni, min_price=min_p, max_price=max_p)


df = load_opportunities(op, prop, muni, min_p, max_p)
df = df[df["opportunity_score"] >= min_score]
if hide_low_conf:
    df = df[~df["low_confidence_flag"].astype(bool)]

if df.empty:
    st.warning("No results match the current filters. Try widening the price range or score.")
    st.stop()

# ── Summary metrics ───────────────────────────────────────────────────────────
unit = "€" if op == "sale" else "€/mo"
great = int((df["deal_tier"] == "great_deal").sum())
c1, c2, c3, c4 = st.columns(4)
c1.metric("Listings", f"{len(df):,}")
c2.metric("Median price", f"{df['price_eur'].median():,.0f} {unit}")
c3.metric("Median €/sqm", f"€{df['price_per_sqm'].median():,.0f}")
c4.metric("🟢 Great deals", great, help="Listings scoring ≥ 75 — clearly below the area median.")

st.markdown("")
tab_list, tab_explore, tab_map = st.tabs(["🏷️ Best deals", "📈 Explore", "🗺️ Map"])

# ── Best deals: cards + table ─────────────────────────────────────────────────
with tab_list:
    section("Deal tier breakdown")
    tier_order = list(DEAL_TIER_LABELS.keys())
    tier_counts = (
        df["deal_tier"].value_counts()
        .reindex(tier_order).fillna(0).astype(int)
        .rename(index=DEAL_TIER_LABELS)
    )
    st.bar_chart(tier_counts, horizontal=True, color="#3b82f6")

    section(f"Top listings · {len(df):,} results sorted by score")
    view_cards, view_table = st.tabs(["🃏 Cards", "📋 Table"])
    with view_cards:
        for _, row in df.head(24).iterrows():
            listing_card(row.to_dict())
    with view_table:
        cols = [
            "neighborhood", "district", "price_eur", "size_sqm", "rooms",
            "price_per_sqm", "neighborhood_median_ppsqm", "ppsqm_vs_median",
            "opportunity_score", "deal_tier", "benchmark_level", "low_confidence_flag",
        ]
        st.dataframe(
            df[cols].rename(columns={
                "neighborhood": "Neighbourhood",
                "district": "District",
                "price_eur": "Price (€)",
                "size_sqm": "sqm",
                "rooms": "Beds",
                "price_per_sqm": "€/sqm",
                "neighborhood_median_ppsqm": "Benchmark €/sqm",
                "ppsqm_vs_median": "Δ vs benchmark",
                "opportunity_score": "Score",
                "deal_tier": "Tier",
                "benchmark_level": "Scored vs",
                "low_confidence_flag": "⚠️ Low data",
            }),
            use_container_width=True,
            hide_index=True,
            column_config={
                "Score": st.column_config.ProgressColumn(
                    "Score", min_value=0, max_value=100, format="%d"
                ),
            },
        )

# ── Explore: scatter ──────────────────────────────────────────────────────────
with tab_explore:
    section("Size vs price")
    st.caption("Each dot is a listing, coloured by deal tier. Cheap-for-their-size flats sit below the cloud.")
    st.plotly_chart(scatter_size_vs_price(df), use_container_width=True)

# ── Map ───────────────────────────────────────────────────────────────────────
with tab_map:
    section("Geographic view")
    listings_map(df)
