"""
The city list and the one control that picks from it.

Every page asks the same question — which cities can be shown? — so the answer
and the widget live here. Each page writing its own list is what once let the
affordability page ship a hardcoded three-city dropdown while the warehouse
held eight.
"""
from __future__ import annotations

from connection import query
import streamlit as st

DEFAULT_CITY = "valència"


@st.cache_data(ttl=3600)
def load_municipalities() -> list[str]:
    """
    The cities with scored listings.

    Read from the gold view, not from every city ever scraped: a city whose
    listings have all aged out of int_listings_screened (ADR-0009) still sits in
    the history, and offering it would open a page with nothing on it.
    """
    df = query(
        "SELECT DISTINCT municipality "
        "FROM spanish_housing_radar.main_gold.rpt_opportunities "
        "WHERE municipality IS NOT NULL ORDER BY 1"
    )
    return df["municipality"].tolist()


def city_picker(cities: list[str], **kwargs) -> str:
    """
    A city selectbox — or nothing, when there is only one city to pick.

    A dropdown with a single option is a control that does nothing, and it
    suggests there should be more. With one city the choice is already made;
    the page names it in its own copy.
    """
    options = sorted(cities) or [DEFAULT_CITY]
    if len(options) == 1:
        return options[0]
    return st.selectbox(
        "City", options,
        index=options.index(DEFAULT_CITY) if DEFAULT_CITY in options else 0,
        format_func=str.title, **kwargs,
    )
