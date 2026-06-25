"""
Flow-structure tests for the daily pipeline — no network, no MotherDuck.

subprocess.run is mocked, so this only proves: task ordering (extract before
dbt build), that a failing extract short-circuits the dbt step, and that the
dbt target is wired through correctly. It does NOT prove the scraper or dbt
project themselves work — that's extraction/tests/ and `dbt build` in CI.
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


class TestDailyPipeline:
    @patch("orchestration.flows.daily_pipeline.subprocess.run", side_effect=_ok_result)
    def test_runs_extract_before_dbt_build(self, mock_run):
        daily_pipeline()

        commands = [call.args[0] for call in mock_run.call_args_list]
        assert any("run_extraction.py" in " ".join(c) for c in commands)
        assert any("build" in c for c in commands)

        extract_idx = next(i for i, c in enumerate(commands) if "run_extraction.py" in " ".join(c))
        dbt_idx = next(i for i, c in enumerate(commands) if "build" in c)
        assert extract_idx < dbt_idx

    @patch("orchestration.flows.daily_pipeline.subprocess.run", side_effect=_ok_result)
    def test_dbt_target_is_passed_through(self, mock_run):
        daily_pipeline(dbt_target="ci")

        commands = [call.args[0] for call in mock_run.call_args_list]
        dbt_cmd = next(c for c in commands if "build" in c)
        assert "ci" in dbt_cmd

    @patch(
        "orchestration.flows.daily_pipeline.subprocess.run",
        return_value=MagicMock(returncode=1, stdout="", stderr="boom"),
    )
    def test_failed_extract_raises_and_skips_dbt_build(self, mock_run):
        """extract_all has retries=2 (3 attempts total); dbt build must never run."""
        with pytest.raises(RuntimeError, match="Command failed"):
            daily_pipeline()

        commands = [call.args[0] for call in mock_run.call_args_list]
        assert len(commands) == 3
        assert all("run_extraction.py" in " ".join(c) for c in commands)
