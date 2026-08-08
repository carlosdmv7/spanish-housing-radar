"""
Shared sidebar filter widgets.
Each function renders filters and returns the selected values.
"""
from __future__ import annotations

from config import OPERATION_LABELS, PROPERTY_TYPE_LABELS
from connection import query
import streamlit as st


@st.cache_data(ttl=3600)
def load_municipalities() -> list[str]:
    """
    The cities actually present in the warehouse.

    Lives here, next to the widget that consumes it, because the alternative --
    each page writing its own list -- is what let the affordability page ship a
    hardcoded three-city dropdown while the warehouse held eight.
    """
    df = query(
        "SELECT DISTINCT municipality "
        "FROM spanish_housing_radar.main_silver.int_listings_current "
        "WHERE municipality IS NOT NULL ORDER BY 1"
    )
    return df["municipality"].tolist()


def operation_filter(default: str = "sale") -> str:
    options = list(OPERATION_LABELS.keys())
    idx     = options.index(default) if default in options else 0
    return st.selectbox(
        "Operation",
        options=options,
        index=idx,
        format_func=lambda k: OPERATION_LABELS[k],
    )


def municipality_filter(municipalities: list[str], default: str = "valència") -> str:
    options = ["all"] + sorted(municipalities)
    idx = options.index(default) if default in options else 0
    return st.selectbox(
        "City",
        options=options,
        index=idx,
        format_func=lambda k: "All cities" if k == "all" else k.title(),
    )


def property_type_filter() -> str:
    options = ["all"] + list(PROPERTY_TYPE_LABELS.keys())
    return st.selectbox(
        "Property type",
        options=options,
        format_func=lambda k: "All types" if k == "all" else PROPERTY_TYPE_LABELS[k],
    )


def price_range_filter(
    min_val: float = 0,
    max_val: float = 2_000_000,
    step:    int   = 10_000,
    label:   str   = "Price range (€)",
) -> tuple[float, float]:
    return st.slider(
        label,
        min_value=int(min_val),
        max_value=int(max_val),
        value=(int(min_val), int(max_val)),
        step=step,
        format="€%d",
    )
