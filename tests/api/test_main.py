"""The server as the desktop app runs it: separate process, any free port,
stops cleanly when the app closes its stdin."""

import io
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import httpx

from multicam_api.main import watch_stream


def test_watch_stream_calls_back_at_eof() -> None:
    closed = threading.Event()
    watch_stream(io.BytesIO(b"some bytes"), closed.set).join(timeout=5)
    assert closed.is_set()


def test_sidecar_lifecycle(tmp_path: Path) -> None:
    env = {**os.environ, "MULTICAM_API_TOKEN": "t0k", "MULTICAM_CORS": "app://multicam"}
    proc = subprocess.Popen(
        [sys.executable, "-m", "multicam_api.main", "--port", "0", "--watch-stdin",
         "--data-dir", str(tmp_path / "data"), "--log-level", "warning"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, env=env,
    )  # fmt: skip
    try:
        assert proc.stdout is not None and proc.stdin is not None
        line = proc.stdout.readline().decode()
        assert line.startswith("MULTICAM_API_READY port=")
        base = f"http://127.0.0.1:{int(line.split('=')[1])}"
        deadline = time.monotonic() + 30
        while True:
            try:
                if httpx.get(f"{base}/api/system/health").status_code == 200:
                    break
            except httpx.TransportError:
                pass
            assert time.monotonic() < deadline, "server did not come up"
            time.sleep(0.1)
        headers = {"Origin": "app://multicam", "X-Multicam-Token": "t0k"}
        resp = httpx.get(f"{base}/api/projects", headers=headers)
        assert resp.status_code == 200
        assert resp.headers["access-control-allow-origin"] == "app://multicam"
        assert httpx.get(f"{base}/api/projects").status_code == 401

        proc.stdin.close()  # what the app does on quit (and the OS on a crash)
        assert proc.wait(timeout=20) == 0
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
