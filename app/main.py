"""
Spanish Housing Radar — entry point & navigation router.

Navigation sits across the top, flat: six pages, each one click away. With this
few pages, dropdown groups only hide things, and a left sidebar spent a fifth of
the screen on a menu before a single number appeared. Same pattern as the
sibling job-market-intelligence app.

Each view renders its own header through `chrome.page_header`, so the title
comes first and the data-age strip sits under it. This router used to render
the header itself, *before* running the page — which is why every screen used to
open with warehouse metadata above its own title.

`set_page_config` lives ONLY here; the view scripts must not call it.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))

from config import PAGE_ICON, PAGE_TITLE
import streamlit as st
from theme import render_footer

st.set_page_config(
    page_title=PAGE_TITLE,
    page_icon=PAGE_ICON,
    layout="wide",
    # "auto", not "collapsed". Pages still being moved to inline controls keep
    # their filters in the sidebar, and "collapsed" hid them behind a chevron a
    # visitor has no reason to click — verified in the capture of the Deals page.
    # A page with nothing in the sidebar shows no sidebar either way, so this
    # stops mattering once the last page moves its controls inline.
    initial_sidebar_state="auto",
)

# Nav labels are one or two words, to scan. Each page's H1 is the question it
# answers, in plain language — the two do different jobs, so they differ.
# Material Symbols, not emoji: they inherit the brand ink instead of importing a
# font vendor's palette.
PAGES = [
    st.Page("views/home.py", title="Overview", icon=":material/home:", default=True),
    st.Page("views/01_opportunities.py", title="Deals",
            icon=":material/sell:", url_path="deals"),
    st.Page("views/02_market.py", title="Neighbourhoods",
            icon=":material/map:", url_path="neighbourhoods"),
    st.Page("views/04_affordability.py", title="Value check",
            icon=":material/balance:", url_path="value-check"),
    st.Page("views/03_mortgage.py", title="Budget",
            icon=":material/calculate:", url_path="budget"),
    st.Page("views/05_how_it_works.py", title="How it works",
            icon=":material/science:", url_path="how-it-works"),
]

nav = st.navigation(PAGES, position="top")
nav.run()
render_footer()
