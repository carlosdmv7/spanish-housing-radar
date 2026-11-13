"""
Card attributes (ADR-0012) through validation and into a raw table.

The loader test runs the real `MotherDuckLoader.load` against an in-memory
DuckDB holding a table in the shape prod has today (raw_title appended last,
none of the card-attribute columns), so it exercises the migration path the
next scheduled run will take — no MotherDuck involved.
"""
from __future__ import annotations

import duckdb
import pytest

from extraction.loaders.motherduck_loader import MotherDuckLoader
from extraction.schemas.raw_listings import RawListing

_BASE = {
    "source_id": "1",
    "source_name": "idealista",
    "raw_price_eur": 300_000,
    "raw_operation_type": "sale",
    "raw_size_sqm": 100,
    "raw_property_type": "apartment",
    "raw_municipality": "madrid",
}


class TestRawListingAttributes:
    def test_all_attributes_default_to_unknown(self):
        listing = RawListing(**_BASE)
        assert listing.raw_floor is None
        assert listing.raw_is_exterior is None
        assert listing.raw_has_lift is None
        assert listing.raw_garage is None

    @pytest.mark.parametrize("field, value", [
        ("raw_floor", 250),
        ("raw_floor", -9),
        ("raw_price_drop_pct", 0),
        ("raw_price_drop_pct", 140),
        ("raw_previous_price_eur", 0),
        ("raw_garage_price_eur", -5),
    ])
    def test_an_implausible_attribute_becomes_unknown_and_keeps_the_listing(self, field, value):
        listing = RawListing(**_BASE, **{field: value})
        assert getattr(listing, field) is None
        assert listing.raw_price_eur == 300_000

    def test_plausible_attributes_survive(self):
        listing = RawListing(**_BASE, raw_floor=-1, raw_price_drop_pct=3.0,
                             raw_previous_price_eur=310_000, raw_garage="optional",
                             raw_garage_price_eur=25_000)
        assert (listing.raw_floor, listing.raw_price_drop_pct) == (-1, 3.0)
        assert listing.raw_garage == "optional"

    def test_garage_is_a_closed_vocabulary(self):
        with pytest.raises(ValueError):
            RawListing(**_BASE, raw_garage="yes")

    def test_blank_text_is_unknown(self):
        listing = RawListing(**_BASE, raw_tags="  ", raw_description="")
        assert listing.raw_tags is None
        assert listing.raw_description is None


# The column set `describe raw.idealista_listings` reports in prod before this
# change, in prod's order.
_PROD_TABLE_BEFORE = """
CREATE TABLE raw.idealista_listings (
    source_id VARCHAR NOT NULL, source_name VARCHAR NOT NULL, raw_url VARCHAR,
    raw_price_eur DOUBLE NOT NULL, raw_operation_type VARCHAR NOT NULL,
    raw_size_sqm DOUBLE NOT NULL, raw_rooms INTEGER, raw_bathrooms INTEGER,
    raw_property_type VARCHAR NOT NULL, raw_lat DOUBLE, raw_lon DOUBLE,
    raw_municipality VARCHAR NOT NULL, raw_district VARCHAR, raw_neighborhood VARCHAR,
    _loaded_at TIMESTAMPTZ NOT NULL, _run_id VARCHAR NOT NULL, raw_title VARCHAR,
    PRIMARY KEY (source_name, source_id)
);
INSERT INTO raw.idealista_listings VALUES
    ('old1', 'idealista', NULL, 250000, 'sale', 80, 2, NULL, 'apartment', NULL, NULL,
     'madrid', NULL, 'sol', now(), 'run_old', 'Piso en Sol, Madrid'),
    ('old2', 'idealista', NULL, 260000, 'sale', 85, 3, NULL, 'apartment', NULL, NULL,
     'madrid', NULL, 'sol', now(), 'run_old', 'Piso en Sol, Madrid');
"""


@pytest.fixture
def loader():
    conn = duckdb.connect()
    conn.execute("CREATE SCHEMA raw")
    conn.execute(_PROD_TABLE_BEFORE)
    ld = MotherDuckLoader(run_id="run_new")
    ld._conn = conn
    yield ld
    conn.close()


def _new_listings() -> list[RawListing]:
    return [
        RawListing(**{**_BASE, "source_id": "new1"}, raw_floor=3,
                   raw_floor_text="Planta 3ª exterior con ascensor", raw_is_exterior=True,
                   raw_has_lift=True, raw_garage="optional", raw_garage_price_eur=60_000,
                   raw_garage_text="Garaje opc. 60.000 €", raw_previous_price_eur=310_000,
                   raw_price_drop_pct=3.0, raw_description="Luminoso", raw_tags="Lujo|Villa"),
        # A house: nothing stated, every attribute must land as NULL, not false.
        RawListing(**{**_BASE, "source_id": "new2", "raw_property_type": "house"}),
    ]


class TestLoaderMigration:
    def test_old_rows_stay_null_and_new_rows_are_populated(self, loader):
        assert loader.load(_new_listings(), "idealista") == 2
        rows = loader._conn.execute("""
            SELECT source_id, raw_floor, raw_floor_text, raw_is_exterior, raw_has_lift,
                   raw_garage, raw_garage_price_eur, raw_previous_price_eur,
                   raw_price_drop_pct, raw_tags, raw_title
            FROM raw.idealista_listings ORDER BY source_id
        """).fetchall()
        assert rows == [
            ("new1", 3, "Planta 3ª exterior con ascensor", True, True, "optional",
             60000.0, 310000.0, 3.0, "Lujo|Villa", None),
            ("new2", None, None, None, None, None, None, None, None, None, None),
            ("old1", None, None, None, None, None, None, None, None, None, "Piso en Sol, Madrid"),
            ("old2", None, None, None, None, None, None, None, None, None, "Piso en Sol, Madrid"),
        ]

    def test_column_types(self, loader):
        loader.load(_new_listings(), "idealista")
        types = dict(loader._conn.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = 'raw' AND table_name = 'idealista_listings'"
        ).fetchall())
        assert types["raw_floor"] == "INTEGER"
        assert types["raw_is_exterior"] == "BOOLEAN"
        assert types["raw_has_lift"] == "BOOLEAN"
        assert types["raw_price_drop_pct"] == "DOUBLE"

    def test_migration_is_idempotent(self, loader):
        loader.load(_new_listings(), "idealista")
        cols_after_first = loader._conn.execute("DESCRIBE raw.idealista_listings").fetchall()
        # A retry of the same run: same rows, same table shape, no duplicates.
        loader.load(_new_listings(), "idealista")
        assert loader._conn.execute("DESCRIBE raw.idealista_listings").fetchall() == cols_after_first
        assert loader._conn.execute("SELECT count(*) FROM raw.idealista_listings").fetchone() == (4,)

    def test_a_batch_where_no_card_states_anything_still_loads(self, loader):
        # Every attribute column all-None in the DataFrame, so nothing in the
        # batch tells pandas the column is BOOLEAN or INTEGER.
        only_house = [_new_listings()[1]]
        assert loader.load(only_house, "idealista") == 1

    def test_a_fresh_table_gets_the_full_shape(self):
        conn = duckdb.connect()
        conn.execute("CREATE SCHEMA raw")
        ld = MotherDuckLoader(run_id="r")
        ld._conn = conn
        ld.load(_new_listings(), "idealista")
        cols = [r[0] for r in conn.execute("DESCRIBE raw.idealista_listings").fetchall()]
        assert {"raw_title", "raw_floor", "raw_tags", "raw_description"} <= set(cols)
        conn.close()
