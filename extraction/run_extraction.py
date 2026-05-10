# extraction/run_extraction.py
"""
CLI entrypoint for the extraction pipeline.

Usage examples:
    python extraction/run_extraction.py --source idealista --province madrid
    python extraction/run_extraction.py --source fotocasa  --province barcelona --operation rent
    python extraction/run_extraction.py --source idealista --province madrid --dry-run

VSCode F5: uses the "Run Extraction (Madrid)" launch config in .vscode/launch.json
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import typer

# Ensure project root is on PYTHONPATH when running as a script
sys.path.insert(0, str(Path(__file__).parent.parent))

from extraction.config import VALID_PROVINCES
from extraction.loaders.motherduck_loader import MotherDuckLoader
from extraction.scrapers.idealista import IdealistaScraper
from extraction.scrapers.fotocasa import FotocasaScraper

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("run_extraction")

# ── Scraper registry — add new sources here only ──────────────────────────────
SCRAPER_REGISTRY = {
    "idealista": IdealistaScraper,
    # "fotocasa":  FotocasaScraper,
}

app = typer.Typer(pretty_exceptions_enable=False)


@app.command()
def main(
    source: str = typer.Option(
        ..., "--source", "-s",
        help=f"Data source to extract. Options: {', '.join(SCRAPER_REGISTRY)}"
    ),
    province: str = typer.Option(
        "madrid", "--province", "-p",
        help=f"Spanish province. Options: {', '.join(VALID_PROVINCES)}"
    ),
    operation: str = typer.Option(
        "sale", "--operation", "-o",
        help="Operation type: 'sale' or 'rent'"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run",
        help="Parse and validate without writing to MotherDuck"
    ),
) -> None:
    """Extract real estate listings and load them into MotherDuck (Bronze layer)."""

    # ── Validate inputs ───────────────────────────────────────────────────────
    if source not in SCRAPER_REGISTRY:
        typer.echo(f"Error: unknown source '{source}'. Choose from: {', '.join(SCRAPER_REGISTRY)}", err=True)
        raise typer.Exit(1)

    if province not in VALID_PROVINCES:
        typer.echo(f"Warning: '{province}' is not in VALID_PROVINCES list. Proceeding anyway.", err=True)

    if operation not in ("sale", "rent"):
        typer.echo("Error: --operation must be 'sale' or 'rent'", err=True)
        raise typer.Exit(1)

    run_id = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    logger.info("=" * 60)
    logger.info("Extraction run  : %s", run_id)
    logger.info("Source          : %s", source)
    logger.info("Province        : %s", province)
    logger.info("Operation       : %s", operation)
    logger.info("Dry run         : %s", dry_run)
    logger.info("=" * 60)

    # ── Scrape ────────────────────────────────────────────────────────────────
    scraper_cls = SCRAPER_REGISTRY[source]
    scraper = scraper_cls(province=province)

    try:
        listings = scraper.scrape(operation=operation)
    except Exception as exc:
        logger.exception("Extraction failed: %s", exc)
        raise typer.Exit(1)

    logger.info("Scraped %d valid listings", len(listings))

    if not listings:
        logger.warning("No listings found — nothing to load.")
        raise typer.Exit(0)

    # ── Load ──────────────────────────────────────────────────────────────────
    with MotherDuckLoader(run_id=run_id, dry_run=dry_run) as loader:
        rows_loaded = loader.load(listings, source_name=source)

    logger.info("Done. Rows written to MotherDuck: %d", rows_loaded)
    logger.info("Next step: cd transform && dbt run --select bronze+")


if __name__ == "__main__":
    app()
