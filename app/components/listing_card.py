"""
Listing card — one listing, with the arithmetic behind its score shown inline.

ADR-0005 makes this a correctness requirement, not a nicety: any surface that
shows an opportunity score must also show the grain it was computed at and how
many comparables backed it. A score of 82 against 9 city-wide flats and a score
of 82 against 60 flats in the same barrio are not the same claim.
"""
from __future__ import annotations

from config import DEAL_TIER_COLORS, DEAL_TIER_FALLBACK_COLOR, DEAL_TIER_LABELS
import pandas as pd
import streamlit as st
from theme import INK_MUTED, RUST_700, TEAL_700

# Wording for each benchmark grain: what the listing was compared against, and
# the noun for the median shown next to it.
GRAIN_WORDING: dict[str, tuple[str, str]] = {
    "neighbourhood": ("its own barrio", "Barrio median"),
    "district": ("its district", "District median"),
    "city": ("the whole city", "City median"),
}


def _grain_wording(level: str) -> tuple[str, str]:
    return GRAIN_WORDING.get(level, (f"the {level} level", "Benchmark"))


def score_explainer(row: dict) -> str:
    """
    One line of markdown that reconstructs the score from its inputs.

    Returned rather than rendered so the caller controls placement — the card
    puts it under the metrics, the table puts it in a column tooltip.
    """
    ppsqm = row.get("price_per_sqm")
    bench = row.get("neighborhood_median_ppsqm")
    level = row.get("benchmark_level", "city")
    comps = int(row.get("benchmark_comp_count") or 0)
    compared_to, _ = _grain_wording(level)

    if not pd.notna(ppsqm) or not pd.notna(bench) or not bench:
        return f":small[{_muted(f'Scored against {compared_to} · {comps} comparables')}]"

    delta_pct = (ppsqm - bench) / bench * 100
    direction = "below" if delta_pct < 0 else "above"
    tone = TEAL_700 if delta_pct < 0 else RUST_700
    delta = f":color[{delta_pct:+.1f}%]{{foreground=\"{tone}\"}}"

    return (
        f":small[€{ppsqm:,.0f}/m² vs €{bench:,.0f}/m² across **{compared_to}** "
        f"→ **{delta}** {direction} · {comps} comparables]"
    )


def _muted(text: str) -> str:
    return f":color[{text}]{{foreground=\"{INK_MUTED}\"}}"


def confidence_note(row: dict) -> str | None:
    """
    Why this particular score deserves less trust, or None when it doesn't.

    Two separate weaknesses, deliberately worded differently: falling back off
    barrio grain (coarse comparison) and the model's own `low_confidence_flag`
    (thin city grain). The second is worse and says so.
    """
    level = row.get("benchmark_level", "city")
    comps = int(row.get("benchmark_comp_count") or 0)

    if row.get("low_confidence_flag"):
        return (
            f"**Low confidence** — only {comps} comparable listings city-wide, "
            "below the 8 this benchmark needs. Treat the score as a hint, not a verdict."
        )
    if level != "neighbourhood":
        compared_to, _ = _grain_wording(level)
        return (
            f"**Reduced confidence** — too few comparables in this barrio, so the "
            f"score comes from {compared_to}. It reads the market, not the street."
        )
    return None


def listing_card(row: dict) -> None:
    tier = row.get("deal_tier", "fair")
    color = DEAL_TIER_COLORS.get(tier, DEAL_TIER_FALLBACK_COLOR)
    label = DEAL_TIER_LABELS.get(tier, tier)

    rooms_val = row.get("rooms")
    rooms = f"{int(rooms_val)} bed · " if pd.notna(rooms_val) else ""
    hood = (row.get("neighborhood") or "").title()
    dist = (row.get("district") or "").title()
    loc = f"{hood}, {dist}" if dist else hood
    level = row.get("benchmark_level", "city")
    _, bench_label = _grain_wording(level)

    with st.container(border=True):
        head, price = st.columns([3, 1], vertical_alignment="center")
        with head:
            st.markdown(f"**{rooms}{row['size_sqm']:.0f} m²** · {loc}")
            provenance = f"{row['source_name'].capitalize()} · {row.get('scraped_date', '')}"
            st.markdown(f":small[{_muted(provenance)}]")
        with price:
            st.markdown(f"### €{row['price_eur']:,.0f}")
            st.markdown(f":small[:color[{label}]{{foreground=\"{color}\"}}]")

        m1, m2, m3 = st.columns(3)
        m1.metric("€/m²", f"€{row['price_per_sqm']:,.0f}")
        m2.metric(bench_label, f"€{row['neighborhood_median_ppsqm']:,.0f}")
        m3.metric("Opportunity score", f"{row['opportunity_score']:.0f}/100")

        st.markdown(score_explainer(row))

        note = confidence_note(row)
        if note:
            st.markdown(
                f":small[:color[:material/warning:]{{foreground=\"{RUST_700}\"}} {note}]"
            )

        # Behavioural signal — only shown when the snapshot history supports it.
        if row.get("seller_motivation") in ("medium", "high"):
            dom = row.get("days_on_market") or 0
            cuts = row.get("n_price_changes") or 0
            bits = []
            if dom >= 21:
                bits.append(f"{int(dom)} days listed")
            if cuts >= 1:
                pct = row.get("price_change_pct") or 0
                bits.append(f"{int(cuts)} price cut{'s' if cuts > 1 else ''} ({pct:+.0f}%)")
            if bits:
                st.markdown(f":small[**Motivated seller** · {' · '.join(bits)}]")

        st.markdown(f"[View on {row['source_name'].capitalize()} →]({row['url']})")
