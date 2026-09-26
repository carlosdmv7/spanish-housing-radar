"""
Serve the refresh deployment from a GitHub Actions runner, for one pass.

    uv run python -m orchestration.gha_runner

Prefect Cloud holds the `spanish-housing-radar-daily/refresh` deployment: its
schedule (Mondays 05:00 UTC), its parameters and its run history. This module
lends it a machine. `.github/workflows/pipeline.yml` wakes up hourly and calls
it:

1. Register the deployment from the code below. It is a *served* deployment, so
   its definition is always what is on main, and it needs no work pool.
2. Ask Cloud whether any of its runs is due: the scheduled one, or one started
   by hand from the Prefect UI. None: exit in seconds.
3. Otherwise start a Runner for a single pass, which executes the due runs and
   waits for them, then read back how each ended. A run that did not complete
   fails the job, so GitHub still emails about it, and the workflow's status
   steps record the conclusion in docs/status.json.

Why a borrowed runner: Prefect Cloud's free tier has no hybrid work pools, and
its 500 serverless minutes a month are shared with the sibling
job-market-intelligence pipeline, which alone needs ~300. Actions minutes on a
public repository are free.
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
import os
from pathlib import Path
import sys
from uuid import UUID

from prefect.client.orchestration import get_client
from prefect.client.schemas.objects import StateType
from prefect.runner import Runner

from orchestration.flows.pipeline import run_pipeline

DEPLOYMENT = "refresh"
SCHEDULE = "0 5 * * 1"  # Mondays 05:00 UTC
# The runner prefetches runs due this soon; the check below uses the same window.
PREFETCH = timedelta(seconds=10)


def set_output(**values: str) -> None:
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with Path(path).open("a", encoding="utf-8") as fh:
            fh.writelines(f"{k}={v}\n" for k, v in values.items())


async def serve_once() -> int:
    runner = Runner(
        name=f"github-actions-{os.environ.get('GITHUB_RUN_ID', 'local')}",
        limit=1,  # one refresh at a time: they write the same warehouse
        prefetch_seconds=PREFETCH.total_seconds(),
        # A long-lived `serve` pauses its schedules when it stops, so nothing
        # piles up while no one is serving. This runner stops after every pass
        # by design; pausing would switch the schedule off an hour after it was
        # registered, and it did, on the first run from Actions.
        pause_on_shutdown=False,
    )
    deployment_id: UUID = await runner.aadd_flow(
        run_pipeline,
        name=DEPLOYMENT,
        cron=SCHEDULE,
        paused=False,  # re-registering un-pauses: the schedule lives in code
        tags=["spanish-housing-radar"],
        description=(
            "Ingest the INE house-price index, scrape València listings when "
            "SCRAPFLY_ENABLED is true (25 credits a search page), then rebuild and test "
            "the dbt medallion on MotherDuck. Served from an hourly GitHub Actions job: "
            "a run shows as Late until that job picks it up."
        ),
    )

    async with get_client() as client:
        due = await client.get_scheduled_flow_runs_for_deployments(
            [deployment_id], scheduled_before=datetime.now(UTC) + PREFETCH
        )
    if not due:
        print("Nothing due.")
        set_output(ran="false")
        return 0

    # Said before the run, not after: if this process dies mid-run, the
    # workflow still knows a run happened and records it as failed.
    set_output(ran="true")
    ids = [run.id for run in due]
    print(f"{len(ids)} run(s) due: {', '.join(map(str, ids))}")
    await runner.start(run_once=True)

    async with get_client() as client:
        states = {run_id: (await client.read_flow_run(run_id)).state for run_id in ids}
    for run_id, state in states.items():
        print(f"{run_id}: {state.type.value if state else 'no state'}")
    # Still scheduled (more were due than one pass takes): the next hour runs it.
    finished = [s for s in states.values() if s and s.type != StateType.SCHEDULED]
    ok = all(s.type == StateType.COMPLETED for s in finished)
    set_output(conclusion="success" if ok else "failure")
    return 0 if ok else 1


def main() -> int:
    return asyncio.run(serve_once())


if __name__ == "__main__":
    sys.exit(main())
