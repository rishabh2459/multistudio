"""Plugin API v1 (PL2): the full flow an NLE plugin runs, plus the stable error codes.

handshake -> POST /sessions -> PATCH setup -> POST run -> SSE events -> editplan /
export -> feedback. Needs ffmpeg."""

from __future__ import annotations

import dataclasses
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from multicam_api.app import create_app
from multicam_api.config import Settings
from multicam_engine.editplan import EditPlan, PlanMethod

from .conftest import Recording, wait

P = "/api/plugin/v1"


def _clips(recording: Recording, **synced: dict[str, int]) -> list[dict[str, Any]]:
    clips: list[dict[str, Any]] = []
    for name, path in (
        ("cam1", recording.cam1),
        ("cam2", recording.cam2),
        ("wide", recording.wide),
    ):
        clips.append(
            {
                "path": str(path),
                "host_ref": f"pp:{name}",
                "track": len(clips) + 1,
                **synced.get(name, {}),
            }
        )
    return clips


def _create(api: TestClient, recording: Recording, **extra: Any) -> dict[str, Any]:
    body = {
        "host": {"app": "premiere", "version": "26.1", "os": "mac"},
        "host_sequence_id": "seq-1",
        "sequence": {
            "fps": {"num": 30000, "den": 1001},
            "width": 1280,
            "height": 720,
            "name": "Ep 1",
        },
        "clips": _clips(recording),
        **extra,
    }
    resp = api.post(f"{P}/sessions", json=body)
    assert resp.status_code in (200, 201), resp.text
    out: dict[str, Any] = resp.json()
    return out


def _setup_roles(api: TestClient, session: dict[str, Any], **extra: Any) -> dict[str, Any]:
    ids = {Path(c["path"]).stem: c["clip_id"] for c in session["clips"]}
    resp = api.patch(
        f"{P}/sessions/{session['id']}/setup",
        json={
            "roles": [
                {"clip_id": ids["cam1"], "role": "speaker", "speaker_label": "Host"},
                {"clip_id": ids["cam2"], "role": "speaker", "speaker_label": "Guest"},
                {"clip_id": ids["wide"], "role": "wide"},
            ],
            **extra,
        },
    )
    assert resp.status_code == 200, resp.text
    out: dict[str, Any] = resp.json()
    return out


def _sse(api: TestClient, url: str) -> list[tuple[str, dict[str, Any]]]:
    events: list[tuple[str, dict[str, Any]]] = []
    name = "message"
    with api.stream("GET", url) as stream:
        assert stream.headers["content-type"].startswith("text/event-stream")
        for line in stream.iter_lines():
            if line.startswith("event:"):
                name = line[6:].strip()
            elif line.startswith("data:"):
                events.append((name, json.loads(line[5:])))
    return events


def _error(resp: Any, status: int, code: str) -> dict[str, Any]:
    assert resp.status_code == status, resp.text
    body: dict[str, Any] = resp.json()
    assert body["code"] == code and body["message"], body
    assert set(body) == {"code", "message", "hint"}
    return body


def test_handshake(api: TestClient) -> None:
    hs = api.get(f"{P}/handshake").json()
    assert hs["api_version"].startswith("1.")
    assert {"editplan", "already_synced", "export:fcpxml", "method:stacked_enable"} <= set(
        hs["capabilities"]
    )
    assert hs["licence"]["status"] == "dev" and hs["pid"] > 0
    assert set(hs["models"]) == {"vad", "face", "asr"}


