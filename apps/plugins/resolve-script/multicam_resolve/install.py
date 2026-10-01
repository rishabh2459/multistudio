"""Install / remove the Resolve script (called by the installer; PL9 adds the UI).

python -m multicam_resolve.install [--uninstall]
"""

import os
import shutil
import sys
from typing import List, Optional

from .client import data_dir

SCRIPT_NAME = "Multicam Studio.py"
HERE = os.path.dirname(os.path.abspath(__file__))


def scripts_dir(platform: str = sys.platform) -> str:
    """Resolve's per-user Scripts/Edit folder (Workspace > Scripts > Edit)."""
    home = os.path.expanduser("~")
    if platform == "darwin":
        base = os.path.join(
            home,
            "Library",
            "Application Support",
            "Blackmagic Design",
            "DaVinci Resolve",
            "Fusion",
            "Scripts",
        )
    elif platform == "win32":
        base = os.path.join(
            os.environ.get("APPDATA", os.path.join(home, "AppData", "Roaming")),
            "Blackmagic Design",
            "DaVinci Resolve",
            "Support",
            "Fusion",
            "Scripts",
        )
    else:
        base = os.path.join(home, ".local", "share", "DaVinciResolve", "Fusion", "Scripts")
    return os.path.join(base, "Edit")


def install(target_scripts: Optional[str] = None, target_lib: Optional[str] = None) -> List[str]:
    scripts = target_scripts or scripts_dir()
    lib = target_lib or os.path.join(data_dir(), "resolve-plugin")
    os.makedirs(scripts, exist_ok=True)
    dest_pkg = os.path.join(lib, "multicam_resolve")
    if os.path.isdir(dest_pkg):
        shutil.rmtree(dest_pkg)
    shutil.copytree(HERE, dest_pkg, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    launcher = os.path.join(os.path.dirname(HERE), SCRIPT_NAME)
    shutil.copy2(launcher, os.path.join(scripts, SCRIPT_NAME))
    return [os.path.join(scripts, SCRIPT_NAME), dest_pkg]


def uninstall(target_scripts: Optional[str] = None, target_lib: Optional[str] = None) -> List[str]:
    removed = []
    script = os.path.join(target_scripts or scripts_dir(), SCRIPT_NAME)
    pkg = os.path.join(target_lib or os.path.join(data_dir(), "resolve-plugin"), "multicam_resolve")
    if os.path.exists(script):
        os.remove(script)
        removed.append(script)
    if os.path.isdir(pkg):
        shutil.rmtree(pkg)
        removed.append(pkg)
    return removed


if __name__ == "__main__":
    done = uninstall() if "--uninstall" in sys.argv else install()
    print("\n".join(done) or "nothing to do")
