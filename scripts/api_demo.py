"""Run the whole pipeline through the HTTP API (plan Phase 4 "done when").

Start the server first:   uv run multicam-api --port 8765
Then:                     uv run python scripts/api_demo.py cam1.mp4 cam2.mp4 [wide.mp4 --wide]

Creates a project, adds the clips, runs auto (sync + who-speaks + cuts) and a
render, following live progress over Server-Sent Events, then prints where the
video is.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import httpx


def follow(client: httpx.Client, job: dict[str, Any]) -> dict[str, Any]:
    """Print progress from the SSE stream until the job finishes."""
    with client.stream("GET", f"/api/jobs/{job['id']}/events", timeout=None) as events:
        for line in events.iter_lines():
            if not line.startswith("data:"):
                continue
            job = json.loads(line[5:])
            print(
                f"\r  {job['kind']:<7} {job['progress']:6.1%}  {job['stage']:<14} "
                f"{job['message'][:50]:<50}",
                end="",
                flush=True,
            )
            if job["status"] in ("succeeded", "failed", "cancelled"):
                break
    print()
    if job["status"] != "succeeded":
        sys.exit(f"{job['kind']} {job['status']}: {job.get('error')}")
    return job


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="+", help="camera files (the first is the reference)")
    parser.add_argument("--wide", action="append", default=[], help="file that is a wide shot")
    parser.add_argument("--url", default="http://127.0.0.1:8765")
    parser.add_argument("--token", default=None, help="API token, if the server uses one")
    parser.add_argument("--preset", default="draft", help="render preset")
    args = parser.parse_args()

    headers = {"X-Multicam-Token": args.token} if args.token else {}
    with httpx.Client(base_url=args.url, headers=headers, timeout=60) as client:
        client.get("/api/system/health").raise_for_status()
        project = client.post("/api/projects", json={"name": "API demo"}).json()
        print(f"project {project['id']}")
        wide = {Path(w).resolve() for w in args.wide}
        for f in [*args.files, *args.wide]:
            path = Path(f).resolve()
            role = "wide" if path in wide else "speaker"
            r = client.post(
                f"/api/projects/{project['id']}/clips", json={"path": str(path), "role": role}
            )
            if r.status_code >= 400:
                sys.exit(f"cannot add {path.name}: {r.json()['detail']}")
            print(f"  + {path.name} ({role})")

        auto = client.post(f"/api/projects/{project['id']}/jobs", json={"kind": "auto"}).json()
        done = follow(client, auto)
        print(
            f"  cutlist v{done['result']['decide']['version']}: "
            f"{done['result']['decide']['segments']} shots"
        )

        job = client.post(
            f"/api/projects/{project['id']}/jobs",
            json={"kind": "render", "params": {"preset": args.preset}},
        ).json()
        done = follow(client, job)
        print(f"video: {done['result']['path']} ({done['result']['frames']} frames)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
