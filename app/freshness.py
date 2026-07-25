"""
Freshness strip — facts about data currency and quality.

Computes metrics from the warehouse and dbt test results, building a sequence
of StripItems for the header on every page. Cached so repeated page loads don't
re-query the warehouse.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from connection import query
from theme import StripItem

# Project root (one up from app/).
PROJECT_ROOT = Path(__file__).parent.parent


@st.cache_resource(ttl=3600)
def _load_dbt_results() -> dict:
    """Read dbt's run_results.json to count passing tests."""
    path = PROJECT_ROOT / "transform" / "target" / "run_results.json"
    if not path.exists():
        return {"passed": 0, "failed": 0, "error": 0}
    try:
        with open(path) as f:
            data = json.load(f)
        # run_results.json has `results: [{status: "pass" | "fail", ...}, ...]`
        # and a top-level `stats` summary.
        if "stats" in data:
            return data["stats"]
        return {"passed": 0, "failed": 0, "error": 0}
    except Exception:
        return {"passed": 0, "failed": 0, "error": 0}


@st.cache_data(ttl=600)
def get_freshness_strip() -> list[StripItem]:
    """
    Build the freshness strip: six key facts about data currency and quality.

    Returns a list of StripItems for app/theme.render_header().
    """
    items: list[StripItem] = []

    # ── Last ingest date ───────────────────────────────────────────────────
    try:
        last_ingest = query("""
            SELECT MAX(_loaded_at::date) AS last_run
            FROM spanish_housing_radar.main_silver.int_listings_current
        """).iloc[0]["last_run"]
        items.append(StripItem(
            label="last ingest",
            value=str(last_ingest),
            tone="good" if pd.notna(last_ingest) else "warn",
        ))
    except Exception:
        items.append(StripItem(
            label="last ingest",
            value="—",
            tone="bad",
            help="Could not query warehouse",
        ))

    # ── Listings in warehouse ──────────────────────────────────────────────
    try:
        listing_count = query("""
            SELECT COUNT(*) as n FROM spanish_housing_radar.main_silver.int_listings_current
        """).iloc[0]["n"]
        items.append(StripItem(
            label="listings",
            value=f"{int(listing_count):,}",
        ))
    except Exception:
        items.append(StripItem(
            label="listings",
            value="—",
            tone="bad",
            help="Could not query warehouse",
        ))

    # ── Cities covered ─────────────────────────────────────────────────────
    try:
        city_count = query("""
            SELECT COUNT(DISTINCT municipality)
            FROM spanish_housing_radar.main_silver.int_listings_current
        """).iloc[0][0]
        items.append(StripItem(
            label="cities",
            value=str(int(city_count)),
        ))
    except Exception:
        items.append(StripItem(
            label="cities",
            value="—",
            tone="bad",
        ))

    # ── Neighbourhood grain % ──────────────────────────────────────────────
    try:
        grain_pct = query("""
            SELECT
                ROUND(
                    100.0 * COUNT(*) FILTER (WHERE benchmark_level = 'neighbourhood')
                    / NULLIF(COUNT(*), 0)
                , 1) AS pct
            FROM spanish_housing_radar.main_gold.fct_listings_scored
        """).iloc[0]["pct"]
        tone = "good" if (pd.notna(grain_pct) and grain_pct >= 70) else "warn"
        items.append(StripItem(
            label="neighbourhood",
            value=f"{grain_pct:.1f}%",
            tone=tone,
            help="% of listings scored at barrio grain; city fallback is lower confidence",
        ))
    except Exception:
        items.append(StripItem(
            label="neighbourhood",
            value="—",
            tone="bad",
        ))

    # ── dbt tests passing ──────────────────────────────────────────────────
    results = _load_dbt_results()
    passed = results.get("passed", 0)
    failed = results.get("failed", 0)
    error = results.get("error", 0)
    if isinstance(passed, dict):
        # run_results.json stats might be a nested object; normalise.
        passed = passed.get("total", 0) if isinstance(passed, dict) else passed
    total = max(passed + failed + error, 1)  # avoid div by zero
    test_tone = "good" if (failed == 0 and error == 0) else "warn"
    items.append(StripItem(
        label="tests",
        value=f"{int(passed)}/{int(total)} passing",
        tone=test_tone,
        help="dbt data-quality tests on sources and models",
    ))

    # ── Scraping status ────────────────────────────────────────────────────
    # This is hardcoded because scraping pauses at the orchestration layer
    # (Prefect `SCRAPFLY_ENABLED=false`), not at the warehouse schema.
    # The README announces it, and the header repeats it here for honesty.
    items.append(StripItem(
        label="scraping",
        value="paused",
        tone="warn",
        help="Idealista extraction is on hold (Scrapfly credits). "
             "INE feed runs weekly. Resume by setting SCRAPFLY_ENABLED=true.",
    ))

    return items