def test_full_plugin_flow(api: TestClient, recording: Recording) -> None:
    session = _create(api, recording)
    sid = session["id"]
    assert session["state"] == "setup" and not session["reused"]
    assert [c["host_ref"] for c in session["clips"]] == ["pp:cam1", "pp:cam2", "pp:wide"]
    assert session["method"] == "stacked_enable"

    # no plan yet
    _error(api.get(f"{P}/sessions/{sid}/editplan"), 409, "no_plan")

    session = _setup_roles(api, session, preset="balanced", method="cuts")
    assert session["method"] == "cuts"
    assert [c["role"] for c in session["clips"]] == ["speaker", "speaker", "wide"]

    run = api.post(f"{P}/sessions/{sid}/run", json={"vad": "energy"})
    assert run.status_code == 202, run.text
    events = _sse(api, run.json()["events_url"])
    names = [n for n, _ in events]
    assert names[0] == "progress" and names[-1] == "plan_ready", events[-3:]
    summary = events[-1][1]
    assert summary["cutlist_version"] == 1 and summary["cuts"] >= 1

    state = api.get(f"{P}/sessions/{sid}").json()
    assert state["state"] == "ready" and state["plan"]["cuts"] == summary["cuts"]
    assert all(c["synced"] for c in state["clips"])

    raw = api.get(f"{P}/sessions/{sid}/editplan", params={"host": "premiere"})
    assert raw.status_code == 200, raw.text
    plan = EditPlan.model_validate(raw.json())
    assert plan.method is PlanMethod.CUTS and plan.host.value == "premiere"
    assert plan.cut_count == summary["cuts"]
    assert {m.host_ref for m in plan.media} == {"pp:cam1", "pp:cam2", "pp:wide"}
    assert plan.sequence.name == "Ep 1 - Auto Edit v1"
    assert plan.video_events[0].start == 0
    assert plan.video_events[-1].end == plan.sequence.duration_frames
    assert len(plan.video_tracks) == 3
    for track in plan.video_tracks:  # stacked: live pieces are exactly the events
        for piece in track.pieces:
            if piece.enabled:
                assert any(
                    e.clip_id == piece.clip_id and e.start <= piece.start < e.end
                    for e in plan.video_events
                )

    # another method on request, same cuts
    stacked = EditPlan.model_validate(
        api.get(f"{P}/sessions/{sid}/editplan", params={"method": "stacked_enable"}).json()
    )
    assert stacked.method is PlanMethod.STACKED_ENABLE
    assert [e.start for e in stacked.video_events] == [e.start for e in plan.video_events]

    # XML fallback (Rule C)
    for fmt, check in (("fcpxml", "fcpxml"), ("xmeml", "xmeml")):
        exp = api.get(f"{P}/sessions/{sid}/export", params={"format": fmt})
        assert exp.status_code == 200, exp.text
        path = Path(exp.json()["path"])
        assert path.is_file() and ET.parse(path).getroot().tag == check
    multi = api.get(f"{P}/sessions/{sid}/export", params={"format": "fcpxml", "method": "multicam"})
    assert multi.status_code == 200, multi.text
    root = ET.parse(multi.json()["path"]).getroot()
    assert root.find("resources/media/multicam") is not None
    assert len(root.findall("library/event/project/sequence/spine/mc-clip")) == summary["cuts"] + 1
    edl = api.get(f"{P}/sessions/{sid}/export", params={"format": "edl"}).json()
    assert Path(edl["path"]).read_text().startswith("TITLE:")
    _error(api.get(f"{P}/sessions/{sid}/export", params={"format": "aaf"}), 422, "not_available")

    # re-cut with another preset: only "decide" runs
    api.patch(f"{P}/sessions/{sid}/setup", json={"preset": "punchy"})
    redo = api.post(f"{P}/sessions/{sid}/run", json={"steps": ["decide"]})
    assert redo.status_code == 202, redo.text
    job = wait(api, redo.json()["job_id"])
    assert job["status"] == "succeeded", job
    assert api.get(f"{P}/sessions/{sid}").json()["plan"]["cutlist_version"] == 2
    old = api.get(f"{P}/sessions/{sid}/editplan", params={"version": 1}).json()
    assert old["cutlist_version"] == 1

    # same host sequence again -> same session (analysis cache reused)
    again = _create(api, recording)
    assert again["id"] == sid and again["reused"]

    # editor's final timeline back
    fb = api.post(f"{P}/sessions/{sid}/feedback", json={"plan": raw.json(), "note": "ok"})
    assert fb.status_code == 200, fb.text
    assert fb.json()["cuts_kept"] == fb.json()["cuts_auto"] == summary["cuts"]
    assert Path(fb.json()["path"]).is_file()

    # Premiere multicam: the stacked edit + a multicam source sequence in one xmeml
    mc = api.get(f"{P}/sessions/{sid}/export", params={"format": "xmeml", "method": "multicam"})
    assert mc.status_code == 200, mc.text
    seqs = ET.parse(mc.json()["path"]).getroot().findall("project/children/sequence")
    assert [s.findtext("name", "").endswith("Multicam Source") for s in seqs] == [False, True]

    # social clips: one sequence per aspect, each with an xmeml to import
    social = api.post(
        f"{P}/sessions/{sid}/social",
        json={"in_frame": 30, "out_frame": 330, "aspects": ["9:16", "1:1"], "name": "Clip 1"},
    )
    assert social.status_code == 200, social.text
    clips = social.json()["clips"]
    assert [c["aspect"] for c in clips] == ["9:16", "1:1"]
    assert [(c["width"], c["height"]) for c in clips] == [(1080, 1920), (1080, 1080)]
    assert [c["name"] for c in clips] == ["Clip 1 - 9x16", "Clip 1 - 1x1"]
    for c in clips:
        assert c["duration_frames"] == 300 and c["render_path"].endswith(".mp4")
        xml = ET.parse(c["xml_path"]).getroot()
        assert xml.findtext("sequence/media/video/format/samplecharacteristics/width") == "1080"
        assert xml.find(".//effect[effectid='basic']") is not None  # framed for the aspect
    _error(
        api.post(
            f"{P}/sessions/{sid}/social",
            json={"in_frame": 50, "out_frame": 40, "aspects": ["9:16"]},
        ),
        422,
        "invalid_request",
    )
    _error(
        api.post(
            f"{P}/sessions/{sid}/social",
            json={
                "in_frame": 0,
                "out_frame": 90,
                "aspects": ["9:16"],
                "watermark": {"path": "/nope.png"},
            },
        ),
        422,
        "media_offline",
    )


