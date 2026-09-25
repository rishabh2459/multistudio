"""Write the generated contract files.

* ``schemas/multicam.schema.json`` - JSON Schema of the engine data model
  (source of the TypeScript types in ``packages/types``)
* ``schemas/openapi.json`` - OpenAPI description of the local HTTP API
  (source of the UI's API client, Phase 5)

Usage:
    uv run python scripts/export_schemas.py          # regenerate
    uv run python scripts/export_schemas.py --check  # CI: fail if out of date
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from multicam_api.app import create_app
from multicam_api.config import Settings
from multicam_engine.models.schema import render_schema

SCHEMAS = Path(__file__).resolve().parent.parent / "schemas"


def render_openapi() -> str:
    # Settings with a dummy folder: building the schema never touches the disk.
    spec = create_app(Settings(data_dir=Path("/nonexistent"))).openapi()
    spec["info"]["version"] = "0"  # keep the file stable across package versions
    return json.dumps(spec, indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="fail if a file is stale")
    args = parser.parse_args()

    outputs = {
        SCHEMAS / "multicam.schema.json": render_schema(),
        SCHEMAS / "openapi.json": render_openapi(),
    }
    stale = 0
    for path, text in outputs.items():
        if args.check:
            current = path.read_text(encoding="utf-8") if path.exists() else ""
            if current != text:
                print(f"{path} is out of date. Run: make schemas", file=sys.stderr)
                stale += 1
            else:
                print(f"{path.name} up to date")
        else:
            path.parent.mkdir(exist_ok=True)
            path.write_text(text, encoding="utf-8")
            print(f"wrote {path}")
    return 1 if stale else 0


if __name__ == "__main__":
    sys.exit(main())
