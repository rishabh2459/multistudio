"""Engine discovery for NLE plugins (PL2): engine.json, single instance, idle exit."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from multicam_api.discovery import (
    Activity,
    EngineInfo,
    IdleWatch,
    InstanceLock,
    engine_file,
    parse_duration,
    read_engine_file,
    remove_engine_file,
    write_engine_file,
)


def test_engine_file_round_trip(tmp_path: Path) -> None:
    info = EngineInfo(port=47811, token="abc", pid=os.getpid(), api="1.0.0")
    path = write_engine_file(tmp_path, info)
    assert json.loads(path.read_text())["token"] == "abc"
    if sys.platform != "win32":
        assert path.stat().st_mode & 0o077 == 0  # token file is private
    assert read_engine_file(tmp_path) == info
    assert info.base_url == "http://127.0.0.1:47811"
    assert not remove_engine_file(tmp_path, pid=os.getpid() + 1)  # not ours: kept
    assert remove_engine_file(tmp_path)
    assert read_engine_file(tmp_path) is None


def test_stale_or_broken_engine_file(tmp_path: Path) -> None:
    write_engine_file(tmp_path, EngineInfo(port=1, token="x", pid=2**22 + 12345, api="1.0.0"))
    assert read_engine_file(tmp_path) is None  # that pid is not running
    engine_file(tmp_path).write_text("{not json")
    assert read_engine_file(tmp_path) is None


def test_instance_lock_is_exclusive(tmp_path: Path) -> None:
    first, second = InstanceLock(tmp_path), InstanceLock(tmp_path)
    assert first.acquire() and first.held
    assert not second.acquire()
    first.release()
    assert second.acquire()
    second.release()


def test_idle_watch() -> None:
    now = [0.0]
    activity = Activity(clock=lambda: now[0])
    fired: list[bool] = []
    busy = [False]
    watch = IdleWatch(activity, 60, lambda: busy[0], lambda: fired.append(True))
    now[0] = 30
    assert not watch.check()
    activity.begin()  # a long request (SSE) in flight is never idle
    now[0] = 500
    assert not watch.check()
    activity.end()
    now[0] = 540
    assert not watch.check()
    now[0] = 561
    busy[0] = True  # a job is running
    assert not watch.check()
    busy[0] = False
    assert watch.check() and fired == [True]


@pytest.mark.parametrize(
    ("text", "seconds"), [("30m", 1800), ("90s", 90), ("1h", 3600), ("45", 45), ("0", 0)]
)
def test_parse_duration(text: str, seconds: float) -> None:
    assert parse_duration(text) == seconds


def _start(data: Path, *extra: str) -> subprocess.Popen[bytes]:
    env = {k: v for k, v in os.environ.items() if k != "MULTICAM_API_TOKEN"}
    return subprocess.Popen(
        [sys.executable, "-m", "multicam_api.main", "--headless", "--port", "0",
         "--data-dir", str(data), "--log-level", "warning", *extra],
        stdout=subprocess.PIPE, env=env,
    )  # fmt: skip


def test_headless_engine_lifecycle(tmp_path: Path) -> None:
    data = tmp_path / "data"
    proc = _start(data, "--idle-exit", "3s")
    try:
        assert proc.stdout is not None
        line = proc.stdout.readline().decode()
        assert line.startswith("MULTICAM_API_READY port="), line
        port = int(line.split("=")[1])
        info = read_engine_file(data)
        assert info is not None and info.port == port and info.pid == proc.pid
        assert info.mode == "headless" and len(info.token) >= 20

        url = f"{info.base_url}/api/plugin/v1/handshake"
        deadline = time.monotonic() + 30
        while True:
            try:
                resp = httpx.get(url, headers={"X-Multicam-Token": info.token})
                break
            except httpx.TransportError:
                assert time.monotonic() < deadline
                time.sleep(0.1)
        assert resp.status_code == 200 and resp.json()["pid"] == proc.pid
        assert httpx.get(url).status_code == 401  # token required

        # A second start (multicam://start pressed again) reports the running one.
        second = _start(data)
        out, _ = second.communicate(timeout=30)
        assert second.returncode == 0
        assert out.decode().strip() == f"MULTICAM_API_RUNNING port={port}"

        # Nothing happens for 3 s -> it stops by itself and cleans up.
        assert proc.wait(timeout=30) == 0
        assert not engine_file(data).exists()
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()


def test_shutdown_endpoint(tmp_path: Path) -> None:
    data = tmp_path / "data"
    proc = _start(data, "--idle-exit", "0")
    try:
        assert proc.stdout is not None
        assert proc.stdout.readline().decode().startswith("MULTICAM_API_READY")
        info = read_engine_file(data)
        assert info is not None
        url = f"{info.base_url}/api/system/shutdown"
        deadline = time.monotonic() + 30
        while True:
            try:
                assert httpx.post(url).status_code == 401  # needs the token
                break
            except httpx.TransportError:
                assert time.monotonic() < deadline
                time.sleep(0.1)
        resp = httpx.post(url, headers={"X-Multicam-Token": info.token})
        assert resp.status_code == 202, resp.text
        assert proc.wait(timeout=30) == 0
        assert not engine_file(data).exists()
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()


def test_shutdown_not_available_in_process(api: object) -> None:
    from fastapi.testclient import TestClient

    assert isinstance(api, TestClient)
    assert api.post("/api/system/shutdown").status_code == 403
