"""
Tests for the committed-status fallback behind the freshness strip.

`docs/status.json` is the only dbt evidence that survives a deploy, so how this
app *reads* it matters as much as how CI writes it. The property under test is
the same one `orchestration/tests/test_status.py` pins on the write side: an
unknown figure is null, and null must render as "can't tell", never as
"0/0 passing" — which would put a catastrophic-looking number in the header of
an app whose entire pitch is honesty about its data.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

import json  # noqa: E402

import freshness  # noqa: E402
import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _clear_cache():
    # The loader is @st.cache_resource with no arguments, so every call in the
    # process shares one entry. Without this, test two would read test one's
    # answer.
    freshness._load_committed_status.clear()
    yield
    freshness._load_committed_status.clear()


def _write_status(tmp_path, payload):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "status.json").write_text(json.dumps(payload))
    return tmp_path


FULL = {
    "project": "spanish-housing-radar",
    "generated_at": "2026-07-30T20:09:05+00:00",
    "last_ingest_at": "2026-07-22T22:11:33+02:00",
    "rows_in_warehouse": 646,
    "dbt_tests_passed": 89,
    "dbt_tests_warned": 0,
    "dbt_tests_total": 89,
    "last_run_conclusion": "success",
}


def test_reads_the_committed_figures(tmp_path, monkeypatch):
    monkeypatch.setattr(freshness, "PROJECT_ROOT", _write_status(tmp_path, FULL))
    result = freshness._load_committed_status()
    assert result == {
        "pass": 89,
        "warn": 0,
        "total": 89,
        "generated_at": "2026-07-30",
        "conclusion": "success",
    }


def test_absent_file_is_no_evidence(tmp_path, monkeypatch):
    monkeypatch.setattr(freshness, "PROJECT_ROOT", tmp_path)
    assert freshness._load_committed_status() is None


def test_unparseable_file_is_no_evidence(tmp_path, monkeypatch):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "status.json").write_text("{ truncated")
    monkeypatch.setattr(freshness, "PROJECT_ROOT", tmp_path)
    assert freshness._load_committed_status() is None


def test_null_counts_are_no_evidence_not_zero(tmp_path, monkeypatch):
    # What CI writes when the warehouse or the dbt artifact was unreachable.
    payload = FULL | {"dbt_tests_passed": None, "dbt_tests_total": None}
    monkeypatch.setattr(freshness, "PROJECT_ROOT", _write_status(tmp_path, payload))
    assert freshness._load_committed_status() is None


def test_zero_total_is_no_evidence(tmp_path, monkeypatch):
    # A `dbt run` with no tests executed must not render as "0/0 passing".
    payload = FULL | {"dbt_tests_passed": 0, "dbt_tests_total": 0}
    monkeypatch.setattr(freshness, "PROJECT_ROOT", _write_status(tmp_path, payload))
    assert freshness._load_committed_status() is None


def test_missing_conclusion_falls_back_to_unknown(tmp_path, monkeypatch):
    payload = FULL | {"last_run_conclusion": None}
    monkeypatch.setattr(freshness, "PROJECT_ROOT", _write_status(tmp_path, payload))
    assert freshness._load_committed_status()["conclusion"] == "unknown"


def test_failed_tests_survive_as_a_gap(tmp_path, monkeypatch):
    # The schema has no fail/error split; the caller derives "broken" from the
    # difference, so the loader must pass the numbers through untouched.
    payload = FULL | {"dbt_tests_passed": 86, "dbt_tests_total": 89}
    monkeypatch.setattr(freshness, "PROJECT_ROOT", _write_status(tmp_path, payload))
    result = freshness._load_committed_status()
    assert (result["pass"], result["warn"], result["total"]) == (86, 0, 89)


def test_a_warning_is_carried_separately_from_a_failure(tmp_path, monkeypatch):
    # 103 pass + 1 warn + 0 broken. Before this field existed the caller derived
    # broken = total - pass = 1 and the header read "103/104 passing" in amber,
    # announcing a failure in a build where nothing had failed.
    payload = FULL | {
        "dbt_tests_passed": 103, "dbt_tests_warned": 1, "dbt_tests_total": 104,
    }
    monkeypatch.setattr(freshness, "PROJECT_ROOT", _write_status(tmp_path, payload))
    result = freshness._load_committed_status()
    assert (result["pass"], result["warn"], result["total"]) == (103, 1, 104)
    assert result["total"] - result["pass"] - result["warn"] == 0


def test_a_status_file_written_before_warnings_existed_still_reads(tmp_path, monkeypatch):
    # Every status.json committed before this field was added has no
    # `dbt_tests_warned` key. It must read as 0 — no test could warn then — and
    # never as None, which would break the arithmetic downstream.
    payload = {k: v for k, v in FULL.items() if k != "dbt_tests_warned"}
    monkeypatch.setattr(freshness, "PROJECT_ROOT", _write_status(tmp_path, payload))
    assert freshness._load_committed_status()["warn"] == 0


def test_the_header_does_not_announce_a_failure_for_an_advisory(tmp_path, monkeypatch):
    """
    The end the visitor actually sees.

    The loader-level tests above pin the numbers; this pins what is rendered from
    them, because the defect was in the rendering: `broken = total - pass` turned
    one advisory warning into "103/104 passing" in amber, which reads as a broken
    assertion on the most prominent number the page carries.

    Runs the deployed path on purpose — PROJECT_ROOT points at a directory with a
    status.json and no transform/target, which is exactly the shape of a
    Streamlit Cloud deploy.
    """
    payload = FULL | {
        "dbt_tests_passed": 103, "dbt_tests_warned": 1, "dbt_tests_total": 104,
    }
    monkeypatch.setattr(freshness, "PROJECT_ROOT", _write_status(tmp_path, payload))
    freshness.get_freshness_strip.clear()
    freshness._load_dbt_test_results.clear()
    freshness._load_committed_status.clear()

    items = freshness.get_freshness_strip()
    dbt_item = next(i for i in items if i.label == "dbt tests")

    assert dbt_item.value == "103/104 passing"
    # Nothing is broken, so nothing may be coloured as broken.
    assert dbt_item.tone == "good"
    # And the warning is not simply swallowed to achieve that.
    assert "advisory warning" in dbt_item.help
