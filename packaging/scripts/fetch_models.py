"""Download model files listed in packaging/models/manifest.json.

* Files are verified against the pinned SHA-256 in the manifest.
* An entry with ``"sha256": null`` is not pinned yet: pass ``--pin`` to download it
  once, record its hash in the manifest, and commit the manifest. After that, every
  download on every machine is verified against that hash.

Usage:
    uv run python packaging/scripts/fetch_models.py            # fetch + verify
    uv run python packaging/scripts/fetch_models.py --pin      # also pin unpinned entries
    uv run python packaging/scripts/fetch_models.py --only silero-vad
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
from pathlib import Path
from typing import Any

MODELS_DIR = Path(__file__).resolve().parent.parent / "models"
MANIFEST = MODELS_DIR / "manifest.json"
CHUNK = 1 << 20


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(CHUNK):
            h.update(chunk)
    return h.hexdigest()


def download(url: str, dest: Path) -> None:
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(url, timeout=60) as resp, tmp.open("wb") as out:
        while chunk := resp.read(CHUNK):
            out.write(chunk)
    tmp.replace(dest)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pin", action="store_true", help="record hashes for unpinned entries")
    parser.add_argument("--only", help="fetch a single model by name")
    args = parser.parse_args()

    manifest: dict[str, Any] = json.loads(MANIFEST.read_text(encoding="utf-8"))
    changed = False
    failures = 0

    for entry in manifest["models"]:
        name, expected = entry["name"], entry["sha256"]
        if args.only and name != args.only:
            continue
        dest = MODELS_DIR / entry["dest"]

        if expected is None and not args.pin:
            print(f"SKIP {name}: not pinned (run with --pin once, then commit the manifest)")
            continue

        if not (dest.exists() and expected and sha256_of(dest) == expected):
            print(f"GET  {name} <- {entry['url']}")
            try:
                download(entry["url"], dest)
            except OSError as exc:
                failures += 1
                print(f"FAIL {name}: download error: {exc}", file=sys.stderr)
                continue

        actual = sha256_of(dest)
        if expected is None:
            entry["sha256"] = actual
            changed = True
            print(f"PIN  {name}: sha256={actual}")
        elif actual != expected:
            failures += 1
            dest.unlink()
            print(f"FAIL {name}: hash mismatch (got {actual}), file removed", file=sys.stderr)
            continue
        print(f"OK   {name} ({dest.stat().st_size / 1e6:.1f} MB, {entry['license']})")

    if changed:
        MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        print(f"\nUpdated {MANIFEST} — review and commit it.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
