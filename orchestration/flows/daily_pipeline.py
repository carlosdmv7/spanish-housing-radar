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


@task(name="ingest-ine", retries=2, retry_delay_seconds=[15, 45], log_prints=True)
def ingest_ine() -> None:
    """Fetch the official INE house-price index into raw.ine_hpi (free, no credits)."""
    _run(
        [PYTHON, "-m", "extraction.run_ine"],
        cwd=PROJECT_ROOT,
    )


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
def daily_pipeline(dbt_target: str = "prod", scrape: bool | None = None) -> None:
    """
    Refresh pipeline: ingest official market data (always, free), scrape fresh
    listings (only when Scrapfly credits are available), then rebuild the medallion.

    `scrape` defaults to the SCRAPFLY_ENABLED env var. This is what un-parks the
    project: even with the listing scraper switched off, the free INE feed + dbt
    build keep the warehouse and the live app fresh instead of frozen.
    """
    logger = get_run_logger()

    # INE is a nice-to-have context feed — never let it block the rebuild.
    try:
        ingest_ine()
    except Exception as exc:
        logger.warning("INE ingestion failed (continuing to dbt build): %s", exc)

    if scrape is None:
        scrape = os.getenv("SCRAPFLY_ENABLED", "false").lower() == "true"

    if scrape:
        extract_all()
    else:
        logger.info(
            "Scrapfly disabled (SCRAPFLY_ENABLED != true) — skipping listing scrape. "
            "Refreshing INE market context + rebuilding dbt only."
        )

    dbt_build(target=dbt_target)


if __name__ == "__main__":
    daily_pipeline()
