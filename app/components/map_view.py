"""
Map component using pydeck (bundled with Streamlit).
Falls back gracefully if lat/lon are null.
"""
from __future__ import annotations

import pandas as pd
import pydeck as pdk
import streamlit as st

from config import DEAL_TIER_COLORS


def _tier_to_rgb(tier: str) -> list[int]:
    hex_color = DEAL_TIER_COLORS.get(tier, "#94a3b8").lstrip("#")
    return [int(hex_color[i:i+2], 16) for i in (0, 2, 4)]


def listings_map(df: pd.DataFrame) -> None:
    geo = df.dropna(subset=["lat", "lon"]).copy()

    if geo.empty:
        st.info("Current listings have no GPS coordinates. They will appear here once coordinates are available.")
        return

    geo["color"] = geo["deal_tier"].apply(_tier_to_rgb)
    geo["tooltip_text"] = geo.apply(
        lambda r: f"€{r['price_eur']:,.0f} · {r['size_sqm']:.0f}sqm · Score {r['opportunity_score']:.0f}",
        axis=1,
    )

    view = pdk.ViewState(
        latitude=geo["lat"].mean(),
        longitude=geo["lon"].mean(),
        zoom=12,
        pitch=0,
    )

    layer = pdk.Layer(
        "ScatterplotLayer",
        data=geo,
        get_position=["lon", "lat"],
        get_color="color",
        get_radius=80,
        pickable=True,
        auto_highlight=True,
    )

    st.pydeck_chart(
        pdk.Deck(
            layers=[layer],
            initial_view_state=view,
            tooltip={"text": "{tooltip_text}"},
            map_style="mapbox://styles/mapbox/light-v11",
        )
    )