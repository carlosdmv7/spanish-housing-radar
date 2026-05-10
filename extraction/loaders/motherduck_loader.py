# extraction/loaders/motherduck_loader.py
"""
MotherDuck loader — receives validated RawListing objects and upserts
them into the Bronze raw schema using DuckDB's Python client.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import duckdb
import pandas as pd

from extraction.config import MOTHERDUCK_DSN, RAW_TABLE_MAP
from extraction.schemas.raw_listings import RawListing

logger = logging.getLogger(__name__)

# DDL executed once at startup to ensure the raw schema and tables exist
_CREATE_SCHEMA_SQL = "CREATE SCHEMA IF NOT EXISTS raw;"

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS {table} (
    source_id           VARCHAR,
    source_name         VARCHAR,
    raw_price_eur       DOUBLE,
    raw_operation_type  VARCHAR,
    raw_size_sqm        DOUBLE,
    raw_rooms           INTEGER,
    raw_bathrooms       INTEGER,
    raw_property_type   VARCHAR,
    raw_lat             DOUBLE,
    raw_lon             DOUBLE,
    raw_municipality    VARCHAR,
    raw_district        VARCHAR,
    raw_neighborhood    VARCHAR,
    _loaded_at          TIMESTAMPTZ,
    _run_id             VARCHAR,
    PRIMARY KEY (source_name, source_id)
);
"""

_UPSERT_SQL = """
INSERT OR REPLACE INTO {table}
SELECT
    source_id, source_name, raw_price_eur, raw_operation_type,
    raw_size_sqm, raw_rooms, raw_bathrooms, raw_property_type,
    raw_lat, raw_lon, raw_municipality, raw_district, raw_neighborhood,
    _loaded_at, _run_id
FROM df;
"""


class MotherDuckLoader:
    """Loads a list of RawListing objects into the MotherDuck Bronze layer."""

    def __init__(self, run_id: str = "manual", dry_run: bool = False) -> None:
        self.run_id = run_id
        self.dry_run = dry_run
        self._conn: duckdb.DuckDBPyConnection | None = None

    # ── Context manager ───────────────────────────────────────────────────────

    def __enter__(self) -> "MotherDuckLoader":
        if not self.dry_run:
            logger.info("Connecting to MotherDuck…")
            self._conn = duckdb.connect(MOTHERDUCK_DSN)
            self._conn.execute(_CREATE_SCHEMA_SQL)
        return self

    def __exit__(self, *_) -> None:
        if self._conn:
            self._conn.close()

    # ── Public ────────────────────────────────────────────────────────────────

    def load(self, listings: list[RawListing], source_name: str) -> int:
        """
        Upsert listings into the correct raw table.
        Returns the number of rows written (0 in dry-run mode).
        """
        if not listings:
            logger.warning("No listings to load for source=%s", source_name)
            return 0

        table = RAW_TABLE_MAP.get(source_name)
        if not table:
            raise ValueError(f"Unknown source: {source_name!r}. Add it to RAW_TABLE_MAP.")

        df = self._to_dataframe(listings)

        if self.dry_run:
            logger.info("[DRY RUN] Would load %d rows into %s", len(df), table)
            print(df.head(3).to_string())
            return 0

        # Register df as a DuckDB relation so the UPSERT SQL can reference it
        self._conn.register("df", df)  # type: ignore[union-attr]
        self._conn.execute(_CREATE_TABLE_SQL.format(table=table))
        self._conn.execute(_UPSERT_SQL.format(table=table))
        self._conn.unregister("df")

        logger.info("Loaded %d rows → %s", len(df), table)
        return len(df)

    # ── Private ───────────────────────────────────────────────────────────────

    def _to_dataframe(self, listings: list[RawListing]) -> pd.DataFrame:
        now = datetime.now(tz=timezone.utc)
        rows = []
        for l in listings:
            rows.append({
                "source_id":           l.source_id,
                "source_name":         l.source_name,
                "raw_price_eur":       l.raw_price_eur,
                "raw_operation_type":  l.raw_operation_type,
                "raw_size_sqm":        l.raw_size_sqm,
                "raw_rooms":           l.raw_rooms,
                "raw_bathrooms":       l.raw_bathrooms,
                "raw_property_type":   l.raw_property_type,
                "raw_lat":             l.raw_lat,
                "raw_lon":             l.raw_lon,
                "raw_municipality":    l.raw_municipality,
                "raw_district":        l.raw_district,
                "raw_neighborhood":    l.raw_neighborhood,
                "_loaded_at":          now,
                "_run_id":             self.run_id,
            })
        return pd.DataFrame(rows)
