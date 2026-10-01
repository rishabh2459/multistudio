"""Multicam Studio — auto-edit a multicam podcast (DaVinci Resolve Free and Studio).

Installed into Resolve's Scripts/Edit folder; the code lives in the Multicam Studio
data folder (resolve-plugin/), so updating the engine updates this script too.
"""

import os
import sys


def _lib_dir():
    here = os.path.dirname(os.path.abspath(globals().get("__file__", "") or "."))
    if os.path.isdir(os.path.join(here, "multicam_resolve")):
        return here  # development: run from the repo
    if sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support/Multicam Studio")
    elif sys.platform == "win32":
        base = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "Multicam Studio")
    else:
        base = os.path.join(
            os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share")), "multicam-studio"
        )
    return os.path.join(os.environ.get("MULTICAM_DATA_DIR", base), "resolve-plugin")


sys.path.insert(0, _lib_dir())
from multicam_resolve.adapter import find_resolve  # noqa: E402
from multicam_resolve.ui import main  # noqa: E402

_resolve = find_resolve(globals())
main(_resolve, globals().get("fusion") or _resolve.Fusion(), globals().get("bmd") or bmd)  # noqa: F821
