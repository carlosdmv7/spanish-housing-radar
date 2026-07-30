"""
Publish `docs/status.json` — the pipeline's own health record, committed to git.

Run at the end of every pipeline run, including failed ones:

    python -m orchestration.status

Why a committed file rather than a query:

* `transform/target/run_results.json` is gitignored, so the deployed Streamlit
  app can never read dbt's own artifact. This file is the distilled, committed
  version of what it needs.
* A run that dies before `dbt build` leaves no artifact at all. Writing this
  under `if: always()` is what turns "the workflow went red" into a *recorded*
  fact with a timestamp, instead of something you only see by opening Actions.
* The git history of this one file is a free, permanent record of when the
  warehouse last built clean — the honest version of a green badge.

Everything here degrades to `None` rather than to a plausible-looking zero.
A status file that reports `dbt_tests_passed: 0` when it simply could not read
the artifact is worse than one that admits it does not know: the first is a
false red, the second is legible. The same rule the app's freshness header
follows (`app/freshness.py`).
"""
from __future__ import annotations

from datetime import UTC, datetime
import json
import os
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
STATUS_PATH = PROJECT_ROOT / "docs" / "status.json"
RUN_RESULTS_PATH = PROJECT_ROOT / "transform" / "target" / "run_results.json"

PROJECT_NAME = "spanish-housing-radar"

# The app's contract table — the view the Streamlit app actually consumes, so
# its row count is the number that means "there is something to show".
ROW_COUNT_SQL = "SELECT COUNT(*) FROM spanish_housing_radar.main_gold.rpt_opportunities"

# "Last ingest" is the most recent write to a *landing* table, not to a dbt
# model: a dbt rebuild refreshes models from data that may be weeks old, and
# reading a model's timestamp would report the rebuild as if it were an ingest.
# Listing scraping is currently paused while the INE feed still runs weekly, so
# taking the max across both is what keeps this field truthful either way.
LAST_INGEST_SQL = """
SELECT MAX(_loaded_at) FROM (
    SELECT _loaded_at FROM raw.idealista_listings
    UNION ALL
    SELECT _loaded_at FROM raw.ine_hpi
)
"""


def _utc_now_iso() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat()


def read_dbt_test_results() -> tuple[int | None, int | None]:
    """
    Return (passed, total) dbt test counts from run_results.json.

    (None, None) when the artifact is missing or unparseable — which is the
    normal case for a run that failed before `dbt build` ever executed.
    """
    if not RUN_RESULTS_PATH.exists():
        return None, None
    try:
        data = json.loads(RUN_RESULTS_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        return None, None

    # run_results.json holds every executed node; test nodes are the ones whose
    # unique_id is prefixed `test.`. Models report "success", tests "pass".
    tests = [
        r for r in data.get("results", [])
        if str(r.get("unique_id", "")).startswith("test.")
    ]
    if not tests:
        return None, None
    passed = sum(1 for r in tests if r.get("status") == "pass")
    return passed, len(tests)


def query_warehouse() -> tuple[int | None, str | None]:
    """
    Return (rows_in_warehouse, last_ingest_at) from MotherDuck.

    (None, None) when the token is absent or the warehouse is unreachable. The
    two are fetched together because either both are trustworthy or neither is.
    """
    token = os.environ.get("MOTHERDUCK_TOKEN")
    if not token:
        print("MOTHERDUCK_TOKEN not set — reporting warehouse figures as null.")
        return None, None

    try:
        import duckdb

        database = os.environ.get("MOTHERDUCK_DATABASE", "spanish_housing_radar")
        con = duckdb.connect(f"md:{database}?motherduck_token={token}")
        try:
            rows = con.execute(ROW_COUNT_SQL).fetchone()[0]
            last_ingest = con.execute(LAST_INGEST_SQL).fetchone()[0]
        finally:
            con.close()
    except Exception as exc:  # noqa: BLE001 — any failure means "we can't tell"
        print(f"Warehouse unreachable ({exc}) — reporting figures as null.")
        return None, None

    return int(rows), last_ingest.isoformat() if last_ingest is not None else None


def build_status() -> dict[str, Any]:
    rows, last_ingest_at = query_warehouse()
    tests_passed, tests_total = read_dbt_test_results()

    return {
        "project": PROJECT_NAME,
        "generated_at": _utc_now_iso(),
        "last_ingest_at": last_ingest_at,
        "rows_in_warehouse": rows,
        "dbt_tests_passed": tests_passed,
        "dbt_tests_total": tests_total,
        # Set by the workflow from `job.status`; "unknown" when run by hand.
        "last_run_conclusion": os.environ.get("RUN_CONCLUSION", "unknown"),
    }


def main() -> int:
    status = build_status()
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATUS_PATH.write_text(json.dumps(status, indent=2) + "\n")
    print(f"Wrote {STATUS_PATH.relative_to(PROJECT_ROOT)}:")
    print(json.dumps(status, indent=2))
    # Always exit 0: this step reports on the run, it must never *become* the
    # reason the run is red.
    return 0


if __name__ == "__main__":
    sys.exit(main())
