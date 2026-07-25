"""
Shared brand chrome — tokens, Altair theme, chart scales, header and footer.

This file is intended to be **byte-identical** across every Streamlit app in the
portfolio, so it must stay free of project-specific knowledge: no SQL, no table
names, no domain vocabulary. The freshness strip is therefore *passed in* as a
sequence of `StripItem`s — each app computes its own facts and this module only
decides how they look.

No CSS injection anywhere. Colour comes from two native mechanisms only:
  * `.streamlit/config.toml` `[theme]` keys (page chrome, widgets, links);
  * Streamlit's native markdown colour directive,
    `:color[text]{foreground="#RRGGBB"}`, for exact brand hex in the strip.
Charts are themed declaratively through the registered Altair theme. Nothing here
depends on Streamlit's internal DOM, so a version bump can't silently break the
look.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

import altair as alt
import streamlit as st

# ══════════════════════════════════════════════════════════════════════════════
# Brand tokens — authoritative, shared across all repos. Do not substitute.
# ══════════════════════════════════════════════════════════════════════════════
SAND_100 = "#F6E2B3"
AMBER_500 = "#E7A84E"
RUST_500 = "#D96C2C"
TEAL_500 = "#3E8E7E"
PETROL_900 = "#274C56"

# Derived — required.
SURFACE = "#FDFAF4"    # page background
SURFACE_2 = "#F5EFE3"  # cards, sidebar
BORDER = "#E4D9C4"     # hairlines
INK = "#274C56"        # body text
INK_MUTED = "#5C7480"  # secondary text
RUST_700 = "#A8501F"   # links, primary button fill (white label)
TEAL_700 = "#2E6B5E"   # success, secondary button fill (white label)
RUST_050 = "#FBEADF"
TEAL_050 = "#E4F0EC"

# Darkest step of the sequential ramp — the only safe "alarm" text colour, since
# the palette has no red and RUST_500 is too light for text (3.4:1).
RUST_900 = "#6E2F10"

FONT_STACK = "sans-serif"

# ══════════════════════════════════════════════════════════════════════════════
# Chart scales
# ══════════════════════════════════════════════════════════════════════════════
# Categorical — max 5 series. Beyond that, aggregate instead of adding colours.
CATEGORICAL: list[str] = [PETROL_900, RUST_500, TEAL_500, AMBER_500, INK_MUTED]

# Diverging — for anything with a meaningful midpoint (opportunity score,
# z-score, the map). Teal = below benchmark (good deal), rust = above
# (overpriced). Colourblind-safe blue–orange axis: never swap in green→red.
DIVERGING: list[str] = [TEAL_700, "#7FB3A4", SAND_100, AMBER_500, RUST_500]

# Sequential — counts and density.
SEQUENTIAL: list[str] = [SAND_100, AMBER_500, RUST_500, RUST_700, RUST_900]

# ── Accessibility guard rails ────────────────────────────────────────────────
# Verified contrast against SURFACE. AMBER_500 (2.1:1) and RUST_500 (3.4:1) are
# fills/icons/borders only — never text. These are the text-safe tokens.
TEXT_SAFE_ON_SURFACE: tuple[str, ...] = (INK, INK_MUTED, RUST_700, TEAL_700, RUST_900)
# White labels are only legible on the 700-weight fills, never on the 500s.
WHITE_LABEL_FILLS: tuple[str, ...] = (RUST_700, TEAL_700, PETROL_900)


# ══════════════════════════════════════════════════════════════════════════════
# Altair theme — registered from the tokens above
# ══════════════════════════════════════════════════════════════════════════════
THEME_NAME = "portfolio-brand"


@alt.theme.register(THEME_NAME, enable=True)
def _portfolio_brand() -> alt.theme.ThemeConfig:
    """Every chart inherits the brand without per-chart styling at the call site."""
    return {
        "config": {
            "background": SURFACE,
            "font": FONT_STACK,
            "view": {"stroke": "transparent", "continuousHeight": 320},
            "title": {
                "color": INK,
                "fontSize": 15,
                "fontWeight": 600,
                "anchor": "start",
                "offset": 12,
                "subtitleColor": INK_MUTED,
                "subtitleFontSize": 12,
            },
            # Axis furniture is INK_MUTED (4.6:1) — readable but recessive, so the
            # marks carry the colour. Grid lines are BORDER hairlines, dashed.
            "axis": {
                "labelColor": INK_MUTED,
                "labelFontSize": 11,
                "titleColor": INK_MUTED,
                "titleFontSize": 11,
                "titleFontWeight": 600,
                "domainColor": BORDER,
                "tickColor": BORDER,
                "gridColor": BORDER,
                "gridDash": [2, 2],
            },
            "axisX": {"grid": False},
            "axisY": {"domain": False, "ticks": False, "labelPadding": 6},
            "legend": {
                "labelColor": INK,
                "labelFontSize": 11,
                "titleColor": INK_MUTED,
                "titleFontSize": 11,
                "titleFontWeight": 600,
                "symbolType": "circle",
                "orient": "top",
                "direction": "horizontal",
                "titlePadding": 6,
                "offset": 8,
            },
            "range": {
                "category": CATEGORICAL,
                "diverging": DIVERGING,
                "heatmap": SEQUENTIAL,
                "ramp": SEQUENTIAL,
                "ordinal": SEQUENTIAL,
            },
            "bar": {"fill": PETROL_900, "cornerRadiusEnd": 3},
            "line": {"stroke": RUST_500, "strokeWidth": 2},
            "point": {"fill": RUST_500, "size": 60, "strokeWidth": 0, "opacity": 0.8},
            "area": {"fill": TEAL_500, "opacity": 0.7},
            "rule": {"stroke": INK_MUTED},
            "text": {"color": INK, "fontSize": 11},
            "header": {"labelColor": INK, "titleColor": INK_MUTED},
        }
    }


def altair_chart(chart: alt.TopLevelMixin, **kwargs) -> None:
    """
    Render an Altair chart with the brand theme actually applied.

    `st.altair_chart` defaults to `theme="streamlit"`, which overrides the
    registered Altair theme with Streamlit's own palette — so every brand chart
    must pass `theme=None`. Routing through this helper means no call site can
    forget and silently render in Streamlit blue.
    """
    kwargs.setdefault("width", "stretch")
    st.altair_chart(chart, theme=None, **kwargs)


# ══════════════════════════════════════════════════════════════════════════════
# Header / footer chrome
# ══════════════════════════════════════════════════════════════════════════════
AUTHOR_NAME = "Carlos De Manuel"
AUTHOR_ROLE = "Analytics Engineer"
PORTFOLIO_URL = "https://carlosdmv7.github.io/personal-portfolio/"
LINKEDIN_URL = "https://www.linkedin.com/in/carlos-de-manuel"

Tone = Literal["neutral", "good", "warn", "bad"]

# Tone → text colour. Every one of these clears 4.5:1 on SURFACE; the palette has
# no red, so "bad" is the darkest rust rather than a colour outside the brand.
_TONE_COLOR: dict[str, str] = {
    "neutral": INK,
    "good": TEAL_700,
    "warn": RUST_700,
    "bad": RUST_900,
}


@dataclass(frozen=True)
class StripItem:
    """
    One fact in the freshness strip.

    `label` is the quiet part, `value` the loud part, `tone` carries the verdict.
    `help` becomes a tooltip so the strip can stay terse without losing the
    caveat. Values must arrive already formatted — this module does no rounding,
    no locale guessing and no unit invention.
    """

    label: str
    value: str
    tone: Tone = "neutral"
    help: str | None = None


def _mark(text: str, color: str) -> str:
    """Native markdown colour directive — exact brand hex, no CSS injection."""
    return f":color[{text}]{{foreground=\"{color}\"}}"


def _strip_markdown(items: Sequence[StripItem]) -> str:
    parts = [
        f"{_mark(item.label, INK_MUTED)} **{_mark(item.value, _TONE_COLOR[item.tone])}**"
        for item in items
    ]
    return ":small[" + "  ·  ".join(parts) + "]"


def page_hero(icon: str, title: str, subtitle: str) -> None:
    """Page title and one-line framing. Native heading, no card markup."""
    st.title(f"{icon} {title}", anchor=False)
    st.markdown(_mark(subtitle, INK_MUTED))
    st.markdown("")


def section(label: str) -> None:
    """Quiet uppercase label that breaks a page into scannable blocks."""
    st.markdown(f":small[**{_mark(label.upper(), INK_MUTED)}**]")


def render_header(freshness: Sequence[StripItem] = ()) -> None:
    """
    Persistent chrome for the top of every page: identity line, then the
    freshness strip.

    Call once per page, before any content. Pass the strip items the app computed
    from its own warehouse; pass nothing and the identity line renders alone.
    """
    identity, portfolio = st.columns([3, 1], vertical_alignment="center")
    with identity:
        st.markdown(
            f"**{AUTHOR_NAME}** · {_mark(AUTHOR_ROLE, INK_MUTED)}",
            help=None,
        )
    with portfolio:
        st.markdown(f"[← portfolio]({PORTFOLIO_URL})")

    if freshness:
        # Tooltips live on their own row of captions rather than in the strip
        # markdown, because a single markdown block can only carry one `help`.
        st.markdown(_strip_markdown(freshness))
        tips = [f"{i.label}: {i.help}" for i in freshness if i.help]
        if tips:
            with st.expander("What these numbers mean", expanded=False):
                for tip in tips:
                    st.markdown(f":small[{_mark('•', RUST_500)} {tip}]")

    st.divider()


def render_footer() -> None:
    """Closing chrome: attribution and the way back to the portfolio."""
    st.divider()
    st.markdown(
        ":small["
        f"Built by [{AUTHOR_NAME}]({PORTFOLIO_URL}) · {_mark(AUTHOR_ROLE, INK_MUTED)} · "
        f"[LinkedIn]({LINKEDIN_URL}) · [← portfolio]({PORTFOLIO_URL})"
        "]"
    )
