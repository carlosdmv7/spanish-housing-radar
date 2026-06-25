"""
Daily pipeline: extract → dbt build, orchestrated with Prefect.

Run once, ad hoc:
    python -m orchestration.flows.daily_pipeline

Run on a schedule:
    See .github/workflows/daily_pipeline.yml — a GitHub Actions cron triggers
    this flow daily; Prefect itself only provides task structure (retries,
    logging, dependency ordering), not the scheduler.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

from dotenv import load_dotenv
from prefect import flow, get_run_logger, task

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TRANSFORM_DIR = PROJECT_ROOT / "transform"
PYTHON = sys.executable
DBT = str(Path(sys.executable).parent / "dbt")

load_dotenv(PROJECT_ROOT / ".env")


def _run(cmd: list[str], cwd: Path, extra_env: dict[str, str] | None = None) -> None:
    logger = get_run_logger()
    logger.info("$ %s", " ".join(cmd))

    env = {**os.environ, **(extra_env or {})}
    result = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, check=False)

    if result.stdout:
        logger.info(result.stdout)
    if result.returncode != 0:
        logger.error(result.stderr)
        raise RuntimeError(f"Command failed (exit {result.returncode}): {' '.join(cmd)}")


@task(name="extract-all-sources", retries=2, retry_delay_seconds=[15, 45], log_prints=True)
def extract_all() -> None:
    """Scrape every configured source × city × operation into raw.*."""
    _run(
        [PYTHON, "extraction/run_extraction.py", "--all"],
        cwd=PROJECT_ROOT,
    )


@task(name="dbt-build", retries=1, retry_delay_seconds=10, log_prints=True)
def dbt_build(target: str = "prod") -> None:
    """Run the medallion build (bronze → silver → gold) + dbt tests."""
    _run(
        [DBT, "build", "--target", target],
        cwd=TRANSFORM_DIR,
        # transform/profiles.yml resolves relative to DBT_PROFILES_DIR; pin it
        # absolute here since this flow's cwd for dbt is transform/ itself.
        extra_env={"DBT_PROFILES_DIR": str(TRANSFORM_DIR)},
    )


@flow(name="spanish-housing-radar-daily")
def daily_pipeline(dbt_target: str = "prod") -> None:
    """Nightly pipeline: scrape fresh listings, then rebuild the medallion."""
    extract_all()
    dbt_build(target=dbt_target)


if __name__ == "__main__":
    daily_pipeline()
