"""
Drop app modules that went stale under a running server.

Streamlit Community Cloud redeploys a push by pulling the new commit into the
running container. The page scripts are re-executed on every run, so they are
always the new code — but the helper modules they import (`components.charts`,
`theme`, `config`, …) stay in `sys.modules` exactly as they were first imported.
After #35 that meant a new Neighbourhoods page asking an old `components.charts`
for `dot_barrio_range`, and the live app died on an ImportError until someone
rebooted it by hand.

`app/main.py` is also re-executed on every run, so it calls `drop_stale()`
before anything imports a helper. When any app module's file has changed since
this process last saw it — or on the first run of a process that has not been
through here before, which is what repairs a server already stale when this
code arrives — **every** app module is dropped, and the next imports load them
all from disk, consistently.

All of them, not just the changed ones. The first version dropped only changed
files, and #43 broke the live app with it: `theme.py` and `freshness.py`
changed, `chrome.py` did not, so the kept `chrome` still called the dropped
`freshness`'s function, which built a `StripItem` from the dropped `theme` —
and `st.cache_data` could not pickle an instance of a class that is no longer
`theme.StripItem`. A module that did not change can still hold objects from
one that did; only a full drop cannot leave such a reference behind. It costs a
re-import of a dozen small modules, once per deploy.

`st.cache_data` / `st.cache_resource` survive this: their keys come from the
function's qualified name and source, not from the module object.
"""
from __future__ import annotations

from pathlib import Path
import sys

# Kept on `sys`, which outlives every script run, because this module's own
# globals are dropped along with everything else.
# Versioned: a new name makes the first run of new logic count as a first run,
# so it drops everything even if an older version already recorded mtimes.
_STATE_ATTR = "_housing_radar_module_mtimes_v2"


def _app_modules(app_dir: Path) -> dict[str, Path]:
    root = str(app_dir.resolve())
    found = {}
    for name, module in list(sys.modules.items()):
        file = getattr(module, "__file__", None)
        if name == "__main__" or not file:
            continue
        path = Path(file).resolve()
        if str(path).startswith(root) and "site-packages" not in path.parts:
            found[name] = path
    return found


def drop_stale(app_dir: Path) -> list[str]:
    """If any app module is stale, drop them all; return the names removed."""
    first_run = not hasattr(sys, _STATE_ATTR)
    seen: dict[str, float] = getattr(sys, _STATE_ATTR, {})
    modules = _app_modules(app_dir)
    mtimes = {}
    for name, path in modules.items():
        try:
            mtimes[name] = path.stat().st_mtime
        except OSError:
            mtimes[name] = None  # deleted by the pull: stale by definition
    stale = first_run or any(seen.get(name, mtime) != mtime
                             for name, mtime in mtimes.items())
    dropped = []
    if stale:
        for name in modules:
            # The reloader itself is refreshed by main.py, not by itself.
            if name != __name__:
                del sys.modules[name]
                dropped.append(name)
    seen.update({name: m for name, m in mtimes.items() if m is not None})
    setattr(sys, _STATE_ATTR, seen)
    return dropped
