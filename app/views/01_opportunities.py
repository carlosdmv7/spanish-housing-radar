"""
Deals — which flats are cheap for their area.

Built to be read at a glance: a row of controls, four numbers, one colour band
that is both the tier legend and the distribution, then a ranked table where the
tier is a coloured label and the score a bar. Pick a row and its card shows the
arithmetic. Everything the old page said in paragraphs is either in a tooltip,
in the card for the one listing you are looking at, or on How it works.

ADR-0005 still holds on every row: the "Compared with" column says which grain
scored it, so a score never appears without the benchmark behind it.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from chrome import page_header
from components.charts import (
    bar_flat_vs_area,
    scatter_size_vs_price,
    strip_deal_tiers,
    tier_legend,
)
from components.filters import load_municipalities
from components.map_view import listings_map
from components.provenance import GRAIN_WORDING, confidence_note
from config import DEAL_TIER_COLORS, DEAL_TIER_LABELS, PROPERTY_TYPE_LABELS
from connection import query
import pandas as pd
import streamlit as st
from theme import TEAL_700, altair_chart

page_header(
    "Which flats are cheap for their area?",
    "Every listing scored 0–100 against comparable flats nearby.",
)

try:
    munis = load_municipalities()
except Exception as exc:
    st.error(
        "**Can't reach the warehouse.** Locally that needs `MOTHERDUCK_TOKEN` in "
        "`.env`; on Streamlit Cloud it comes from the app's Secrets."
    )
    st.caption(f"Underlying error: {exc}")
    st.stop()

# ── Controls, inline ──────────────────────────────────────────────────────────
MAX_PRICE = {
    "sale": [None, 200_000, 300_000, 400_000, 600_000, 1_000_000],
    "rent": [None, 1_000, 1_500, 2_000, 3_000],
}
c_op, c_city, c_type, c_price, c_more = st.columns([1.2, 1.4, 1.4, 1.4, 1],
                                                   vertical_alignment="bottom")
with c_op:
    op = st.segmented_control(
        "Looking to", ["sale", "rent"], default="sale", required=True,
        format_func=lambda k: {"sale": "Buy", "rent": "Rent"}[k],
    )
with c_city:
    cities = sorted(munis)
    muni = st.selectbox(
        "City", cities,
        index=cities.index("valència") if "valència" in cities else 0,
        format_func=str.title,
    )
with c_type:
    prop = st.selectbox(
        "Type", ["all", *PROPERTY_TYPE_LABELS],
        format_func=lambda k: "Any" if k == "all" else PROPERTY_TYPE_LABELS[k],
    )
with c_price:
    per = "/mo" if op == "rent" else ""
    max_price = st.selectbox(
        "Max price", MAX_PRICE[op],
        format_func=lambda v: "Any" if v is None else f"€{v:,.0f}{per}",
    )
with c_more, st.popover("More filters", width="stretch"):
    min_score = st.slider("Minimum score", 0, 100, 0, step=5)
    own_barrio_only = st.toggle(
        "Only scored against their own barrio",
        help="The strongest comparison. Off by default so nothing is hidden.",
    )
    motivated_only = st.toggle(
        "Only motivated sellers",
        help="Long on the market, or the price has already been cut.",
    )

# ── Data ──────────────────────────────────────────────────────────────────────
SQL = (Path(__file__).parent.parent / "queries" / "opportunities.sql").read_text()


@st.cache_data(ttl=600, show_spinner="Loading listings…")
def load(op: str, prop: str, muni: str) -> pd.DataFrame:
    return query(SQL, operation_type=op, property_type=prop, municipality=muni,
                 min_price=0, max_price=10**12)


try:
    everything = load(op, prop, muni)
except Exception as exc:
    st.error("**The listings query failed.**")
    st.caption(f"Underlying error: {exc}")
    st.stop()

df = everything
if max_price is not None:
    df = df[df["price_eur"] <= max_price]
df = df[df["opportunity_score"] >= min_score]
if own_barrio_only:
    df = df[df["benchmark_level"] == "neighbourhood"]
if motivated_only:
    df = df[df["seller_motivation"].isin(["medium", "high"])]

if everything.empty:
    st.info(f"No {'rentals' if op == 'rent' else 'listings'} for this city and type yet.")
    st.stop()
if df.empty:
    st.warning(f"{len(everything):,} listings match, but none pass your filters.")
    st.stop()

# ── Four numbers ──────────────────────────────────────────────────────────────
m1, m2, m3, m4 = st.columns(4)
m1.metric("Listings", f"{len(df):,}")
m2.metric("Great deals", f"{int((df['deal_tier'] == 'great_deal').sum()):,}",
          help="Score 75+: well below what comparable flats ask.")
m3.metric("Typical price", f"€{df['price_per_sqm'].median():,.0f}/m²"
          + ("/mo" if op == "rent" else ""))
m4.metric("Compared with their own barrio",
          f"{(df['benchmark_level'] == 'neighbourhood').mean():.0%}",
          help="The rest are compared with their district or the whole city, "
               "because their barrio has too few listings to be a fair yardstick.")

altair_chart(strip_deal_tiers(df))
st.markdown(f":small[{tier_legend(df)}]")

# ── Ranked / map / size ───────────────────────────────────────────────────────
tab_rank, tab_map, tab_size = st.tabs(
    [":material/format_list_numbered: Ranked", ":material/map: Map",
     ":material/scatter_plot: Size vs price"]
)

with tab_rank:
    tiers = list(DEAL_TIER_LABELS.values())
    table = df.reset_index(drop=True).assign(
        area=lambda d: (d["neighborhood"].fillna(d["district"])
                        .fillna(d["municipality"]).str.title()),
        # A one-item list, because MultiselectColumn is the one native column that
        # renders a value as a coloured label — which is the whole point here.
        tier=lambda d: d["deal_tier"].map(DEAL_TIER_LABELS).map(lambda t: [t]),
        vs_area=lambda d: (d["price_per_sqm"] / d["neighborhood_median_ppsqm"] - 1) * 100,
        compared=lambda d: d["benchmark_level"].map(
            {"neighbourhood": "Barrio", "district": "District", "city": "City"}),
    )
    left, right = st.columns([3, 2], gap="large")
    with left:
        event = st.dataframe(
            table[["area", "tier", "opportunity_score", "vs_area", "price_eur",
                   "size_sqm", "compared", "url"]],
            hide_index=True,
            height=520,
            on_select="rerun",
            selection_mode="single-row",
            selection_default={"selection": {"rows": [0], "columns": []}},
            key=f"deals-{op}-{muni}-{prop}",
            column_config={
                "area": st.column_config.TextColumn("Barrio", pinned=True, width="medium"),
                "tier": st.column_config.MultiselectColumn(
                    "Verdict", options=tiers,
                    color=[DEAL_TIER_COLORS[k] for k in DEAL_TIER_LABELS],
                ),
                "opportunity_score": st.column_config.ProgressColumn(
                    "Score", min_value=0, max_value=100, format="%d", color=TEAL_700,
                    help="50 = exactly the price of comparable flats. Higher is cheaper.",
                ),
                "vs_area": st.column_config.NumberColumn(
                    "vs area", format="%+.0f%%",
                    help="Price per m² against the flats it was compared with."),
                "price_eur": st.column_config.NumberColumn(
                    "Price", format=f"€%,d{per}"),
                "size_sqm": st.column_config.NumberColumn("m²", format="%d"),
                "compared": st.column_config.TextColumn(
                    "Scored vs", width="small",
                    help="What the flat was compared with: the finest area with at "
                         "least 8 comparable flats — its barrio, its district or the "
                         "whole city."),
                "url": st.column_config.LinkColumn("", display_text="open ↗"),
            },
        )
        st.caption("Pick a row to see why it scored what it did.")

    rows = event.selection.rows if event and event.selection else []
    pick = table.iloc[rows[0] if rows else 0]

    with right, st.container(border=True):
        tier_key = str(pick["deal_tier"])
        badge_color = {"great_deal": "green", "good_deal": "green", "fair": "orange",
                       "overpriced": "red", "very_overpriced": "red"}.get(tier_key, "gray")
        st.badge(DEAL_TIER_LABELS.get(tier_key, tier_key), color=badge_color)
        beds = f"{int(pick['rooms'])} bed · " if pd.notna(pick["rooms"]) else ""
        st.markdown(f"### €{pick['price_eur']:,.0f}{per}")
        st.markdown(f"{beds}{pick['size_sqm']:.0f} m² · **{pick['area']}**")

        k1, k2 = st.columns(2)
        k1.metric("Score", f"{pick['opportunity_score']:.0f}/100")
        k2.metric("vs area", f"{pick['vs_area']:+.0f}%")

        bench_label = GRAIN_WORDING.get(str(pick["benchmark_level"]),
                                        ("", "Benchmark"))[1]
        if pd.notna(pick["neighborhood_median_ppsqm"]):
            altair_chart(bar_flat_vs_area(float(pick["price_per_sqm"]),
                                          float(pick["neighborhood_median_ppsqm"]),
                                          bench_label))
        st.caption(f"€/m² · compared with {int(pick['benchmark_comp_count'] or 0)} "
                   "comparable flats.")

        note = confidence_note(pick.to_dict())
        if note:
            st.caption(note)
        if pick.get("seller_motivation") in ("medium", "high"):
            cut = pick.get("price_change_pct")
            st.caption(
                ":material/trending_down: Price already cut "
                f"{abs(cut):.0f}%" if pd.notna(cut) and cut < 0
                else ":material/schedule: Long on the market"
            )
        st.link_button("Open the listing", str(pick["url"]),
                       icon=":material/open_in_new:", width="stretch")

with tab_map:
    listings_map(df)

with tab_size:
    altair_chart(scatter_size_vs_price(df))
    st.caption("Each dot is a listing. Cheap for its size sits below the cloud.")
