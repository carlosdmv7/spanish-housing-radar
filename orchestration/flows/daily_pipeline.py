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


# Prefect Cloud rejects any single log message over 25 000 characters with a 422,
# and a full `dbt build` writes far more than that — so shipping stdout whole meant
# the API silently dropped the entire message and the run's history in the Cloud UI
# was empty for exactly the task worth reading. The tail is what matters anyway:
# dbt puts the failures and the PASS/ERROR summary at the end.
_MAX_LOG_CHARS = 20_000


def _tail(text: str, limit: int = _MAX_LOG_CHARS) -> str:
    if len(text) <= limit:
        return text
    dropped = len(text) - limit
    return f"[… {dropped:,} earlier characters omitted …]\n{text[-limit:]}"


def _run(cmd: list[str], cwd: Path, extra_env: dict[str, str] | None = None) -> None:
    logger = get_run_logger()
    logger.info("$ %s", " ".join(cmd))

    env = {**os.environ, **(extra_env or {})}
    result = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, check=False)

    if result.stdout:
        logger.info(_tail(result.stdout))
    if result.returncode != 0:
        logger.error(_tail(result.stderr))
        raise RuntimeError(f"Command failed (exit {result.returncode}): {' '.join(cmd)}")


@task(name="ingest-ine", retries=2, retry_delay_seconds=[15, 45], log_prints=True)
def ingest_ine() -> None:
    """Fetch the official INE house-price index into raw.ine_hpi (free, no credits)."""
    _run(
        [PYTHON, "-m", "extraction.run_ine"],
        cwd=PROJECT_ROOT,
    )


# Scrapfly bills a flat 25 credits per search page, so `--all` — every source ×
# every city × sale and rent — is 40 requests and 1 000 credits, the entire free
# monthly allowance, in a single run. On a weekly cron that overspends the budget
# four times over, and the first evidence would be a scraper that silently returns
# nothing for three weeks out of four.
#
# So the scheduled scrape is scoped, and scoped narrowly on purpose: depth in one
# city produces barrio-level benchmarks, while one page each across ten cities
# produces city-level fallbacks nobody can act on. Widen it by setting the env
# vars, with the credit maths in front of you.
SCRAPE_SOURCE = os.getenv("SCRAPE_SOURCE", "idealista")
SCRAPE_CITIES = os.getenv("SCRAPE_CITIES", "valencia")
SCRAPE_OPERATIONS = [
    op.strip()
    for op in os.getenv("SCRAPE_OPERATIONS", "sale,rent").split(",")
    if op.strip()
]


@task(name="extract-listings", retries=2, retry_delay_seconds=[15, 45], log_prints=True)
def extract_listings() -> None:
    """Scrape the configured source × cities × operations into raw.*."""
    for operation in SCRAPE_OPERATIONS:
        _run(
            [
                PYTHON, "extraction/run_extraction.py",
                "--source", SCRAPE_SOURCE,
                "--cities", SCRAPE_CITIES,
                "--operation", operation,
            ],
            cwd=PROJECT_ROOT,
        )


@task(name="dbt-build", retries=1, retry_delay_seconds=10, log_prints=True)
def dbt_build(target: str = "prod") -> None:
    """Run the medallion build (bronze → silver → gold) + dbt tests."""
    # --project-dir from the repo root, never cwd=transform. dbt stores seed
    # paths in transform/target/partial_parse.msgpack relative to the invocation
    # directory, so mixing the two forms makes a cache written by one break the
    # other — and it breaks seeds only, which means the build reports success for
    # every model and fails at the three CSVs. Same form as the Makefile and CI.
    _run(
        [DBT, "build", "--project-dir", str(TRANSFORM_DIR), "--target", target],
        cwd=PROJECT_ROOT,
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
        logger.info(
            "Scraping %s × [%s] × %s. At 25 credits per search page this run costs "
            "≈%d credits per page of depth.",
            SCRAPE_SOURCE, SCRAPE_CITIES, SCRAPE_OPERATIONS,
            25 * len(SCRAPE_CITIES.split(",")) * len(SCRAPE_OPERATIONS),
        )
        extract_listings()
    else:
        logger.info(
            "Scrapfly disabled (SCRAPFLY_ENABLED != true) — skipping listing scrape. "
            "Refreshing INE market context + rebuilding dbt only."
        )

    dbt_build(target=dbt_target)


if __name__ == "__main__":
    daily_pipeline()
