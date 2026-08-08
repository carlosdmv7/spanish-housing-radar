"""
MotherDuck loader — upserts validated RawListing objects into Bronze raw tables.

Each source portal has its own table (raw.idealista_listings, raw.fotocasa_listings)
with identical schemas, so dbt can UNION ALL them cleanly in the Silver layer.

INSERT OR REPLACE makes every run fully idempotent — safe to re-run anytime.
"""
from __future__ import annotations

from datetime import UTC, datetime
import logging

import duckdb
import pandas as pd

from extraction.config import INE_HPI_RAW_TABLE, MOTHERDUCK_DSN, RAW_TABLE_MAP
from extraction.schemas.ine_records import IneHpiRecord
from extraction.schemas.raw_listings import RawListing

logger = logging.getLogger(__name__)

_CREATE_SCHEMA_SQL = "CREATE SCHEMA IF NOT EXISTS raw;"

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS {table} (
    source_id           VARCHAR        NOT NULL,
    source_name         VARCHAR        NOT NULL,
    raw_url             VARCHAR,
    raw_price_eur       DOUBLE         NOT NULL,
    raw_operation_type  VARCHAR        NOT NULL,
    raw_size_sqm        DOUBLE         NOT NULL,
    raw_rooms           INTEGER,
    raw_bathrooms       INTEGER,
    raw_property_type   VARCHAR        NOT NULL,
    raw_lat             DOUBLE,
    raw_lon             DOUBLE,
    raw_municipality    VARCHAR        NOT NULL,
    raw_district        VARCHAR,
    raw_neighborhood    VARCHAR,
    -- The listing title exactly as the portal wrote it. The municipality /
    -- district / neighborhood columns above are the output of a text heuristic,
    -- and a heuristic that discards its own input cannot be corrected: when the
    -- parser was found to be putting street names and house numbers in
    -- raw_neighborhood, there was no way to re-derive the 646 existing rows
    -- short of re-scraping them. Keeping the source text makes the parse
    -- reproducible and every future parser fix retroactive.
    raw_title           VARCHAR,
    _loaded_at          TIMESTAMPTZ    NOT NULL,
    _run_id             VARCHAR        NOT NULL,
    PRIMARY KEY (source_name, source_id)
);
"""

_UPSERT_SQL = """
INSERT OR REPLACE INTO {table}
    SELECT
        source_id, source_name, raw_url,
        raw_price_eur, raw_operation_type,
        raw_size_sqm, raw_rooms, raw_bathrooms,
        raw_property_type, raw_lat, raw_lon,
        raw_municipality, raw_district, raw_neighborhood, raw_title,
        _loaded_at, _run_id
    FROM df;
