"""
Two live-app failures after a Cloud redeploy, reproduced.

1. An ImportError: a new page importing a name the cached, pre-deploy
   `components.charts` does not have.
2. An UnserializableReturnValueError: `chrome.py` unchanged and kept, still
   calling the function of a dropped `freshness`, which built a `StripItem`
   from a dropped `theme` that `st.cache_data` could no longer pickle. (`theme`
   is now the installed `brand` package; the test keeps the chrome→freshness
   half of that chain.)
"""
from __future__ import annotations

import importlib
import os
from pathlib import Path
import pickle
import sys
import time
import types

sys.path.insert(0, str(Path(__file__).parent.parent))

import hot_reload  # noqa: E402
import pytest  # noqa: E402

APP_DIR = Path(__file__).resolve().parent.parent
CHARTS = APP_DIR / "components" / "charts.py"


@pytest.fixture
def clean_state():
    # drop_stale now removes every app module, so put every one of them back —
    # and remove any the test added. A module swapped under the other test
    # files is this bug, reproduced in every test that runs after.
    saved = dict(hot_reload._app_modules(APP_DIR))
    saved = {name: sys.modules[name] for name in saved}
    had_state = hasattr(sys, hot_reload._STATE_ATTR)
    old_state = getattr(sys, hot_reload._STATE_ATTR, None)
    yield
    for name in hot_reload._app_modules(APP_DIR):
        if name not in saved:
            sys.modules.pop(name, None)
    sys.modules.update(saved)
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
def test_an_unchanged_module_is_dropped_with_the_changed_one():
    importlib.import_module("freshness")
    hot_reload.drop_stale(APP_DIR)
    importlib.import_module("freshness")
    importlib.import_module("chrome")
    old_item = sys.modules["freshness"].StripItem("label", "value")

    freshness_py = APP_DIR / "freshness.py"
    stat = freshness_py.stat()
    os.utime(freshness_py, (stat.st_atime, stat.st_mtime + 5))   # only freshness changed
    try:
        dropped = hot_reload.drop_stale(APP_DIR)
    finally:
        os.utime(freshness_py, (stat.st_atime, stat.st_mtime))

    # chrome did not change, but it held the old freshness's function.
    assert {"freshness", "chrome"} <= set(dropped)
    # What broke the live app in #43 was a StripItem class defined in an app
    # module that had been dropped. It now lives in the installed `brand`
    # package, which is never dropped, so an instance built before a deploy
    # still pickles after it.
    fresh = importlib.import_module("freshness")
    assert fresh.StripItem is type(old_item)
    pickle.dumps(old_item)


@pytest.mark.usefixtures("clean_state")
def test_a_pull_before_the_second_run_is_still_seen():
    # First run: drop, and only the modules imported so far get an mtime.
    if hasattr(sys, hot_reload._STATE_ATTR):
        delattr(sys, hot_reload._STATE_ATTR)
    sys.modules.pop("config", None)
    hot_reload.drop_stale(APP_DIR)
    importlib.import_module("config")        # imported after the drop: no baseline

    config_py = APP_DIR / "config.py"
    stat = config_py.stat()
    os.utime(config_py, (stat.st_atime, time.time() + 5))   # the pull lands now
    try:
        assert "config" in hot_reload.drop_stale(APP_DIR)
    finally:
        os.utime(config_py, (stat.st_atime, stat.st_mtime))


@pytest.mark.usefixtures("clean_state")
def test_the_reloader_does_not_drop_itself():
    hot_reload.drop_stale(APP_DIR)
    assert "hot_reload" in sys.modules


@pytest.mark.usefixtures("clean_state")
def test_site_packages_are_never_touched():
    hot_reload.drop_stale(APP_DIR)
    assert "streamlit" in sys.modules
    assert "pandas" in sys.modules
