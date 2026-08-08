"""
Freshness strip — facts about data currency and quality.

Computes metrics from the warehouse and dbt test results, building a sequence
of StripItems for the header on every page. Cached so repeated page loads don't
re-query the warehouse.
"""
from __future__ import annotations

import json
from pathlib import Path

from connection import query
import pandas as pd
import streamlit as st
from theme import StripItem

# Project root (one up from app/).
PROJECT_ROOT = Path(__file__).parent.parent


DBT_DOCS_URL = "https://carlosdmv7.github.io/spanish-housing-radar/"


@st.cache_resource(ttl=3600)
def _load_dbt_test_results() -> dict | None:
    """
    Count dbt test outcomes from `run_results.json`, or None when unavailable.

    `transform/target/` is gitignored, so this artifact exists on a dev machine
    that has run `dbt build` and *not* on the deployed app. None means "no
    evidence" — the caller must say so rather than render a zero, because a
    header claiming "0 tests" is worse than one admitting it can't tell.
    """
    path = PROJECT_ROOT / "transform" / "target" / "run_results.json"
    if not path.exists():
        return None
    try:
        with path.open() as f:
            data = json.load(f)
        # run_results.json holds every executed node; test nodes are the ones
        # prefixed `test.`. Models report "success", tests "pass"/"fail"/"error".
        tests = [r for r in data.get("results", [])
                 if str(r.get("unique_id", "")).startswith("test.")]
        if not tests:
            return None
        counts = {"pass": 0, "fail": 0, "error": 0, "skipped": 0}
        for r in tests:
            counts[r.get("status", "error")] = counts.get(r.get("status", "error"), 0) + 1
        counts["total"] = len(tests)
        counts["generated_at"] = data.get("metadata", {}).get("generated_at", "")[:10]
        return counts
    except Exception:
        return None


@st.cache_resource(ttl=3600)
def _load_committed_status() -> dict | None:
    """
    The pass/total the CI pipeline last committed, or None.

    Unlike `run_results.json` this file *is* checked in, so it is the only test
    evidence that survives a deploy. It is written by `orchestration/status.py`
    on every pipeline run, `if: always()`, which is what makes it usable here:
    a red run overwrites it, so a stale-but-passing figure can't outlive the
    failure that invalidated it.

    Deliberately no fail/error breakdown — the file records passed and total,
    and the caller derives "broken" from the gap rather than inventing a
    per-status split the schema never promised.
    """
    path = PROJECT_ROOT / "docs" / "status.json"
    if not path.exists():
        return None
    try:
        with path.open() as f:
            data = json.load(f)
        passed, total = data.get("dbt_tests_passed"), data.get("dbt_tests_total")
        # The contract's own rule: an unknown figure is null, never 0. Honour it
        # on the read side too, or "couldn't tell" renders as "0/0 passing".
        if not isinstance(passed, int) or not isinstance(total, int) or total == 0:
            return None
        return {
            "pass": passed,
            "total": total,
            "generated_at": str(data.get("generated_at") or "")[:10],
            "conclusion": data.get("last_run_conclusion") or "unknown",
        }
    except Exception:
        return None


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
        # DuckDB's DATE arrives as a pandas Timestamp, whose str() carries a
        # 00:00:00 that implies a precision the daily pipeline doesn't have.
        stale_days = (pd.Timestamp.today().normalize() - pd.Timestamp(last_ingest)).days
        items.append(StripItem(
            label="last ingest",
            value=pd.Timestamp(last_ingest).date().isoformat(),
            tone="good" if stale_days <= 7 else "warn",
            help=f"Most recent row written to the warehouse — {stale_days} days ago. "
                 "Listing scraping is paused, so this date is expected to sit still; "
                 "the INE market-context feed still refreshes weekly.",
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
            SELECT COUNT(DISTINCT municipality) AS n
            FROM spanish_housing_radar.main_silver.int_listings_current
        """).iloc[0]["n"]
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

    # ── dbt tests ──────────────────────────────────────────────────────────
    results = _load_dbt_test_results()
    committed = _load_committed_status() if results is None else None
    if results is None and committed is not None:
        # The deployed app's normal path: no local dbt artifact, but the last
        # pipeline run committed its own verdict. Say which run it was and when,
        # so the number is attributable rather than merely present.
        broken = committed["total"] - committed["pass"]
        conclusion = committed["conclusion"]
        items.append(StripItem(
            label="dbt tests",
            value=f"{committed['pass']}/{committed['total']} passing",
            tone="good" if broken == 0 and conclusion == "success" else "warn",
            help="Data-quality tests on sources and models (unique, not_null, "
                 "accepted_values, accepted_range), as recorded by the pipeline run "
                 f"of {committed['generated_at'] or 'an unknown date'} "
                 f"(outcome: {conclusion}). Full results at {DBT_DOCS_URL}.",
        ))
    elif results is None:
        items.append(StripItem(
            label="dbt tests",
            value="see docs",
            help="Test results come from a build artifact that isn't deployed with "
                 f"the app. Every run's outcome is published at {DBT_DOCS_URL} and "
                 "gated in CI on each pull request.",
        ))
    else:
        broken = results["fail"] + results["error"]
        items.append(StripItem(
            label="dbt tests",
            value=f"{results['pass']}/{results['total']} passing",
            tone="good" if broken == 0 else "bad",
            help="Data-quality tests on sources and models (unique, not_null, "
                 "accepted_values, accepted_range), from the last local "
                 f"`dbt build` on {results['generated_at'] or 'an unknown date'}.",
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


@st.cache_data(ttl=600)
def get_benchmark_grain_counts() -> pd.DataFrame:
    """
    Listings per benchmark grain, with each grain's share of the total.

    Feeds the data-quality page's headline chart. Empty frame on failure — the
    caller decides what to say about it, because a chart module should not own
    the wording of an outage.
    """
    try:
        df = query("""
            SELECT
                benchmark_level,
                COUNT(*) AS listings
            FROM spanish_housing_radar.main_gold.fct_listings_scored
            GROUP BY 1
        """)
    except Exception:
        return pd.DataFrame(columns=["benchmark_level", "listings", "share"])
    total = df["listings"].sum()
    df["share"] = df["listings"] / total if total else 0.0
    return df
