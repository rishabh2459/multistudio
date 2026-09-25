"""Fixtures for API tests: a running app (real queue, temp data folder) and media."""

from __future__ import annotations

import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from fastapi.testclient import TestClient

from multicam_api.app import create_app
from multicam_api.config import Settings

from ..media_factory import write_clip
from ..synth import Turn, conversation_mics

SR = 8000
FINISHED = ("succeeded", "failed", "cancelled")


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(data_dir=tmp_path / "data", sse_interval=0.05)


@pytest.fixture
def api(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as client:
        yield client


@dataclass(frozen=True)
class Recording:
    cam1: Path
    cam2: Path  # started 1 s before cam1
    wide: Path  # 25 fps, started 0.5 s after cam1
    turns: list[Turn]


@pytest.fixture(scope="session")
def recording(tmp_path_factory: pytest.TempPathFactory, ffmpeg: str) -> Recording:
    folder = tmp_path_factory.mktemp("recording")
    turns, mics = conversation_mics(40, SR, gains=(1.0, 0.35), seed=21)
    write_clip(ffmpeg, folder / "cam1.mp4", mics[0], SR)
    write_clip(ffmpeg, folder / "cam2.mp4", np.concatenate([np.zeros(SR), mics[1]]), SR)
    wide = mics[0] * 0.5 + mics[1] * 1.2
    write_clip(ffmpeg, folder / "wide.mp4", wide[SR // 2 :], SR, fps="25")
    return Recording(folder / "cam1.mp4", folder / "cam2.mp4", folder / "wide.mp4", turns)


def wait(client: TestClient, job_id: str, timeout: float = 120.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job: dict[str, Any] = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in FINISHED:
            return job
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} did not finish in {timeout} s")


def new_project(client: TestClient, name: str = "Episode") -> str:
    resp = client.post("/api/projects", json={"name": name})
    assert resp.status_code == 201, resp.text
    project_id: str = resp.json()["id"]
    return project_id


def add_clip(client: TestClient, project_id: str, path: Path, **extra: Any) -> dict[str, Any]:
    resp = client.post(f"/api/projects/{project_id}/clips", json={"path": str(path), **extra})
    assert resp.status_code == 201, resp.text
    clip: dict[str, Any] = resp.json()
    return clip


def start_job(client: TestClient, project_id: str, kind: str, **params: Any) -> dict[str, Any]:
    resp = client.post(f"/api/projects/{project_id}/jobs", json={"kind": kind, "params": params})
    assert resp.status_code == 202, resp.text
    job: dict[str, Any] = resp.json()
    return job
