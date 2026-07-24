"""
Listing card component — renders a single listing as a styled Streamlit card.
"""
from __future__ import annotations

from config import DEAL_TIER_COLORS, DEAL_TIER_LABELS
import pandas as pd
import streamlit as st


def listing_card(row: dict) -> None:
    tier   = row.get("deal_tier", "fair")
    color  = DEAL_TIER_COLORS.get(tier, "#94a3b8")
    label  = DEAL_TIER_LABELS.get(tier, tier)
    rooms_val = row.get("rooms")
    rooms  = f"{int(rooms_val)} bed · " if pd.notna(rooms_val) else ""
    size   = f"{row['size_sqm']:.0f} sqm"
    hood   = (row.get("neighborhood") or "").title()
    dist   = (row.get("district") or "").title()
    loc    = f"{hood}, {dist}" if dist else hood

    with st.container(border=True):
        col1, col2 = st.columns([3, 1])
        with col1:
            st.markdown(f"**{rooms}{size}** · {loc}")
            st.caption(f"{row['source_name'].capitalize()} · {row.get('scraped_date', '')}")

            # Behavioural signal — only shown when the history actually supports it
            dom = row.get("days_on_market") or 0
            cuts = row.get("n_price_changes") or 0
            if row.get("seller_motivation") in ("medium", "high"):
                bits = []
                if dom >= 21:
                    bits.append(f"{int(dom)} days listed")
                if cuts >= 1:
                    pct = row.get("price_change_pct") or 0
                    bits.append(f"{int(cuts)} price cut{'s' if cuts > 1 else ''} ({pct:+.0f}%)")
                if bits:
                    st.caption("🔥 Motivated seller · " + " · ".join(bits))

            if row.get("low_confidence_flag"):
                st.caption("⚠️ Few comparable listings in this neighborhood — score may be unreliable")
        with col2:
            st.markdown(
                f"<div style='text-align:right;font-size:1.3rem;font-weight:700'>"
                f"€{row['price_eur']:,.0f}</div>"
                f"<div style='text-align:right;color:{color};font-size:0.85rem'>{label}</div>",
                unsafe_allow_html=True,
            )

        level = row.get("benchmark_level", "city")
        level_label = {"neighbourhood": "Area median", "district": "District median",
                       "city": "City median"}.get(level, "Benchmark")

        col3, col4, col5 = st.columns(3)
        col3.metric("€/sqm",            f"€{row['price_per_sqm']:,.0f}")
        col4.metric(level_label,        f"€{row['neighborhood_median_ppsqm']:,.0f}",
                    help=f"Scored against the {level} median ({int(row.get('benchmark_comp_count', 0))} comparable listings)")
        col5.metric("Opportunity score", f"{row['opportunity_score']:.0f}/100")

        st.markdown(
            f"<a href='{row['url']}' target='_blank'>View on {row['source_name'].capitalize()} →</a>",
            unsafe_allow_html=True,
        )
