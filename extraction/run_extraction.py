"""
Extraction pipeline CLI.

USAGE EXAMPLES
──────────────
Single city / source:
  python extraction/run_extraction.py --source idealista --city madrid --operation sale

Multiple cities (comma-separated):
  python extraction/run_extraction.py --source idealista --cities madrid,barcelona,valencia

All cities, one source:
  python extraction/run_extraction.py --source idealista --all-cities

All cities, all sources (full nightly run):
  python extraction/run_extraction.py --all

Dry-run (no writes to MotherDuck):
  python extraction/run_extraction.py --source idealista --city madrid --dry-run

VSCode F5: uses .vscode/launch.json → "Run Extraction (Madrid dry-run)"
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import typer

# Make sure project root is on PYTHONPATH when run as a script
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.aux_logger import configure_logger, get_logger

from extraction.config import SCRAPING_CITIES
from extraction.loaders.motherduck_loader import MotherDuckLoader
from extraction.scrapers.fotocasa import FotocasaScraper
from extraction.scrapers.idealista import IdealistaScraper

# ── Logging ───────────────────────────────────────────────────────────────────
configure_logger()
logger = get_logger("run_extraction")

# ── Registry: add new scrapers here only ─────────────────────────────────────
SCRAPER_REGISTRY: dict[str, type] = {
    "idealista": IdealistaScraper,
    "fotocasa":  FotocasaScraper,
}
VALID_SOURCES = list(SCRAPER_REGISTRY.keys())
VALID_OPERATIONS = ["sale", "rent"]

app = typer.Typer(pretty_exceptions_enable=False, add_completion=False)


@app.command()
def main(
    # ── Source selection ──────────────────────────────────────────────────────
    source: Optional[str] = typer.Option(
        None, "--source", "-s",
        help=f"Portal to scrape. Options: {', '.join(VALID_SOURCES)}"
    ),
    all_sources: bool = typer.Option(
        False, "--all",
        help="Run ALL sources × ALL cities × ALL operations (full nightly pipeline)."
    ),
    # ── City selection ────────────────────────────────────────────────────────
    city: Optional[str] = typer.Option(
        None, "--city", "-c",
        help="Single city to scrape. Mutually exclusive with --cities / --all-cities."
    ),
    cities: Optional[str] = typer.Option(
        None, "--cities",
        help="Comma-separated city list: madrid,barcelona,valencia"
    ),
    all_cities: bool = typer.Option(
        False, "--all-cities",
        help=f"Scrape all configured cities: {', '.join(SCRAPING_CITIES)}"
    ),
    # ── Operation ─────────────────────────────────────────────────────────────
    operation: str = typer.Option(
        "sale", "--operation", "-o",
        help="'sale' or 'rent'  (ignored when --all is used)"
    ),
    # ── Misc ──────────────────────────────────────────────────────────────────
    dry_run: bool = typer.Option(
        False, "--dry-run",
        help="Parse and validate, but do NOT write to MotherDuck."
    ),
) -> None:
    """Extract real estate listings → validate → load into MotherDuck (Bronze layer)."""

    # ── Build the job matrix: list of (source, city, operation) tuples ───────
    jobs: list[tuple[str, str, str]] = []

    if all_sources:
        # Full pipeline: every source × every city × sale + rent
        for src in VALID_SOURCES:
            for c in SCRAPING_CITIES:
                for op in VALID_OPERATIONS:
                    jobs.append((src, c, op))

    else:
        # Resolve source
        if not source:
            typer.echo("Error: --source is required unless you use --all.", err=True)
            raise typer.Exit(1)
        if source not in SCRAPER_REGISTRY:
            typer.echo(f"Unknown source {source!r}. Choose from: {', '.join(VALID_SOURCES)}", err=True)
            raise typer.Exit(1)

        # Resolve city list
        if all_cities:
            city_list = SCRAPING_CITIES
        elif cities:
            city_list = [c.strip().lower() for c in cities.split(",") if c.strip()]
        elif city:
            city_list = [city.lower().strip()]
        else:
            # Default: madrid only (safe for dev)
            logger.warning("No city specified — defaulting to madrid. Use --all-cities for everything.")
            city_list = ["madrid"]

        # Resolve operation
        if operation not in VALID_OPERATIONS:
            typer.echo(f"--operation must be 'sale' or 'rent', got {operation!r}", err=True)
            raise typer.Exit(1)

        for c in city_list:
            jobs.append((source, c, operation))

    # ── Run ───────────────────────────────────────────────────────────────────
    if not jobs:
        logger.warning("No jobs to run.")
        raise typer.Exit(0)

    run_id = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    total_rows = 0
    failed_jobs: list[tuple[str, str, str]] = []

    logger.info("=" * 65)
    logger.info("Run ID   : %s", run_id)
    logger.info("Jobs     : %d  (source × city × operation)", len(jobs))
    logger.info("Dry run  : %s", dry_run)
    logger.info("=" * 65)

    with MotherDuckLoader(run_id=run_id, dry_run=dry_run) as loader:
        for i, (src, cty, op) in enumerate(jobs, 1):
            logger.info("── Job %d/%d  source=%s  city=%s  op=%s ──", i, len(jobs), src, cty, op)

            scraper_cls = SCRAPER_REGISTRY[src]
            scraper = scraper_cls(province=cty)

            try:
                listings = scraper.scrape(operation=op)
            except Exception as exc:
                logger.error("Job failed (source=%s city=%s op=%s): %s", src, cty, op, exc)
                failed_jobs.append((src, cty, op))
                continue

            if not listings:
                logger.warning("No valid listings for source=%s city=%s op=%s", src, cty, op)
                continue

            try:
                rows = loader.load(listings, source_name=src)
                total_rows += rows
            except Exception as exc:
                logger.error("Load failed: %s", exc)
                failed_jobs.append((src, cty, op))

    # ── Summary ───────────────────────────────────────────────────────────────
    logger.info("=" * 65)
    logger.info("DONE  — total rows written: %d", total_rows)
    if failed_jobs:
        logger.warning("Failed jobs (%d):", len(failed_jobs))
        for src, cty, op in failed_jobs:
            logger.warning("  ✗  source=%s  city=%s  op=%s", src, cty, op)
    else:
        logger.info("All jobs completed successfully.")
    logger.info("Next step: cd transform && dbt run")

    if failed_jobs:
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