"""


class MotherDuckLoader:
    """
    Context-manager loader. Opens one MotherDuck connection for the
    whole extraction run and closes it on exit.

    Usage:
        with MotherDuckLoader(run_id="20260510T060000Z") as loader:
            loader.load(idealista_listings, source_name="idealista")
            loader.load(fotocasa_listings,  source_name="fotocasa")
    """

    def __init__(self, run_id: str = "manual", dry_run: bool = False) -> None:
        self.run_id = run_id
        self.dry_run = dry_run
        self._conn: duckdb.DuckDBPyConnection | None = None

    def __enter__(self) -> MotherDuckLoader:
        if not self.dry_run:
            logger.info("Connecting to MotherDuck…")
            self._conn = duckdb.connect(MOTHERDUCK_DSN)
            self._conn.execute(_CREATE_SCHEMA_SQL)
            logger.info("Connected. Schema 'raw' ensured.")
        return self

    def __exit__(self, *_) -> None:
        if self._conn:
            self._conn.close()
            logger.info("MotherDuck connection closed.")

    def load(self, listings: list[RawListing], source_name: str) -> int:
        """
        Upsert listings into the correct raw table.
        Returns rows written (0 in dry-run mode).
        """
        if not listings:
            logger.warning("[loader] No listings for source=%s — nothing to write.", source_name)
            return 0

        table = RAW_TABLE_MAP.get(source_name)
        if not table:
            raise ValueError(
                f"Unknown source {source_name!r}. Add it to RAW_TABLE_MAP in config.py."
            )

        df = self._to_dataframe(listings)

        if self.dry_run:
            logger.info("[loader][DRY RUN] Would write %d rows → %s", len(df), table)
            print(df.head(5).to_string(index=False))
            return 0

        if self._conn is None:
            raise RuntimeError("Loader not initialised — use as a context manager.")

        self._conn.register("df", df)
        self._conn.execute(_CREATE_TABLE_SQL.format(table=table))
        self._conn.execute(_UPSERT_SQL.format(table=table))
        self._conn.unregister("df")

        logger.info("[loader] ✓  %d rows → %s", len(df), table)
        return len(df)

    # ── INE house-price index ─────────────────────────────────────────────────

    _CREATE_INE_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS {table} (
        series_cod   VARCHAR      NOT NULL,
        region       VARCHAR      NOT NULL,
        housing_type VARCHAR      NOT NULL,
        metric       VARCHAR      NOT NULL,
        period_date  DATE         NOT NULL,
        year         INTEGER      NOT NULL,
        value        DOUBLE       NOT NULL,
        _loaded_at   TIMESTAMPTZ  NOT NULL,
        _run_id      VARCHAR      NOT NULL,
        PRIMARY KEY (series_cod, period_date)
    );
    """

    _UPSERT_INE_SQL = """
    INSERT OR REPLACE INTO {table}
        SELECT series_cod, region, housing_type, metric,
               period_date, year, value, _loaded_at, _run_id
        FROM df;
    """

    def load_ine_hpi(self, records: list[IneHpiRecord]) -> int:
        """Upsert INE IPV records into raw.ine_hpi. Idempotent on (series, quarter)."""
        if not records:
            logger.warning("[loader] No INE records — nothing to write.")
            return 0

        now = datetime.now(tz=UTC)
        df = pd.DataFrame([
            {**r.model_dump(), "_loaded_at": now, "_run_id": self.run_id}
            for r in records
        ])

        if self.dry_run:
            logger.info("[loader][DRY RUN] Would write %d rows → %s", len(df), INE_HPI_RAW_TABLE)
            print(df.head(5).to_string(index=False))
            return 0

        if self._conn is None:
            raise RuntimeError("Loader not initialised — use as a context manager.")

        self._conn.register("df", df)
        self._conn.execute(self._CREATE_INE_TABLE_SQL.format(table=INE_HPI_RAW_TABLE))
        self._conn.execute(self._UPSERT_INE_SQL.format(table=INE_HPI_RAW_TABLE))
        self._conn.unregister("df")

        logger.info("[loader] ✓  %d rows → %s", len(df), INE_HPI_RAW_TABLE)
        return len(df)

    def _to_dataframe(self, listings: list[RawListing]) -> pd.DataFrame:
        return pd.DataFrame([
            {
                "source_id":          listing.source_id,
                "source_name":        listing.source_name,
                "raw_url":            listing.raw_url,
                "raw_price_eur":      listing.raw_price_eur,
                "raw_operation_type": listing.raw_operation_type,
                "raw_size_sqm":       listing.raw_size_sqm,
                "raw_rooms":          listing.raw_rooms,
                "raw_bathrooms":      listing.raw_bathrooms,
                "raw_property_type":  listing.raw_property_type,
                "raw_lat":            listing.raw_lat,
                "raw_lon":            listing.raw_lon,
                "raw_municipality":   listing.raw_municipality,
                "raw_district":       listing.raw_district,
                "raw_neighborhood":   listing.raw_neighborhood,
                "_loaded_at":         datetime.now(tz=UTC),
                "_run_id":            self.run_id,
            }
            for listing in listings
        ])
