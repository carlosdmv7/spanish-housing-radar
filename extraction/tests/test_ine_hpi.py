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
