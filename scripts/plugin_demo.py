"""Run the NLE-plugin flow against the engine, like a Premiere/Resolve panel would
(PLUGIN_PLAN PL2 "done when").

    uv run python scripts/plugin_demo.py host.mp4 guest.mp4 --wide wide.mp4 [--start]

1. finds the engine through ``engine.json`` (``--start``: starts a headless one),
2. handshake -> POST /sessions -> PATCH setup -> POST run,
3. follows the SSE events until ``plan_ready``,
4. fetches the EditPlan and writes it, plus an FCPXML (the import fallback), next
   to the first clip, and prints a summary.

``--synced`` sends the clips as already synced at frame 0 (skips audio sync).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import httpx

from multicam_api.config import Settings
from multicam_api.discovery import EngineInfo, read_engine_file

P = "/api/plugin/v1"


def find_engine(data_dir: Path, start: bool) -> EngineInfo:
    info = read_engine_file(data_dir)
    if info is not None or not start:
        if info is None:
            sys.exit(f"no engine running (no engine.json in {data_dir}); use --start")
        return info
    print("starting a headless engine ...")
    data_dir.mkdir(parents=True, exist_ok=True)
    with (data_dir / "engine-headless.log").open("ab") as log:
        subprocess.Popen(
            [sys.executable, "-m", "multicam_api.main", "--headless", "--data-dir", str(data_dir)],
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            start_new_session=True,
        )
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        info = read_engine_file(data_dir)
        if info is not None:
            try:
                httpx.get(f"{info.base_url}/api/system/health", timeout=2).raise_for_status()
                return info
            except httpx.HTTPError:
                pass
        time.sleep(0.3)
    sys.exit("the engine did not start in 60 s")


def check(resp: httpx.Response) -> Any:
    if resp.status_code >= 400:
        try:
            err = resp.json()
            sys.exit(f"{err.get('code')}: {err.get('message')}  ({err.get('hint', '')})")
        except ValueError:
            resp.raise_for_status()
    return resp.json()


def follow(client: httpx.Client, url: str) -> dict[str, Any]:
    event = "message"
    with client.stream("GET", url, timeout=None) as stream:
        for line in stream.iter_lines():
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("data:"):
                data: dict[str, Any] = json.loads(line[5:])
                if event == "progress":
                    print(
                        f"\r  {data['progress']:6.1%}  {data['stage']:<14} "
                        f"{(data['message'] or '')[:50]:<50}",
                        end="",
                        flush=True,
                    )
                elif event == "plan_ready":
                    print()
                    return data
                elif event == "error":
                    print()
                    sys.exit(f"{data['code']}: {data['message']}  ({data['hint']})")
    sys.exit("event stream ended without a plan")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="+", help="speaker cameras (the first is the reference)")
    parser.add_argument("--wide", action="append", default=[], help="a wide camera")
    parser.add_argument("--mic", action="append", default=[], help="a sound-only mic file")
    parser.add_argument("--data-dir", type=Path, default=None)
    parser.add_argument("--start", action="store_true", help="start a headless engine if needed")
    parser.add_argument("--synced", action="store_true", help="clips are already in sync")
    parser.add_argument("--method", default="stacked_enable")
    parser.add_argument("--preset", default="balanced")
    parser.add_argument("--fps", default="30000/1001", help="host sequence rate")
    parser.add_argument("--size", default="1920x1080", help="host sequence size")
    args = parser.parse_args()

    info = find_engine(args.data_dir or Settings.from_env().data_dir, args.start)
    num, _, den = args.fps.partition("/")
    width, height = (int(v) for v in args.size.lower().split("x"))
    clips = [
        *({"path": str(Path(f).resolve()), "kind": "video"} for f in [*args.files, *args.wide]),
        *({"path": str(Path(f).resolve()), "kind": "audio"} for f in args.mic),
    ]
    headers = {"X-Multicam-Token": info.token}
    with httpx.Client(base_url=info.base_url, headers=headers, timeout=60) as client:
        hs = check(client.get(f"{P}/handshake"))
        print(f"engine {hs['engine_version']}, plugin api {hs['api_version']}")
        session = check(
            client.post(
                f"{P}/sessions",
                json={
                    "host": {"app": "premiere", "version": "demo", "os": ""},
                    "host_sequence_id": "plugin-demo:"
                    + hashlib.sha1("|".join(c["path"] for c in clips).encode()).hexdigest(),
                    "sequence": {
                        "fps": {"num": int(num), "den": int(den or 1)},
                        "width": width,
                        "height": height,
                    },
                    "already_synced": args.synced,
                    "clips": clips,
                },
            )
        )
        print(f"session {session['id']} ({'reused' if session['reused'] else 'new'})")
        wide = {str(Path(w).resolve()) for w in args.wide}
        roles = [
            {"clip_id": c["clip_id"], "role": "wide" if c["path"] in wide else c["role"]}
            for c in session["clips"]
        ]
        check(
            client.patch(
                f"{P}/sessions/{session['id']}/setup",
                json={"roles": roles, "preset": args.preset, "method": args.method},
            )
        )
        run = check(client.post(f"{P}/sessions/{session['id']}/run", json={}))
        summary = follow(client, run["events_url"])
        print(
            f"plan v{summary['cutlist_version']}: {summary['cuts']} cuts, "
            f"{summary['low_confidence_cuts']} to check"
        )
        plan = check(client.get(f"{P}/sessions/{session['id']}/editplan"))
        out = Path(args.files[0]).resolve().with_suffix(".editplan.json")
        out.write_text(json.dumps(plan, indent=2), encoding="utf-8")
        exp = check(client.get(f"{P}/sessions/{session['id']}/export?format=fcpxml"))
        print(f"EditPlan: {out}")
        print(f"FCPXML:   {exp['path']}")
        for warning in plan["warnings"]:
            print(f"warning: {warning}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
