"""
Spanish Housing Radar — main entry point.
Configures page layout and shows a landing summary.
"""
from config import PAGE_ICON, PAGE_TITLE
from connection import query
import streamlit as st

st.set_page_config(
    page_title=PAGE_TITLE,
    page_icon=PAGE_ICON,
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title(f"{PAGE_ICON} {PAGE_TITLE}")
st.caption("Spanish real estate market analysis · Data from Idealista")

st.markdown("---")

# ── Quick stats ───────────────────────────────────────────────────────────────
try:
    stats = query("""
        SELECT
            COUNT(DISTINCT listing_pk)    AS total_listings,
            COUNT(DISTINCT municipality)  AS cities,
            COUNT(DISTINCT neighborhood)  AS neighborhoods,
            MIN(_loaded_at::date)         AS first_run,
            MAX(_loaded_at::date)         AS last_run
        FROM spanish_housing_radar.main_silver.int_listings_current
    """)

    row = stats.iloc[0]
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Active listings",  f"{int(row['total_listings']):,}")
    c2.metric("Cities",           int(row['cities']))
    c3.metric("Neighborhoods",    int(row['neighborhoods']))
    c4.metric("First snapshot",   str(row['first_run']))
    c5.metric("Latest snapshot",  str(row['last_run']))

except Exception as e:
    st.warning(f"Could not load stats: {e}")

st.markdown("---")
st.markdown("""
### How to use this app

| Page | What you'll find |
|---|---|
| 🔍 **Opportunities** | Listings ranked by opportunity score — cheapest vs their neighborhood appear first. |
| 📊 **Market** | €/sqm by neighborhood, price distribution, historical trends. |
| 🏠 **Mortgage** | Fixed vs variable simulator with full French amortisation schedule. |
| 💰 **Affordability** | How much do you need to earn to buy in each neighborhood? Buy vs rent comparison. |

Use the left sidebar to navigate.
""")