def test_jump_cuts_review_and_ripple(api: TestClient, recording: Recording) -> None:
    session = _create(api, recording, host_sequence_id="seq-jumpcuts")
    sid = session["id"]
    _error(api.post(f"{P}/sessions/{sid}/jumpcuts", json={}), 409, "no_plan")
    _setup_roles(api, session)
    run = api.post(f"{P}/sessions/{sid}/run", json={"vad": "energy"}).json()
    assert wait(api, run["job_id"])["status"] == "succeeded"
    _error(api.get(f"{P}/sessions/{sid}/editplan", params={"ripple": True}), 409, "no_plan")

    jc = api.post(
        f"{P}/sessions/{sid}/jumpcuts",
        json={"mode": "db", "threshold_db": -40, "min_silence_s": 0.3, "pad_s": 0.05},
    )
    assert jc.status_code == 202, jc.text
    assert jc.json()["kind"] == "jumpcut"
    events = _sse(api, jc.json()["events_url"])
    assert events[-1][0] == "plan_ready", events[-3:]
    job = wait(api, jc.json()["job_id"])
    assert job["status"] == "succeeded", job
    assert job["result"]["removals"] >= 1  # at least the silence before the first word

    rem = api.get(f"{P}/sessions/{sid}/removals").json()
    assert rem["cutlist_version"] == job["result"]["version"]
    items = rem["removals"]
    assert items and all(r["kind"] == "silence" and r["approved"] for r in items)
    assert rem["removed_frames"] == sum(r["end"] - r["start"] for r in items)

    # reject one -> new version, fewer frames removed
    patched = api.patch(f"{P}/sessions/{sid}/removals", json={"reject": [0]}).json()
    assert patched["cutlist_version"] == rem["cutlist_version"] + 1
    assert not patched["removals"][0]["approved"]
    _error(
        api.patch(f"{P}/sessions/{sid}/removals", json={"approve": [999]}), 422, "invalid_request"
    )
    patched = api.patch(f"{P}/sessions/{sid}/removals", json={"all": True}).json()
    assert all(r["approved"] for r in patched["removals"])

    full = EditPlan.model_validate(api.get(f"{P}/sessions/{sid}/editplan").json())
    cut = EditPlan.model_validate(
        api.get(f"{P}/sessions/{sid}/editplan", params={"ripple": True}).json()
    )
    assert cut.rippled and not cut.removals
    removed = patched["removed_frames"]
    assert cut.sequence.duration_frames == full.sequence.duration_frames - removed
    assert cut.sequence.name.endswith(" - Jump Cuts")
    exp = api.get(f"{P}/sessions/{sid}/export", params={"format": "xmeml", "ripple": True})
    assert exp.status_code == 200, exp.text
    assert exp.json()["path"].endswith("-jumpcuts.xml")
    root = ET.parse(exp.json()["path"]).getroot()
    assert root.findtext("sequence/duration") == str(cut.sequence.duration_frames)

    # speech detection mode works on the same analysis
    vad = api.post(f"{P}/sessions/{sid}/jumpcuts", json={"mode": "vad", "min_silence_s": 0.3})
    assert wait(api, vad.json()["job_id"])["status"] == "succeeded"
    hs = api.get(f"{P}/handshake").json()
    assert {"jump_cuts", "ripple", "social"} <= set(hs["capabilities"])


