"""The Resolve script lives outside the Python packages: make it importable."""

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[2] / "apps" / "plugins" / "resolve-script"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
