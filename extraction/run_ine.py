"""
INE market-context ingestion CLI.

Fetches the official INE house-price index (IPV) and loads it into
raw.ine_hpi. Free, keyless and independent of Scrapfly — so it keeps the
warehouse fresh even while the listing scraper is parked on API credits.

USAGE
─────
  python -m extraction.run_ine                # fetch + load
  python -m extraction.run_ine --dry-run      # fetch + validate, no writes
"""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import sys

import typer

sys.path.insert(0, str(Path(__file__).parent.parent))

from extraction.loaders.motherduck_loader import MotherDuckLoader
from extraction.sources.ine_hpi import fetch_ine_hpi
from shared.aux_logger import configure_logger, get_logger

configure_logger()
logger = get_logger("run_ine")

app = typer.Typer(pretty_exceptions_enable=False, add_completion=False)


@app.command()
def main(
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Fetch and validate, but do NOT write to MotherDuck."
    ),
) -> None:
    """Fetch the INE house-price index → validate → load into raw.ine_hpi."""
    run_id = datetime.now(tz=UTC).strftime("%Y-%m-%d_%H:%M:%S")
    logger.info("INE ingestion — run_id=%s  dry_run=%s", run_id, dry_run)

    records = fetch_ine_hpi()
    if not records:
        logger.warning("No INE records fetched — nothing to load.")
        raise typer.Exit(1)

    with MotherDuckLoader(run_id=run_id, dry_run=dry_run) as loader:
        rows = loader.load_ine_hpi(records)

    logger.info("DONE — %d INE rows written. Next: cd transform && dbt build", rows)


if __name__ == "__main__":
    app()
