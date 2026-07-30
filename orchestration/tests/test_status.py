"""
Tests for the committed pipeline status record — no network, no MotherDuck.

The property under test is the one the file exists for: when a figure can't be
established, the status reports **null**, never a plausible-looking zero. A
status file claiming `dbt_tests_passed: 0` because it couldn't find the artifact
reads as a catastrophic failure; `null` reads as "couldn't tell", which is the
truth. These tests pin that distinction, and the exact key set the schema
promises to whatever consumes the file.
"""
from __future__ import annotations

import json
from unittest.mock import patch

from orchestration import status

EXPECTED_KEYS = {
    "project",
    "generated_at",
    "last_ingest_at",
    "rows_in_warehouse",
    "dbt_tests_passed",
    "dbt_tests_total",
    "last_run_conclusion",
}


class TestBuildStatus:
    @patch.object(status, "query_warehouse", return_value=(646, "2026-07-22T22:11:33+02:00"))
    @patch.object(status, "read_dbt_test_results", return_value=(89, 89))
    def test_schema_is_exactly_the_documented_keys(self, _tests, _wh):
        assert set(status.build_status()) == EXPECTED_KEYS

    @patch.object(status, "query_warehouse", return_value=(646, "2026-07-22T22:11:33+02:00"))
    @patch.object(status, "read_dbt_test_results", return_value=(89, 89))
    def test_happy_path_reports_the_figures(self, _tests, _wh):
        result = status.build_status()
        assert result["project"] == "spanish-housing-radar"
        assert result["rows_in_warehouse"] == 646
        assert result["dbt_tests_passed"] == 89
        assert result["dbt_tests_total"] == 89

    @patch.object(status, "query_warehouse", return_value=(None, None))
    @patch.object(status, "read_dbt_test_results", return_value=(None, None))
    def test_unknown_figures_are_null_not_zero(self, _tests, _wh):
        result = status.build_status()
        for field in ("rows_in_warehouse", "last_ingest_at",
                      "dbt_tests_passed", "dbt_tests_total"):
            assert result[field] is None, f"{field} must degrade to null, not 0"

    @patch.object(status, "query_warehouse", return_value=(None, None))
    @patch.object(status, "read_dbt_test_results", return_value=(None, None))
    def test_conclusion_comes_from_the_environment(self, _tests, _wh, monkeypatch):
        monkeypatch.setenv("RUN_CONCLUSION", "failure")
        assert status.build_status()["last_run_conclusion"] == "failure"

    @patch.object(status, "query_warehouse", return_value=(None, None))
    @patch.object(status, "read_dbt_test_results", return_value=(None, None))
    def test_conclusion_is_unknown_outside_ci(self, _tests, _wh, monkeypatch):
        monkeypatch.delenv("RUN_CONCLUSION", raising=False)
        assert status.build_status()["last_run_conclusion"] == "unknown"


class TestReadDbtTestResults:
    def _write(self, tmp_path, payload):
        path = tmp_path / "run_results.json"
        path.write_text(json.dumps(payload))
        return path

    def test_counts_only_test_nodes(self, tmp_path, monkeypatch):
        path = self._write(tmp_path, {"results": [
            {"unique_id": "model.shr.fct_listings_scored", "status": "success"},
            {"unique_id": "test.shr.not_null_x", "status": "pass"},
            {"unique_id": "test.shr.unique_y", "status": "pass"},
            {"unique_id": "test.shr.range_z", "status": "fail"},
        ]})
        monkeypatch.setattr(status, "RUN_RESULTS_PATH", path)
        # The model node must not inflate either count.
        assert status.read_dbt_test_results() == (2, 3)

    def test_missing_artifact_is_unknown_not_zero(self, tmp_path, monkeypatch):
        monkeypatch.setattr(status, "RUN_RESULTS_PATH", tmp_path / "absent.json")
        assert status.read_dbt_test_results() == (None, None)

    def test_unparseable_artifact_is_unknown(self, tmp_path, monkeypatch):
        path = tmp_path / "run_results.json"
        path.write_text("{ truncated")
        monkeypatch.setattr(status, "RUN_RESULTS_PATH", path)
        assert status.read_dbt_test_results() == (None, None)

    def test_a_run_with_no_tests_is_unknown(self, tmp_path, monkeypatch):
        # `dbt run` (no tests executed) must not be reported as "0/0 passing".
        path = self._write(tmp_path, {"results": [
            {"unique_id": "model.shr.rpt_opportunities", "status": "success"},
        ]})
        monkeypatch.setattr(status, "RUN_RESULTS_PATH", path)
        assert status.read_dbt_test_results() == (None, None)


class TestQueryWarehouse:
    def test_missing_token_degrades_to_null(self, monkeypatch):
        monkeypatch.delenv("MOTHERDUCK_TOKEN", raising=False)
        assert status.query_warehouse() == (None, None)

    def test_unreachable_warehouse_degrades_to_null(self, monkeypatch):
        monkeypatch.setenv("MOTHERDUCK_TOKEN", "not-a-real-token")
        with patch("duckdb.connect", side_effect=RuntimeError("no route to host")):
            assert status.query_warehouse() == (None, None)