def test_already_synced_skips_audio_sync(api: TestClient, recording: Recording) -> None:
    # Host sequence at 30 fps: cam2 started 1 s early (trimmed by 30 frames),
    # the wide started 0.5 s late (placed at frame 15).
    clips = _clips(
        recording,
        cam2={"in_frame": 30},
        wide={"record_start_frame": 15},
    )
    session = _create(
        api,
        recording,
        host_sequence_id="seq-synced",
        already_synced=True,
        clips=clips,
        sequence={"fps": {"num": 30, "den": 1}, "width": 1280, "height": 720},
    )
    assert session["already_synced"] and all(c["synced"] for c in session["clips"])
    _setup_roles(api, session)
    run = api.post(f"{P}/sessions/{session['id']}/run", json={"vad": "energy"}).json()
    job = wait(api, run["job_id"])
    assert job["status"] == "succeeded", job
    assert job["result"]["sync"]["skipped"]

    project = api.get(f"/api/projects/{session['project_id']}").json()
    offsets = {c["name"]: c["sync"]["offset_samples"] / 48000 for c in project["clips"]}
    assert offsets["cam1.mp4"] == 0
    assert offsets["cam2.mp4"] == pytest.approx(1.0, abs=0.001)
    assert offsets["wide.mp4"] == pytest.approx(-0.5, abs=0.001)


def test_sound_only_mic_clip(
    api: TestClient, recording: Recording, tmp_path: Path, ffmpeg: str
) -> None:
    import subprocess

    mic = tmp_path / "mic.wav"
    subprocess.run(
        [ffmpeg, "-v", "error", "-y", "-i", str(recording.cam1), "-vn", str(mic)], check=True
    )
    clips = [*_clips(recording), {"path": str(mic), "kind": "audio"}]
    session = _create(api, recording, host_sequence_id="seq-mic", clips=clips)
    by_name = {Path(c["path"]).name: c for c in session["clips"]}
    assert by_name["mic.wav"]["kind"] == "audio" and by_name["mic.wav"]["role"] == "mic"
    assert all(cam["clip_id"] != by_name["mic.wav"]["clip_id"] for cam in session["cameras"])


