"""
Map of scored listings (pydeck — bundled with Streamlit, no Mapbox token needed).

Dots are coloured on the brand's diverging ramp, the same one the scatter and the
tier chart use: teal = priced below its benchmark, rust = above. pydeck draws no
legend of its own, so this module renders one from the same colour dict — the
alternative is an unlabelled colour field, which is not a chart.
"""
from __future__ import annotations

from config import DEAL_TIER_COLORS, DEAL_TIER_FALLBACK_COLOR, DEAL_TIER_LABELS
import pandas as pd
import pydeck as pdk
import streamlit as st
from theme import INK_MUTED, RUST_500


def _hex_to_rgb(hex_color: str) -> list[int]:
    h = hex_color.lstrip("#")
    return [int(h[i:i + 2], 16) for i in (0, 2, 4)]


def _tier_to_rgb(tier: str) -> list[int]:
    return _hex_to_rgb(DEAL_TIER_COLORS.get(tier, DEAL_TIER_FALLBACK_COLOR))


def _legend() -> None:
    parts = [
        f":color[●]{{foreground=\"{DEAL_TIER_COLORS[k]}\"}} {DEAL_TIER_LABELS[k]}"
        for k in DEAL_TIER_LABELS
    ]
    st.markdown(":small[" + "  ".join(parts) + "]")


def listings_map(df: pd.DataFrame) -> None:
    geo = df.dropna(subset=["lat", "lon"]).copy()

    if geo.empty:
        st.info(
            "**No mapped listings in this selection.** Coordinates come from a seed "
            "of barrio centroids for Valencia, Madrid, Barcelona, Sevilla and Málaga — "
            "pick one of those cities in the sidebar, or widen the price range."
        )
        return

    missing = len(df) - len(geo)
    geo["color"] = geo["deal_tier"].apply(_tier_to_rgb)
    geo["tier_label"] = geo["deal_tier"].map(DEAL_TIER_LABELS).fillna(geo["deal_tier"])
    geo["tooltip_text"] = geo.apply(
        lambda r: (
            f"€{r['price_eur']:,.0f} · {r['size_sqm']:.0f} m² · "
            f"€{r['price_per_sqm']:,.0f}/m²\n"
            f"Score {r['opportunity_score']:.0f}/100 · {r['tier_label']}\n"
            f"{(r['neighborhood'] or '').title()} · scored vs {r['benchmark_level']}"
        ),
        axis=1,
    )

    _legend()

    layer = pdk.Layer(
        "ScatterplotLayer",
        data=geo,
        get_position=["lon", "lat"],
        get_color="color",
        get_radius=80,
        radius_min_pixels=4,
        stroked=True,
        get_line_color=_hex_to_rgb(INK_MUTED),
        line_width_min_pixels=0.5,
        pickable=True,
        auto_highlight=True,
    )

    st.pydeck_chart(
        pdk.Deck(
            layers=[layer],
            initial_view_state=pdk.ViewState(
                latitude=geo["lat"].mean(),
                longitude=geo["lon"].mean(),
                zoom=12,
                pitch=0,
            ),
            tooltip={"text": "{tooltip_text}"},
            map_style="mapbox://styles/mapbox/light-v11",
        )
    )

    # Listings plot at their barrio's centroid, so several dots land on the same
    # point. Saying so is cheaper than a visitor concluding the map is broken.
    note = (
        "Dots sit at the **centre of each barrio**, not the exact address — "
        "search-card scraping doesn't expose per-listing coordinates."
    )
    if missing:
        note += (
            f" {missing:,} of {len(df):,} listings in this selection have no "
            "centroid yet and are not plotted."
        )
    st.markdown(f":small[:color[ⓘ]{{foreground=\"{RUST_500}\"}} {note}]")
