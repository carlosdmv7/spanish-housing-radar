"""Unit tests for the INE IPV series-name parser and record building."""
from __future__ import annotations

from extraction.schemas.ine_records import IneHpiRecord
from extraction.sources.ine_hpi import _parse_series_name


class TestParseSeriesName:
    def test_simple_region(self):
        assert _parse_series_name("Cataluña. General. Índice.") == (
            "Cataluña", "general", "index",
        )

    def test_trailing_space_real_format(self):
        # INE returns a trailing "period + space" — must still parse to 3 segments.
        assert _parse_series_name("Nacional. General. Índice. ") == (
            "Nacional", "general", "index",
        )

    def test_region_with_comma(self):
        # Region names carry commas but never ". ", so the split stays clean.
        assert _parse_series_name("Madrid, Comunidad de. Vivienda nueva. Variación anual.") == (
            "Madrid, Comunidad de", "new", "yoy",
        )

    def test_second_hand_qoq(self):
        assert _parse_series_name(
            "Comunitat Valenciana. Vivienda segunda mano. Variación trimestral."
        ) == ("Comunitat Valenciana", "second_hand", "qoq")

    def test_ytd_metric(self):
        region, htype, metric = _parse_series_name(
            "Andalucía. General. Variación en lo que va de año."
        )
        assert (htype, metric) == ("general", "ytd")

    def test_unknown_housing_type_returns_none(self):
        assert _parse_series_name("Galicia. Locales comerciales. Índice.") is None

    def test_malformed_returns_none(self):
        assert _parse_series_name("Nacional General Índice") is None


class TestIneHpiRecord:
    def test_valid_record(self):
        from datetime import date

        rec = IneHpiRecord(
            series_cod="ABC123",
            region="Comunitat Valenciana",
            housing_type="second_hand",
            metric="yoy",
            period_date=date(2025, 1, 1),
            year=2025,
            value=8.4,
        )
        assert rec.value == 8.4
        assert rec.year == 2025


class TestQuarterEnd:
    def test_ine_period_codes_map_to_quarter_ends(self):
        from datetime import date

        from extraction.sources.ine_hpi import _quarter_end

        assert [_quarter_end(2025, p) for p in (19, 20, 21, 22)] == [
            date(2025, 3, 31), date(2025, 6, 30), date(2025, 9, 30), date(2025, 12, 31),
        ]

    def test_non_quarterly_period_is_skipped(self):
        from extraction.sources.ine_hpi import _quarter_end

        assert _quarter_end(2025, 28) is None


class TestFetchLabelsTheRightQuarter:
    """The payload shape INE really returns, for Q4 2025."""

    def test_q4_is_stored_as_december_not_september(self, monkeypatch):
        from datetime import date

        from extraction.sources import ine_hpi

        payload = [{
            "COD": "IPV1209",
            "Nombre": "Nacional. General. Índice. ",
            # 2025-10-01 00:00 in Madrid — read as UTC this is 2025-09-30, which
            # is how Q4 used to be stored as the end of Q3.
            "Data": [{"Fecha": 1759269600000, "FK_Periodo": 22, "Anyo": 2025,
                      "Valor": 103.805}],
        }]

        class FakeResponse:
            def raise_for_status(self):
                pass

            def json(self):
                return payload

        monkeypatch.setattr(ine_hpi.requests, "get", lambda *_args, **_kwargs: FakeResponse())
        [rec] = ine_hpi.fetch_ine_hpi()
        assert rec.period_date == date(2025, 12, 31)
        assert rec.year == 2025


class TestLoadReplacesTheSnapshot:
    def _record(self, cod: str, value: float) -> IneHpiRecord:
        from datetime import date

        return IneHpiRecord(series_cod=cod, region="Nacional", housing_type="general",
                            metric="index", period_date=date(2025, 12, 31),
                            year=2025, value=value)

    def test_a_rebase_does_not_leave_the_old_series_behind(self):
        import duckdb

        from extraction.config import INE_HPI_RAW_TABLE
        from extraction.loaders.motherduck_loader import MotherDuckLoader

        loader = MotherDuckLoader(run_id="test")
        loader._conn = duckdb.connect(":memory:")
        loader._conn.execute("CREATE SCHEMA raw")

        loader.load_ine_hpi([self._record("IPV769", 186.75)])   # base 2015
        loader.load_ine_hpi([self._record("IPV1209", 103.805)])  # base 2025

        rows = loader._conn.execute(
            f"SELECT series_cod, value FROM {INE_HPI_RAW_TABLE}").fetchall()
        assert rows == [("IPV1209", 103.805)]