def test_error_codes(api: TestClient, recording: Recording, tmp_path: Path) -> None:
    missing = "00000000-0000-0000-0000-000000000000"
    _error(api.get(f"{P}/sessions/{missing}"), 404, "not_found")
    _error(api.post(f"{P}/sessions", json={"host": {"app": "premiere"}}), 422, "invalid_request")

    twice = _clips(recording)
    twice[1]["path"] = twice[0]["path"]
    body = {
        "host": {"app": "resolve"},
        "sequence": {"fps": {"num": 25, "den": 1}, "width": 1920, "height": 1080},
        "clips": twice,
    }
    _error(api.post(f"{P}/sessions", json=body), 422, "invalid_request")

    body["clips"] = [{"path": str(recording.cam1), "kind": "audio"}]
    _error(api.post(f"{P}/sessions", json=body), 422, "setup_required")

    gone = tmp_path / "gone.mp4"
    body["clips"] = [{"path": str(recording.cam1)}, {"path": str(gone)}]
    session = api.post(f"{P}/sessions", json=body).json()
    assert any("offline" in w for w in session["warnings"])
    _error(api.post(f"{P}/sessions/{session['id']}/run", json={}), 422, "media_offline")

    good = _create(api, recording, host_sequence_id="seq-err")
    bad_layout = {
        "layout": {
            "speakers": [],
            "cameras": [
                {
                    "clip_id": good["clips"][0]["clip_id"],
                    "shot": "solo",
                    "covers": ["11111111-1111-1111-1111-111111111111"],
                }
            ],
        }
    }
    _error(api.patch(f"{P}/sessions/{good['id']}/setup", json=bad_layout), 422, "setup_required")
    _error(
        api.post(f"{P}/sessions/{good['id']}/run", json={"steps": ["sync", "decide"]}),
        422,
        "invalid_request",
    )


def test_plugin_origins_only_with_a_token(api: TestClient, settings: Settings) -> None:
    preflight = {"Origin": "null", "Access-Control-Request-Method": "GET"}
    # no token: a sandboxed page (origin "null") must not get access
    open_resp = api.options(f"{P}/handshake", headers=preflight)
    assert "access-control-allow-origin" not in open_resp.headers
    with TestClient(create_app(dataclasses.replace(settings, token="t0k"))) as secured:
        resp = secured.options(f"{P}/handshake", headers=preflight)
        assert resp.headers.get("access-control-allow-origin") == "null"
        assert secured.get(f"{P}/handshake").status_code == 401
        assert secured.get(f"{P}/handshake", headers={"X-Multicam-Token": "t0k"}).status_code == 200


def test_host_offsets_are_dropped_when_already_synced_turns_off(
    api: TestClient, recording: Recording
) -> None:
    # The host claims cam2 is 3 s early (wrong): those offsets are used as they are...
    wrong = _clips(recording, cam2={"in_frame": 90}, wide={"record_start_frame": 15})
    seq = {"fps": {"num": 30, "den": 1}, "width": 1280, "height": 720}
    session = _create(
        api, recording, host_sequence_id="seq-flip", already_synced=True, clips=wrong, sequence=seq
    )
    _setup_roles(api, session)
    job = wait(
        api, api.post(f"{P}/sessions/{session['id']}/run", json={"vad": "energy"}).json()["job_id"]
    )
    assert job["result"]["sync"]["skipped"]
    project = f"/api/projects/{session['project_id']}"
    cam2 = next(c for c in api.get(project).json()["clips"] if c["name"] == "cam2.mp4")
    assert cam2["sync"]["offset_samples"] / 48000 == pytest.approx(3.0, abs=0.001)

    # ...until the clips arrive as not synced: audio sync runs again (no stale cache).
    again = _create(
        api, recording, host_sequence_id="seq-flip", clips=_clips(recording), sequence=seq
    )
    assert again["id"] == session["id"] and not any(c["synced"] for c in again["clips"])
    job = wait(
        api, api.post(f"{P}/sessions/{session['id']}/run", json={"vad": "energy"}).json()["job_id"]
    )
    assert job["status"] == "succeeded", job
    assert not job["result"]["sync"].get("skipped")
    cam2 = next(c for c in api.get(project).json()["clips"] if c["name"] == "cam2.mp4")
    assert cam2["sync"]["offset_samples"] / 48000 == pytest.approx(1.0, abs=0.005)


def test_same_files_in_another_order_reuse_the_session(
    api: TestClient, recording: Recording
) -> None:
    first = _create(api, recording, host_sequence_id="seq-order")
    clips = list(reversed(_clips(recording)))
    second = _create(api, recording, host_sequence_id="seq-order", clips=clips)
    assert second["id"] == first["id"] and second["reused"]
    assert second["project_id"] == first["project_id"]
    refs = {Path(c["path"]).name: c["host_ref"] for c in second["clips"]}
    assert refs == {"cam1.mp4": "pp:cam1", "cam2.mp4": "pp:cam2", "wide.mp4": "pp:wide"}
