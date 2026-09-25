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
before anything imports a helper. A module is dropped when its file changed
since this process last saw it, and on the first run of a process that has not
been through here before — which is what repairs a server that was already
stale when this code arrived. The next import loads the file from disk.

`st.cache_data` / `st.cache_resource` survive this: their keys come from the
function's qualified name and source, not from the module object.
"""
from __future__ import annotations

from pathlib import Path
import sys

# Kept on `sys`, which outlives every script run, because this module's own
# globals are dropped along with everything else.
_STATE_ATTR = "_housing_radar_module_mtimes"


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
    """Remove stale app modules from `sys.modules`; return the names removed."""
    first_run = not hasattr(sys, _STATE_ATTR)
    seen: dict[str, float] = getattr(sys, _STATE_ATTR, {})
    dropped = []
    for name, path in _app_modules(app_dir).items():
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if first_run or seen.get(name, mtime) != mtime:
            del sys.modules[name]
            dropped.append(name)
        seen[name] = mtime
    setattr(sys, _STATE_ATTR, seen)
    return dropped
