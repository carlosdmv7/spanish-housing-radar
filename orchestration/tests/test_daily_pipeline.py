"""
Flow-structure tests for the daily pipeline — no network, no MotherDuck.

subprocess.run is mocked, so this only proves orchestration wiring: task ordering
(INE + extract before dbt build), that the free INE feed runs even when scraping
is off, that a failing scrape short-circuits the dbt step, and that the dbt target
is passed through. It does NOT prove the scraper / INE fetch / dbt project work —
that's extraction/tests/ and `dbt build` in CI.
"""
from unittest.mock import MagicMock, patch

from prefect.testing.utilities import prefect_test_harness
import pytest

from orchestration.flows.daily_pipeline import daily_pipeline


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


class TestDailyPipeline:
    @patch("orchestration.flows.daily_pipeline.subprocess.run", side_effect=_ok_result)
    def test_ine_and_extract_run_before_dbt_build(self, mock_run):
        daily_pipeline(scrape=True)

        commands = [" ".join(call.args[0]) for call in mock_run.call_args_list]
        ine_idx = next(i for i, c in enumerate(commands) if "run_ine" in c)
        extract_idx = next(i for i, c in enumerate(commands) if "run_extraction.py" in c)
        dbt_idx = next(i for i, c in enumerate(commands) if "build" in c)
        assert ine_idx < dbt_idx
        assert extract_idx < dbt_idx

    @patch("orchestration.flows.daily_pipeline.subprocess.run", side_effect=_ok_result)
    def test_scrape_off_still_refreshes_ine_and_dbt(self, mock_run):
        """The un-park guarantee: no scrape, but INE + dbt still run (free refresh)."""
        daily_pipeline(scrape=False)

        commands = [" ".join(call.args[0]) for call in mock_run.call_args_list]
        assert any("run_ine" in c for c in commands)
        assert any("build" in c for c in commands)
        assert not any("run_extraction.py" in c for c in commands)

    @patch("orchestration.flows.daily_pipeline.subprocess.run", side_effect=_ok_result)
    def test_dbt_target_is_passed_through(self, mock_run):
        daily_pipeline(dbt_target="ci", scrape=False)

        commands = [call.args[0] for call in mock_run.call_args_list]
        dbt_cmd = next(c for c in commands if "build" in c)
        assert "ci" in dbt_cmd

    @patch("orchestration.flows.daily_pipeline.subprocess.run", side_effect=_fail_extract_only)
    def test_failed_scrape_raises_and_skips_dbt_build(self, mock_run):
        """extract_all has retries=2 (3 attempts); dbt build must never run."""
        with pytest.raises(RuntimeError, match="Command failed"):
            daily_pipeline(scrape=True)

        commands = [" ".join(call.args[0]) for call in mock_run.call_args_list]
        # The medallion rebuild must not have run after the scrape failure.
        assert not any("build --target" in c for c in commands)
        # …but the free INE feed did run before it.
        assert any("run_ine" in c for c in commands)
