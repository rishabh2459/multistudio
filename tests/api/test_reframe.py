"""Phase 8 API: auto framing as a job, vertical render. Needs ffmpeg."""

from fastapi.testclient import TestClient

from multicam_engine.media.probe import probe

from .conftest import Recording, add_clip, new_project, start_job, wait


def test_auto_framing_and_vertical_render(api: TestClient, recording: Recording) -> None:
    pid = new_project(api, "Shorts")
    add_clip(api, pid, recording.cam1, speaker_label="Host")
    add_clip(api, pid, recording.cam2, speaker_label="Guest")
    add_clip(api, pid, recording.wide, role="wide")
    assert "face_model_available" in api.get("/api/system/info").json()

    auto = wait(api, start_job(api, pid, "auto", vad="energy", framing=True)["id"])
    assert auto["status"] == "succeeded", auto
    framing = auto["result"]["reframe"]
    assert framing["version"] == 2 and not framing["cached"]
    # the test pattern has no faces: centred crops, and the user is told
    assert framing["framed"] == 0 and framing["centred"] > 0
    assert any("no faces" in w for w in auto["result"]["warnings"])

    latest = api.get(f"/api/projects/{pid}/cutlist").json()
    assert latest["source"] == "reframe"
    for seg in latest["cutlist"]["segments"]:
        v = seg["reframe_vertical"]
        assert v is not None and v["cx"] == 0.5 and v["path"] is None

    again = wait(api, start_job(api, pid, "reframe")["id"])
    assert again["result"]["cached"] and again["result"]["version"] == 2
    off = wait(api, start_job(api, pid, "reframe", punch="off", vertical=False)["id"])
    assert off["status"] == "succeeded"

    tl = api.get(f"/api/projects/{pid}/timeline").json()
    assert {(c["width"], c["height"]) for c in tl["clips"]} == {(160, 90)}

    render = wait(api, start_job(api, pid, "render", preset="vertical-draft")["id"])
    assert render["status"] == "succeeded", render
    info = probe(render["result"]["path"])
    assert (info.media.width, info.media.height) == (540, 960)
    assert render["result"]["frames"] == latest["cutlist"]["segments"][-1]["end_frame"]


def test_reframe_needs_a_cutlist(api: TestClient, recording: Recording) -> None:
    pid = new_project(api)
    add_clip(api, pid, recording.cam1)
    job = wait(api, start_job(api, pid, "reframe")["id"])
    assert job["status"] == "failed" and "auto edit" in job["error"]
    bad = api.post(
        f"/api/projects/{pid}/jobs", json={"kind": "reframe", "params": {"punch": "wild"}}
    )
    assert bad.status_code == 422
