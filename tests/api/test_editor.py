"""Phase 7 API: timeline mapping, waveforms, preview proxies, NLE export. Needs ffmpeg."""

import base64
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from .conftest import Recording, add_clip, new_project, start_job, wait


@pytest.fixture
def edited(api: TestClient, recording: Recording) -> dict[str, object]:
    pid = new_project(api, "Episode 9")
    clips = {
        "cam1": add_clip(api, pid, recording.cam1, speaker_label="Host"),
        "cam2": add_clip(api, pid, recording.cam2, speaker_label="Guest"),
        "wide": add_clip(api, pid, recording.wide, role="wide"),
    }
    assert wait(api, start_job(api, pid, "auto", vad="energy")["id"])["status"] == "succeeded"
    return {"pid": pid, "clips": clips}


def test_timeline_mapping_and_waveform(api: TestClient, edited: dict) -> None:  # type: ignore[type-arg]
    pid, clips = edited["pid"], edited["clips"]
    tl = api.get(f"/api/projects/{pid}/timeline").json()
    assert tl["fps"] == {"num": 30000, "den": 1001}
    assert tl["duration_frames"] > 0 and tl["proxies_ready"] is False
    by_id = {c["clip_id"]: c for c in tl["clips"]}
    cam2, wide = by_id[clips["cam2"]["id"]], by_id[clips["wide"]["id"]]
    assert cam2["audio_offset_s"] == pytest.approx(1.0, abs=0.005)  # started 1 s early
    assert wide["audio_offset_s"] == pytest.approx(-0.5, abs=0.005)
    assert wide["fps"] == {"num": 25, "den": 1} and wide["speed"] == pytest.approx(1, abs=1e-4)
    # container start differs from the audio start by a few ms at most
    assert cam2["media_offset_s"] == pytest.approx(cam2["audio_offset_s"], abs=0.05)

    wf = api.get(f"/api/clips/{clips['cam1']['id']}/waveform", params={"rate": 20}).json()
    peaks = base64.b64decode(wf["peaks"])
    assert wf["rate"] == 20 and abs(len(peaks) - 40 * 20) <= 20
    assert max(peaks) > 150 and min(peaks) < max(peaks)  # speech and pauses


def test_proxies(api: TestClient, edited: dict) -> None:  # type: ignore[type-arg]
    pid, clips = edited["pid"], edited["clips"]
    cam1 = clips["cam1"]["id"]
    assert api.get(f"/api/clips/{cam1}/proxy").status_code == 404
    job = wait(api, start_job(api, pid, "proxy")["id"])
    assert job["status"] == "succeeded", job
    assert job["result"]["made"] == 3
    assert api.get(f"/api/projects/{pid}/timeline").json()["proxies_ready"] is True
    resp = api.get(f"/api/clips/{cam1}/proxy", headers={"Range": "bytes=0-99"})
    assert resp.status_code == 206 and resp.headers["content-type"] == "video/mp4"
    again = wait(api, start_job(api, pid, "proxy")["id"])
    assert again["result"]["cached"] is True


def test_nle_exports(api: TestClient, edited: dict, tmp_path: Path) -> None:  # type: ignore[type-arg]
    pid = edited["pid"]
    for fmt, ext in (("fcpxml", ".fcpxml"), ("xmeml", ".xml"), ("edl", ".edl")):
        resp = api.post(f"/api/projects/{pid}/nle-exports", json={"format": fmt})
        assert resp.status_code == 201, resp.text
        out = resp.json()
        export = out["export"]
        assert export["kind"] == fmt and export["exists"] and export["path"].endswith(f"-v1{ext}")
        text = Path(export["path"]).read_text()
        if fmt != "edl":
            ET.fromstring(text.split("\n", 2)[2])  # well-formed XML
        else:
            assert text.startswith("TITLE: Episode 9\nFCM: DROP FRAME")
        assert api.get(f"/api/exports/{export['id']}/file").status_code == 200
    kinds = {e["kind"] for e in api.get(f"/api/projects/{pid}/exports").json()}
    assert kinds == {"fcpxml", "xmeml", "edl"}

    custom = tmp_path / "for-resolve.fcpxml"
    resp = api.post(
        f"/api/projects/{pid}/nle-exports",
        json={"format": "fcpxml", "version": 1, "output_path": str(custom)},
    )
    assert resp.status_code == 201 and custom.is_file()
    assert (
        api.post(
            f"/api/projects/{pid}/nle-exports", json={"format": "fcpxml", "version": 7}
        ).status_code
        == 404
    )
    assert api.post(f"/api/projects/{pid}/nle-exports", json={"format": "aaf"}).status_code == 422


def test_edit_then_export_uses_the_new_version(api: TestClient, edited: dict) -> None:  # type: ignore[type-arg]
    pid, clips = edited["pid"], edited["clips"]
    cut = api.get(f"/api/projects/{pid}/cutlist").json()["cutlist"]
    cut["segments"][0]["clip_id"] = clips["wide"]["id"]
    assert api.put(f"/api/projects/{pid}/cutlist", json={"cutlist": cut}).json()["version"] == 2
    out = api.post(f"/api/projects/{pid}/nle-exports", json={"format": "edl"}).json()
    assert out["export"]["path"].endswith("-v2.edl")
    first_event = next(
        line for line in Path(out["export"]["path"]).read_text().splitlines() if line[:3] == "001"
    )
    assert first_event.split()[1] == "WIDE"
