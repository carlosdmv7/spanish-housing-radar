"""
Two live-app failures after a Cloud redeploy, reproduced.

1. An ImportError: a new page importing a name the cached, pre-deploy
   `components.charts` does not have.
2. An UnserializableReturnValueError: `chrome.py` unchanged and kept, still
   calling the function of a dropped `freshness`, which built a `StripItem`
   from a dropped `theme` that `st.cache_data` could no longer pickle.
"""
from __future__ import annotations

import importlib
import os
from pathlib import Path
import pickle
import sys
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
    importlib.import_module("theme")
    hot_reload.drop_stale(APP_DIR)
    importlib.import_module("theme")
    importlib.import_module("chrome")
    importlib.import_module("freshness")
    old_item = sys.modules["freshness"].StripItem("label", "value")

    theme_py = APP_DIR / "theme.py"
    stat = theme_py.stat()
    os.utime(theme_py, (stat.st_atime, stat.st_mtime + 5))   # only theme changed
    try:
        dropped = hot_reload.drop_stale(APP_DIR)
    finally:
        os.utime(theme_py, (stat.st_atime, stat.st_mtime))

    # chrome did not change, but it held freshness, which held the old theme.
    assert {"theme", "freshness", "chrome"} <= set(dropped)
    # What broke the live app: an old instance no longer pickles once theme
    # is re-imported. Everything re-imported together pickles again.
    importlib.import_module("theme")
    with pytest.raises(pickle.PicklingError):
        pickle.dumps(old_item)
    fresh = importlib.import_module("freshness")
    pickle.dumps(fresh.StripItem("label", "value"))


@pytest.mark.usefixtures("clean_state")
def test_the_reloader_does_not_drop_itself():
    hot_reload.drop_stale(APP_DIR)
    assert "hot_reload" in sys.modules


@pytest.mark.usefixtures("clean_state")
def test_site_packages_are_never_touched():
    hot_reload.drop_stale(APP_DIR)
    assert "streamlit" in sys.modules
    assert "pandas" in sys.modules
