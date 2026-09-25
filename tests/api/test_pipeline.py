"""Phase 4 "done when": create a project, add clips, run the pipeline and get the
final video - entirely through the HTTP API. Also: SSE, caching, manual edits,
cancel, retry, missing files. Needs ffmpeg."""

import json
import shutil
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from multicam_engine.media.probe import probe

from .conftest import Recording, add_clip, new_project, start_job, wait


def _setup(api: TestClient, recording: Recording) -> tuple[str, dict[str, Any]]:
    pid = new_project(api, "Episode 1")
    clips = {
        "cam1": add_clip(api, pid, recording.cam1, speaker_label="Host"),
        "cam2": add_clip(api, pid, recording.cam2, speaker_label="Guest"),
        "wide": add_clip(api, pid, recording.wide, role="wide"),
    }
    return pid, clips


def _sse(api: TestClient, url: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    with api.stream("GET", url) as stream:
        assert stream.headers["content-type"].startswith("text/event-stream")
        for line in stream.iter_lines():
            if line.startswith("data:"):
                events.append(json.loads(line[5:]))
    return events


def test_full_pipeline_through_the_api(api: TestClient, recording: Recording) -> None:
    pid, clips = _setup(api, recording)

    auto = start_job(api, pid, "auto", vad="energy")
    events = _sse(api, f"/api/jobs/{auto['id']}/events")
    assert events[-1]["status"] == "succeeded", events[-1]
    progress = [e["progress"] for e in events]
    assert progress == sorted(progress) and progress[-1] == 1.0
    result = events[-1]["result"]
    assert result["sync"]["cached"] is False and result["decide"]["version"] == 1

    project = api.get(f"/api/projects/{pid}").json()
    by_name = {c["name"]: c for c in project["clips"]}
    assert by_name["cam2.mp4"]["sync"]["offset_samples"] / 48000 == pytest.approx(1.0, abs=0.005)
    assert by_name["wide.mp4"]["sync"]["offset_samples"] / 48000 == pytest.approx(-0.5, abs=0.005)
    assert project["cutlist_version"] == 1

    cutlist = api.get(f"/api/projects/{pid}/cutlist").json()
    segments = cutlist["cutlist"]["segments"]
    assert cutlist["source"] == "auto" and len(segments) >= 2
    used = {s["clip_id"] for s in segments}
    assert {clips["cam1"]["id"], clips["cam2"]["id"]} <= used | {clips["wide"]["id"]}

    render = start_job(api, pid, "render", preset="draft")
    done = wait(api, render["id"])
    assert done["status"] == "succeeded", done
    out = Path(done["result"]["path"])
    assert out.is_file() and done["result"]["frames"] == segments[-1]["end_frame"]
    info = probe(out)
    assert info.media.duration_frames == segments[-1]["end_frame"]
    assert (info.media.width, info.media.height) == (1280, 720)

    exports = api.get(f"/api/projects/{pid}/exports").json()
    assert len(exports) == 1 and exports[0]["exists"] and exports[0]["size_bytes"] > 0
    file = api.get(f"/api/exports/{exports[0]['id']}/file")
    assert file.status_code == 200 and file.content[4:8] == b"ftyp"
    partial = api.get(f"/api/exports/{exports[0]['id']}/file", headers={"Range": "bytes=0-99"})
    assert partial.status_code == 206 and len(partial.content) == 100

    # ---- caching: nothing changed -> every step is skipped
    again = wait(api, start_job(api, pid, "auto", vad="energy")["id"])
    assert again["result"]["sync"]["cached"] and again["result"]["analyze"]["cached"]
    assert again["result"]["decide"]["cached"] and again["result"]["decide"]["version"] == 1
    cached_render = wait(api, start_job(api, pid, "render", preset="draft")["id"])
    assert cached_render["result"]["cached"]
    assert cached_render["result"]["export_id"] == done["result"]["export_id"]

    # ---- another preset re-cuts from the stored analysis (no re-analysis)
    dynamic = wait(api, start_job(api, pid, "decide", preset="dynamic")["id"])
    assert dynamic["status"] == "succeeded"
    assert dynamic["result"]["version"] == 2 and not dynamic["result"]["cached"]
    analysis = wait(api, start_job(api, pid, "analyze", vad="energy")["id"])
    assert analysis["result"]["cached"]

    # ---- manual edit: new version; an invalid edit is refused
    edited = api.get(f"/api/projects/{pid}/cutlist").json()["cutlist"]
    edited["segments"][0]["clip_id"] = clips["wide"]["id"]
    edited["segments"][0]["source"] = "manual"
    saved = api.put(f"/api/projects/{pid}/cutlist", json={"cutlist": edited}).json()
    assert saved["version"] == 3 and saved["source"] == "manual"
    edited["segments"][1]["start_frame"] += 1  # leaves a gap
    assert api.put(f"/api/projects/{pid}/cutlist", json={"cutlist": edited}).status_code == 422
    versions = api.get(f"/api/projects/{pid}/cutlist/versions").json()
    assert [v["version"] for v in versions] == [3, 2, 1]
    assert api.get(f"/api/projects/{pid}/cutlist/versions/1").json()["source"] == "auto"


def test_retry_after_fixing_the_problem(api: TestClient, recording: Recording) -> None:
    pid = new_project(api)
    add_clip(api, pid, recording.cam1)
    failed = wait(api, start_job(api, pid, "sync")["id"])
    assert failed["status"] == "failed" and "two clips" in failed["error"]
    add_clip(api, pid, recording.cam2)
    retried = api.post(f"/api/jobs/{failed['id']}/retry").json()
    assert retried["retry_of"] == failed["id"]
    assert wait(api, retried["id"])["status"] == "succeeded"
    done = wait(api, retried["id"])
    assert api.post(f"/api/jobs/{done['id']}/retry").status_code == 409  # only failed/cancelled
    assert api.post(f"/api/jobs/{done['id']}/cancel").status_code == 409  # already finished


def test_missing_file_fails_with_relink_hint(
    api: TestClient, recording: Recording, tmp_path: Path
) -> None:
    copy = tmp_path / "cam2.mp4"
    shutil.copy(recording.cam2, copy)
    pid = new_project(api)
    add_clip(api, pid, recording.cam1)
    clip = add_clip(api, pid, copy)
    copy.unlink()
    job = wait(api, start_job(api, pid, "sync")["id"])
    assert job["status"] == "failed" and "relink" in job["error"]
    api.patch(f"/api/clips/{clip['id']}", json={"path": str(recording.cam2)})
    assert wait(api, start_job(api, pid, "sync")["id"])["status"] == "succeeded"


def test_cancel_running_and_queued_jobs(api: TestClient, recording: Recording) -> None:
    pid, _ = _setup(api, recording)
    assert wait(api, start_job(api, pid, "auto", vad="energy")["id"])["status"] == "succeeded"
    running = start_job(api, pid, "render", preset="youtube-4k")  # slow enough to catch
    queued = start_job(api, pid, "render", preset="draft")
    # Cancel the queued one right away, then the running one once it is rendering.
    cancelled_q = api.post(f"/api/jobs/{queued['id']}/cancel").json()
    assert cancelled_q["status"] == "cancelled"
    _poll_until(api, running["id"], lambda j: j["stage"].startswith("render:video"))
    assert api.post(f"/api/jobs/{running['id']}/cancel").status_code == 200
    final = wait(api, running["id"])
    assert final["status"] == "cancelled"
    assert api.get(f"/api/projects/{pid}/exports").json() == []
    retried = api.post(f"/api/jobs/{queued['id']}/retry").json()
    assert retried["params"]["preset"] == "draft"
    assert wait(api, retried["id"])["status"] == "succeeded"


def _poll_until(api: TestClient, job_id: str, stop: Any, timeout: float = 120) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job: dict[str, Any] = api.get(f"/api/jobs/{job_id}").json()
        if stop(job) or job["status"] in ("succeeded", "failed", "cancelled"):
            return job
        time.sleep(0.05)
    raise AssertionError("timed out")


def test_delete_project_with_running_job_is_refused(api: TestClient, recording: Recording) -> None:
    pid, _ = _setup(api, recording)
    job = start_job(api, pid, "sync")
    resp = api.delete(f"/api/projects/{pid}")
    if resp.status_code == 409:  # still queued/running (usual case)
        assert "cancel" in resp.json()["detail"]
        wait(api, job["id"])
        assert api.delete(f"/api/projects/{pid}").status_code == 204


def test_project_event_stream(api: TestClient, recording: Recording) -> None:
    pid = new_project(api)
    add_clip(api, pid, recording.cam1)
    job = start_job(api, pid, "probe")
    wait(api, job["id"])
    events = _sse(api, f"/api/projects/{pid}/events?follow=false")
    assert [(e["id"], e["status"]) for e in events] == [(job["id"], "succeeded")]
