"""
INE district-income ingestion CLI.

Fetches the Atlas de Distribución de Renta de los Hogares (ADRH) and loads
district-level income into raw.ine_income. Free, keyless, and independent of
Scrapfly — like the IPV feed, it keeps the warehouse gaining information while
the listing scraper is out of credits.

The data is annual, so this is not a daily job. Run it when INE publishes a new
reference year.

USAGE
─────
  python -m extraction.run_ine_income               # fetch + load
  python -m extraction.run_ine_income --dry-run     # fetch + validate, no writes
"""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import sys

import typer

sys.path.insert(0, str(Path(__file__).parent.parent))

from extraction.config import INE_MUNICIPALITY_CODES
from extraction.loaders.motherduck_loader import MotherDuckLoader
from extraction.sources.ine_income import fetch_ine_income
from shared.aux_logger import configure_logger, get_logger

configure_logger()
logger = get_logger("run_ine_income")

app = typer.Typer(pretty_exceptions_enable=False, add_completion=False)


@app.command()
def main(
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Fetch and validate, but do NOT write to MotherDuck."
    ),
) -> None:
    """Fetch INE ADRH district income → validate → load into raw.ine_income."""
    run_id = datetime.now(tz=UTC).strftime("%Y-%m-%d_%H:%M:%S")
    codes = set(INE_MUNICIPALITY_CODES.values())

    logger.info("=" * 65)
    logger.info("Run ID   : %s", run_id)
    logger.info("Cities   : %s", ", ".join(sorted(INE_MUNICIPALITY_CODES)))
    logger.info("Dry run  : %s", dry_run)
    logger.info("=" * 65)

    records = fetch_ine_income(codes)
    if not records:
        logger.warning("No income records returned — nothing to write.")
        raise typer.Exit(code=0)

    with MotherDuckLoader(run_id=run_id, dry_run=dry_run) as loader:
        written = loader.load_ine_income(records)

    logger.info("=" * 65)
    logger.info("DONE  — rows written: %d", written)


if __name__ == "__main__":
    app()
