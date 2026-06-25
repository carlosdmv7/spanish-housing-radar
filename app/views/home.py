"""
Home — landing page: what the tool is, live data freshness, and where to go.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from connection import query
import pandas as pd
import streamlit as st
from styles import page_hero, section

page_hero(
    "🏠",
    "Spanish Housing Radar",
    "Find under-priced flats across Spain. Listings are scored against their own "
    "neighbourhood, so a cheap flat in a pricey area rises to the top.",
)

# ── Live data snapshot ────────────────────────────────────────────────────────
try:
    stats = query("""
        SELECT
            COUNT(DISTINCT listing_pk)    AS total_listings,
            COUNT(DISTINCT municipality)  AS cities,
            COUNT(DISTINCT neighborhood)  AS neighborhoods,
            MAX(_loaded_at::date)         AS last_run
        FROM spanish_housing_radar.main_silver.int_listings_current
    """)
    row = stats.iloc[0]

    section("Live snapshot")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Active listings", f"{int(row['total_listings']):,}")
    c2.metric("Cities", int(row["cities"]))
    c3.metric("Neighbourhoods", int(row["neighborhoods"]))
    c4.metric("Last updated", str(row["last_run"]))

    # Freshness guard — the daily pipeline should refresh this; warn if it hasn't.
    days_stale = (pd.Timestamp.today().normalize() - pd.Timestamp(row["last_run"])).days
    if days_stale >= 3:
        st.warning(
            f"⚠️ Data is **{days_stale} days old** — the daily pipeline may not have "
            f"run recently. Figures below may be stale."
        )

    # ── Coverage by city (Valencia is the focus market) ───────────────────────
    cov = query("""
        SELECT
            INITCAP(municipality)                               AS city,
            COUNT(*) FILTER (WHERE operation_type = 'sale')     AS for_sale,
            COUNT(*) FILTER (WHERE operation_type = 'rent')     AS for_rent
        FROM spanish_housing_radar.main_silver.int_listings_current
        GROUP BY 1
        ORDER BY (for_sale + for_rent) DESC
    """)
    section("Coverage by city")
    st.dataframe(
        cov.rename(columns={"city": "City", "for_sale": "For sale", "for_rent": "For rent"}),
        use_container_width=True,
        hide_index=True,
    )
except Exception as e:
    st.warning(f"Could not load the live snapshot: {e}")

st.markdown("")
section("Where to go")
st.markdown("""
| Page | What you'll find |
|---|---|
| 🔍 **Opportunities** | Listings ranked by opportunity score — cheapest vs their neighbourhood first. |
| 📊 **Market** | €/sqm benchmarks per neighbourhood, price spread, historical trends. |
| 🧮 **Mortgage** | Fixed vs variable simulator with full French amortisation schedule. |
| 💰 **Affordability** | What you need to earn to buy in each neighbourhood, plus buy-vs-rent. |
""")
st.caption("Tip: most data is in **Valencia** — it's selected by default on every page.")
