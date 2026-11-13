"""
Flow-structure tests for the refresh pipeline — no network, no MotherDuck.

subprocess.run is mocked, so this only proves orchestration wiring: task ordering
(INE + extract before dbt build), that the free INE feed runs even when scraping
is off, that a failing scrape short-circuits the dbt step, and that the dbt target
is passed through. It does NOT prove the scraper / INE fetch / dbt project work —
that's extraction/tests/ and `dbt build` in CI.
"""
import json
from unittest.mock import MagicMock, patch

from prefect.testing.utilities import prefect_test_harness
import pytest

from orchestration.flows import pipeline as pipeline_mod
from orchestration.flows.pipeline import parse_scrape_summary, rotated_operations, run_pipeline


@pytest.fixture(autouse=True, scope="module")
def prefect_harness():
    with prefect_test_harness():
        yield


def _ok_result(*_args, **_kwargs):
    return MagicMock(returncode=0, stdout="", stderr="")


def _fail_extract_only(cmd, *_args, **_kwargs):
    """INE + dbt succeed; only the listing scraper fails."""
    if "run_extraction.py" in " ".join(cmd):
        return MagicMock(returncode=1, stdout="", stderr="boom")
    return MagicMock(returncode=0, stdout="", stderr="")


class TestPipeline:
    @patch("orchestration.flows.pipeline.subprocess.run", side_effect=_ok_result)
    def test_ine_and_extract_run_before_dbt_build(self, mock_run):
        run_pipeline(scrape=True)

        commands = [" ".join(call.args[0]) for call in mock_run.call_args_list]
        ine_idx = next(i for i, c in enumerate(commands) if "run_ine" in c)
        extract_idx = next(i for i, c in enumerate(commands) if "run_extraction.py" in c)
        dbt_idx = next(i for i, c in enumerate(commands) if "build" in c)
        assert ine_idx < dbt_idx
        assert extract_idx < dbt_idx

    @patch("orchestration.flows.pipeline.subprocess.run", side_effect=_ok_result)
    def test_scrape_off_still_refreshes_ine_and_dbt(self, mock_run):
        """The un-park guarantee: no scrape, but INE + dbt still run (free refresh)."""
        run_pipeline(scrape=False)

        commands = [" ".join(call.args[0]) for call in mock_run.call_args_list]
        assert any("run_ine" in c for c in commands)
        assert any("build" in c for c in commands)
        assert not any("run_extraction.py" in c for c in commands)

    @patch("orchestration.flows.pipeline.subprocess.run", side_effect=_ok_result)
    def test_dbt_target_is_passed_through(self, mock_run):
        run_pipeline(dbt_target="ci", scrape=False)

        commands = [call.args[0] for call in mock_run.call_args_list]
        dbt_cmd = next(c for c in commands if "build" in c)
        assert "ci" in dbt_cmd

    @patch("orchestration.flows.pipeline.subprocess.run", side_effect=_fail_extract_only)
    def test_failed_scrape_raises_and_skips_dbt_build(self, mock_run):
        """extract_all has retries=2 (3 attempts); dbt build must never run."""
        with pytest.raises(RuntimeError, match="Command failed"):
            run_pipeline(scrape=True)

        commands = [" ".join(call.args[0]) for call in mock_run.call_args_list]
        # The medallion rebuild must not have run after the scrape failure. (This
        # looked for "build --target", which the real command never contains —
        # `dbt build --project-dir … --target …` — so it could not fail.)
        assert not any(" build " in f" {c} " for c in commands)
        # …but the free INE feed did run before it.
        assert any("run_ine" in c for c in commands)


class TestScrapeCoverageWiring:
    def test_rotation_is_deterministic_and_alternates(self):
        ops = ["sale", "rent"]
        assert rotated_operations(ops, 46) == rotated_operations(ops, 46)
        assert rotated_operations(ops, 46)[0] != rotated_operations(ops, 47)[0]
        assert rotated_operations([], 3) == []

    def test_parse_summary_ignores_other_lines(self):
        out = 'noise\nSCRAPE_SUMMARY {"operation": "sale", "listings": 5}\nSCRAPE_SUMMARY bad{\n'
        assert parse_scrape_summary(out) == [{"operation": "sale", "listings": 5}]

    def test_flow_writes_summary_and_a_partial_scrape_does_not_fail(self, tmp_path, monkeypatch):
        path = tmp_path / "summary.json"
        monkeypatch.setattr(pipeline_mod, "SCRAPE_SUMMARY_PATH", path)

        def fake(cmd, *_a, **_k):
            if "run_extraction.py" in " ".join(cmd):
                op = cmd[cmd.index("--operation") + 1]
                n = 0 if op == "rent" else 90
                line = "SCRAPE_SUMMARY " + json.dumps({
                    "operation": op, "pages_requested": 3, "pages_with_cards": 3,
                    "pages_blocked": 0, "listings": n})
                return MagicMock(returncode=0, stdout=line, stderr="")
            return MagicMock(returncode=0, stdout="", stderr="")

        with patch("orchestration.flows.pipeline.subprocess.run", side_effect=fake):
            run_pipeline(scrape=True)
        written = {r["operation"]: r["listings"] for r in json.loads(path.read_text())}
        assert written == {"sale": 90, "rent": 0}

    def test_no_scrape_removes_a_stale_summary(self, tmp_path, monkeypatch):
        path = tmp_path / "summary.json"
        path.write_text("[]")
        monkeypatch.setattr(pipeline_mod, "SCRAPE_SUMMARY_PATH", path)
        with patch("orchestration.flows.pipeline.subprocess.run", side_effect=_ok_result):
            run_pipeline(scrape=False)
        assert not path.exists()
