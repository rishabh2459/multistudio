"""Write schemas/multicam.schema.json from the Python data model.

Usage:
    uv run python scripts/export_schemas.py          # regenerate
    uv run python scripts/export_schemas.py --check  # CI: fail if out of date
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from multicam_engine.models.schema import render_schema

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schemas" / "multicam.schema.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="fail if the file is stale")
    args = parser.parse_args()

    text = render_schema()
    if args.check:
        current = SCHEMA_PATH.read_text(encoding="utf-8") if SCHEMA_PATH.exists() else ""
        if current != text:
            print(f"{SCHEMA_PATH} is out of date. Run: make schemas", file=sys.stderr)
            return 1
        print("schema up to date")
        return 0

    SCHEMA_PATH.parent.mkdir(exist_ok=True)
    SCHEMA_PATH.write_text(text, encoding="utf-8")
    print(f"wrote {SCHEMA_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
