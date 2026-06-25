"""
Spanish Housing Radar — entry point & navigation router.

Uses st.navigation (Streamlit ≥ 1.36) so the sidebar shows grouped, icon-led
pages instead of the raw `NN_filename` auto-listing. set_page_config lives ONLY
here; the individual view scripts must not call it.
"""
from config import PAGE_ICON, PAGE_TITLE
import streamlit as st
from styles import inject_css

st.set_page_config(
    page_title=PAGE_TITLE,
    page_icon=PAGE_ICON,
    layout="wide",
    initial_sidebar_state="expanded",
)
inject_css()

home = st.Page("views/home.py", title="Home", icon="🏠", default=True)
opportunities = st.Page("views/01_opportunities.py", title="Opportunities", icon="🔍")
market = st.Page("views/02_market.py", title="Market", icon="📊")
mortgage = st.Page("views/03_mortgage.py", title="Mortgage", icon="🧮")
affordability = st.Page("views/04_affordability.py", title="Affordability", icon="💰")

nav = st.navigation(
    {
        "Overview": [home],
        "Explore the market": [opportunities, market],
        "Can I afford it?": [mortgage, affordability],
    }
)

with st.sidebar:
    st.caption("Spanish Housing Radar · data from Idealista")

nav.run()
