"""
Page 1 — Search & Opportunities
Listings ranked by opportunity score with filters and map.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st

from components.charts import scatter_size_vs_price
from components.filters import (
    municipality_filter,
    operation_filter,
    price_range_filter,
    property_type_filter,
)
from components.listing_card import listing_card
from components.map_view import listings_map
from config import DEAL_TIER_LABELS, PAGE_ICON
from connection import query

st.set_page_config(page_title="Opportunities · SHR", page_icon=PAGE_ICON, layout="wide")
st.title("🔍 Opportunities")
st.caption("Listings ranked by opportunity score — higher score means cheaper relative to the neighborhood.")

# ── Load municipalities ───────────────────────────────────────────────────────
@st.cache_data(ttl=3600)
def load_municipalities() -> list[str]:
    df = query("SELECT DISTINCT municipality FROM spanish_housing_radar.main_silver.int_listings_current ORDER BY 1")
    return df["municipality"].tolist()

munis = load_municipalities()

# ── Sidebar filters ───────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Filters")
    op           = operation_filter()
    muni         = municipality_filter(munis)
    prop         = property_type_filter()
    min_p, max_p = price_range_filter(
        min_val=0,
        max_val=2_000_000 if op == "sale" else 5_000,
        step=10_000 if op == "sale" else 100,
        label="Price (€)" if op == "sale" else "Monthly rent (€)",
    )
    min_score = st.slider("Min opportunity score", 0, 100, 0)

# ── Load data ─────────────────────────────────────────────────────────────────
sql = (Path(__file__).parent.parent / "queries" / "opportunities.sql").read_text()

@st.cache_data(ttl=600, show_spinner="Loading listings…")
def load_opportunities(op, prop, muni, min_p, max_p):
    return query(sql, operation_type=op, property_type=prop,
                 municipality=muni, min_price=min_p, max_price=max_p)

df = load_opportunities(op, prop, muni, min_p, max_p)
df = df[df["opportunity_score"] >= min_score]

if df.empty:
    st.warning("No results match the current filters.")
    st.stop()

# ── Summary metrics ───────────────────────────────────────────────────────────
c1, c2, c3, c4 = st.columns(4)
c1.metric("Listings",          len(df))
c2.metric("Median price",      f"€{df['price_eur'].median():,.0f}")
c3.metric("Median €/sqm",      f"€{df['price_per_sqm'].median():,.0f}")
c4.metric("Avg score",         f"{df['opportunity_score'].mean():.1f}/100")

# ── Deal tier breakdown ───────────────────────────────────────────────────────
st.markdown("#### Deal tier breakdown")
tier_counts = df["deal_tier"].value_counts().rename(index=DEAL_TIER_LABELS)
st.bar_chart(tier_counts)

# ── Map ───────────────────────────────────────────────────────────────────────
st.markdown("#### Map")
listings_map(df)

# ── Scatter ───────────────────────────────────────────────────────────────────
st.markdown("#### Size vs Price")
st.plotly_chart(scatter_size_vs_price(df), use_container_width=True)

# ── Listing cards ─────────────────────────────────────────────────────────────
st.markdown("#### Listings")
st.caption(f"{len(df)} results · sorted by opportunity score")

tab_cards, tab_table = st.tabs(["🃏 Cards", "📋 Table"])

with tab_cards:
    for _, row in df.head(30).iterrows():
        listing_card(row.to_dict())

with tab_table:
    cols = [
        "neighborhood", "district", "price_eur", "size_sqm", "rooms",
        "price_per_sqm", "neighborhood_median_ppsqm", "ppsqm_vs_median",
        "opportunity_score", "deal_tier", "low_confidence_flag",
    ]
    st.dataframe(
        df[cols].rename(columns={
            "neighborhood":              "Neighborhood",
            "district":                  "District",
            "price_eur":                 "Price (€)",
            "size_sqm":                  "sqm",
            "rooms":                     "Beds",
            "price_per_sqm":             "€/sqm",
            "neighborhood_median_ppsqm": "Neighborhood median",
            "ppsqm_vs_median":           "Δ median",
            "opportunity_score":         "Score",
            "deal_tier":                 "Tier",
            "low_confidence_flag":       "⚠️ Low data",
        }),
        use_container_width=True,
        hide_index=True,
    )