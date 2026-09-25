"""
The live-app ImportError, reproduced: a new page importing a name that the
cached, pre-deploy `components.charts` does not have.
"""
from __future__ import annotations

import importlib
import os
from pathlib import Path
import sys
import types

sys.path.insert(0, str(Path(__file__).parent.parent))

import hot_reload  # noqa: E402
import pytest  # noqa: E402

APP_DIR = Path(__file__).resolve().parent.parent
CHARTS = APP_DIR / "components" / "charts.py"


@pytest.fixture
def clean_state():
    saved = sys.modules.get("components.charts")
    had_state = hasattr(sys, hot_reload._STATE_ATTR)
    old_state = getattr(sys, hot_reload._STATE_ATTR, None)
    yield
    # Always put back what was there, including "nothing": a fake left behind
    # is this bug, reproduced in every test that runs after.
    if saved is not None:
        sys.modules["components.charts"] = saved
    else:
        sys.modules.pop("components.charts", None)
    if had_state:
        setattr(sys, hot_reload._STATE_ATTR, old_state)
    elif hasattr(sys, hot_reload._STATE_ATTR):
        delattr(sys, hot_reload._STATE_ATTR)


def _stale_charts() -> types.ModuleType:
    """What the server held after the pull: the old module, same file path."""
    old = types.ModuleType("components.charts")
    old.__file__ = str(CHARTS)
    return old


@pytest.mark.usefixtures("clean_state")
def test_the_failure_is_real_without_the_fix():
    sys.modules["components.charts"] = _stale_charts()
    with pytest.raises(ImportError):
        from components.charts import dot_barrio_range  # noqa: F401


@pytest.mark.usefixtures("clean_state")
def test_a_server_already_stale_when_this_arrives_is_repaired():
    # First run of this code in the process: nothing recorded yet, so every app
    # module is dropped — the live app's situation on the deploy of this fix.
    if hasattr(sys, hot_reload._STATE_ATTR):
        delattr(sys, hot_reload._STATE_ATTR)
    sys.modules["components.charts"] = _stale_charts()

    assert "components.charts" in hot_reload.drop_stale(APP_DIR)
    from components.charts import dot_barrio_range  # noqa: F401


@pytest.mark.usefixtures("clean_state")
def test_a_later_deploy_is_picked_up_by_mtime():
    importlib.import_module("components.charts")
    hot_reload.drop_stale(APP_DIR)          # first run: drop + record
    importlib.import_module("components.charts")
    assert hot_reload.drop_stale(APP_DIR) == []   # nothing changed: nothing dropped

    sys.modules["components.charts"] = _stale_charts()
    stat = CHARTS.stat()
    os.utime(CHARTS, (stat.st_atime, stat.st_mtime + 5))   # the pull rewrote it
    try:
        assert "components.charts" in hot_reload.drop_stale(APP_DIR)
        from components.charts import dot_barrio_range  # noqa: F401
    finally:
        os.utime(CHARTS, (stat.st_atime, stat.st_mtime))


@pytest.mark.usefixtures("clean_state")
def test_site_packages_are_never_touched():
    hot_reload.drop_stale(APP_DIR)
    assert "streamlit" in sys.modules
    assert "pandas" in sys.modules
