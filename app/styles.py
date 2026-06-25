"""
Shared visual identity for the whole app.

`inject_css()` is called once at the top of every page (cheap — Streamlit
dedupes identical markdown). It tightens spacing, restyles metric cards and
tables, and gives the sidebar/headers a consistent look so the four pages feel
like one product instead of four scripts.
"""
from __future__ import annotations

import streamlit as st

# Palette — kept in sync with .streamlit/config.toml [theme].
ACCENT = "#3b82f6"
ACCENT_SOFT = "rgba(59,130,246,0.12)"
SURFACE = "#161b26"
SURFACE_BORDER = "rgba(148,163,184,0.18)"
MUTED = "#94a3b8"

_CSS = f"""
<style>
/* ── Layout polish ─────────────────────────────────────────────────────── */
.block-container {{ padding-top: 2.2rem; padding-bottom: 3rem; max-width: 1300px; }}
section[data-testid="stSidebar"] {{ border-right: 1px solid {SURFACE_BORDER}; }}

/* ── Metric cards ──────────────────────────────────────────────────────── */
div[data-testid="stMetric"] {{
    background: {SURFACE};
    border: 1px solid {SURFACE_BORDER};
    border-radius: 12px;
    padding: 14px 16px;
}}
div[data-testid="stMetric"] label p {{ color: {MUTED}; font-size: 0.78rem; }}
div[data-testid="stMetricValue"] {{ font-size: 1.7rem; font-weight: 700; }}

/* ── Tabs ──────────────────────────────────────────────────────────────── */
button[data-baseweb="tab"] {{ font-weight: 600; }}

/* ── Dataframes ────────────────────────────────────────────────────────── */
div[data-testid="stDataFrame"] {{ border-radius: 10px; }}

/* ── Headings ──────────────────────────────────────────────────────────── */
h1 {{ font-weight: 800; letter-spacing: -0.02em; }}
h2, h3 {{ font-weight: 700; letter-spacing: -0.01em; }}

/* ── Page hero ─────────────────────────────────────────────────────────── */
.shr-hero {{
    background: linear-gradient(135deg, {ACCENT_SOFT} 0%, rgba(59,130,246,0.02) 100%);
    border: 1px solid {SURFACE_BORDER};
    border-radius: 16px;
    padding: 22px 26px;
    margin-bottom: 8px;
}}
.shr-hero h1 {{ margin: 0; font-size: 2rem; }}
.shr-hero p {{ margin: 6px 0 0 0; color: {MUTED}; font-size: 0.95rem; }}

/* ── Section label ─────────────────────────────────────────────────────── */
.shr-section {{
    font-size: 0.78rem; font-weight: 700; letter-spacing: 0.08em;
    text-transform: uppercase; color: {MUTED};
    margin: 8px 0 2px 0;
}}
</style>
"""


def inject_css() -> None:
    """Inject the shared stylesheet. Safe to call on every page."""
    st.markdown(_CSS, unsafe_allow_html=True)


def page_hero(icon: str, title: str, subtitle: str) -> None:
    """Render a consistent page header banner."""
    inject_css()
    st.markdown(
        f"<div class='shr-hero'><h1>{icon}&nbsp; {title}</h1>"
        f"<p>{subtitle}</p></div>",
        unsafe_allow_html=True,
    )


def section(label: str) -> None:
    """Small uppercase section divider used to break up a page."""
    st.markdown(f"<div class='shr-section'>{label}</div>", unsafe_allow_html=True)
