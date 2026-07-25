"""
Spanish Housing Radar — entry point & navigation router.

`st.navigation` runs the selected page script inline, which makes this the single
place that can wrap *every* page in the shared chrome: identity line and freshness
strip above, attribution below. Doing it here rather than in five view files means
no page can ship without its data-provenance header.

`set_page_config` lives ONLY here; the view scripts must not call it.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))

from config import PAGE_ICON, PAGE_TITLE
from freshness import get_freshness_strip
import streamlit as st
from theme import render_footer, render_header

st.set_page_config(
    page_title=PAGE_TITLE,
    page_icon=PAGE_ICON,
    layout="wide",
    initial_sidebar_state="expanded",
)

home = st.Page("views/home.py", title="Home", icon="🏘️", default=True)
opportunities = st.Page("views/01_opportunities.py", title="Opportunities", icon="🔍",
                        url_path="opportunities")
market = st.Page("views/02_market.py", title="Market", icon="📊", url_path="market")
mortgage = st.Page("views/03_mortgage.py", title="Mortgage", icon="🧮", url_path="mortgage")
affordability = st.Page("views/04_affordability.py", title="Affordability", icon="💰",
                        url_path="affordability")
how_it_works = st.Page("views/05_how_it_works.py", title="How it works", icon="🔬",
                       url_path="how-it-works")

nav = st.navigation(
    {
        "Overview": [home],
        "Explore the market": [opportunities, market],
        "Can I afford it?": [mortgage, affordability],
        "Under the hood": [how_it_works],
    }
)

with st.sidebar:
    st.markdown(
        ":small[Listings from Idealista · official market context from INE · "
        "[how it works](how-it-works)]"
    )

# The strip is a handful of cached aggregate queries. If the warehouse is
# unreachable it renders its own "—" facts rather than raising, so a dead
# connection degrades the header instead of blanking the whole app.
render_header(get_freshness_strip())
nav.run()
render_footer()
