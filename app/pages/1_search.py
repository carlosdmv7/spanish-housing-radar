# app/pages/1_search.py
from pathlib import Path
import streamlit as st
import pandas as pd
from app.connection import get_connection

QUERY = (Path(__file__).parent.parent / "queries" / "listings.sql").read_text()

def load_listings(
    operation: str,
    municipalities: list[str],
    property_types: list[str],
    price_range: tuple[int, int],
    min_score: int,
) -> pd.DataFrame:
    conn = get_connection()
    return conn.execute(
        QUERY,
        [operation, municipalities, property_types, *price_range, min_score]
    ).df()

# --- UI ---
st.title("🏠 Spanish Housing Radar")

with st.sidebar:
    operation   = st.radio("Operation", ["sale", "rent"])
    muni        = st.multiselect("Municipality", ["madrid", "barcelona", "valencia"])
    prop_types  = st.multiselect("Type", ["apartment", "house", "other"], default=["apartment"])
    price_range = st.slider("Max price (€)", 50_000, 2_000_000, (100_000, 500_000), step=10_000)
    min_score   = st.slider("Min opportunity score", 0, 100, 50)

df = load_listings(operation, muni or ["madrid"], prop_types or ["apartment"], price_range, min_score)

# Colour-coded deal tier
TIER_COLORS = {
    "great_deal":    "🟢",
    "good_deal":     "🟡",
    "fair":          "⚪",
    "overpriced":    "🟠",
    "very_overpriced": "🔴",
}
df["deal"] = df["deal_tier"].map(TIER_COLORS)

st.dataframe(
    df[["deal", "neighborhood", "property_type", "price_eur",
        "size_sqm", "price_per_sqm", "opportunity_score"]],
    use_container_width=True,
    column_config={
        "opportunity_score": st.column_config.ProgressColumn(
            "Score", min_value=0, max_value=100
        ),
        "price_eur": st.column_config.NumberColumn("Price €", format="€%d"),
    }
)