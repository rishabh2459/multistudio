"""PL1 API: camera layout on projects, custom switching, user presets."""

from __future__ import annotations

from fastapi.testclient import TestClient

from .conftest import Recording, add_clip, new_project, start_job, wait


def test_role_layout_is_reported_and_explicit_layout_drives_the_edit(
    api: TestClient, recording: Recording
) -> None:
    pid = new_project(api)
    c1 = add_clip(api, pid, recording.cam1, speaker_label="Host")
    c2 = add_clip(api, pid, recording.cam2, speaker_label="Guest")
    wide = add_clip(api, pid, recording.wide, role="wide")

    project = api.get(f"/api/projects/{pid}").json()
    assert project["layout_custom"] is False
    assert [s["name"] for s in project["speakers"]] == ["Host", "Guest"]
    assert [c["shot"] for c in project["cameras"]] == ["solo", "solo", "wide"]
    assert project["switch"]["min_shot_s"] == 2.5 and project["switch_custom"] is False

    job = wait(api, start_job(api, pid, "auto")["id"])
    assert job["status"] == "succeeded", job["error"]
    first = api.get(f"/api/projects/{pid}/cutlist").json()["cutlist"]
    assert {s["clip_id"] for s in first["segments"]} <= {c1["id"], c2["id"], wide["id"]}
    assert all(s["confidence"] is not None for s in first["segments"])

    # Explicit layout: cam2 is a two-shot showing both people, the wide is B-roll.
    host, guest = project["speakers"]
    layout = {
        "speakers": [host, guest],
        "cameras": [
            {"clip_id": c1["id"], "shot": "solo", "covers": [host["id"]]},
            {"clip_id": c2["id"], "shot": "two", "covers": [host["id"], guest["id"]]},
        ],
    }
    resp = api.patch(f"/api/projects/{pid}", json={"layout": layout})
    assert resp.status_code == 200, resp.text
    assert resp.json()["layout_custom"] is True
    assert [c["shot"] for c in resp.json()["cameras"]] == ["solo", "two", "broll"]

    job = wait(api, start_job(api, pid, "decide")["id"])
    assert job["status"] == "succeeded", job["error"]
    assert job["result"]["cached"] is False  # layout is part of the decide inputs
    cut = api.get(f"/api/projects/{pid}/cutlist").json()["cutlist"]
    assert wide["id"] not in {s["clip_id"] for s in cut["segments"]}

    # Back to roles.
    resp = api.patch(f"/api/projects/{pid}", json={"reset_layout": True})
    assert resp.json()["layout_custom"] is False


def test_invalid_layout_is_rejected(api: TestClient, recording: Recording) -> None:
    pid = new_project(api)
    c1 = add_clip(api, pid, recording.cam1)
    bad = {
        "speakers": [{"name": "A", "mic_clip_id": c1["id"]}],
        "cameras": [{"clip_id": c1["id"], "shot": "solo", "covers": ["not-a-speaker"]}],
    }
    assert api.patch(f"/api/projects/{pid}", json={"layout": bad}).status_code == 422


def test_custom_switch_settings_and_preset_reset(api: TestClient) -> None:
    pid = new_project(api)
    settings = api.get(f"/api/projects/{pid}").json()["switch"]
    settings["max_shot_s"] = 9.0
    resp = api.patch(f"/api/projects/{pid}", json={"switch": settings})
    assert resp.json()["switch_custom"] is True
    assert resp.json()["switch"]["max_shot_s"] == 9.0
    resp = api.patch(f"/api/projects/{pid}", json={"preset": "punchy"})
    assert resp.json()["switch_custom"] is False
    assert resp.json()["switch"]["min_shot_s"] == 1.0


def test_user_presets_crud_export_import(api: TestClient) -> None:
    presets = api.get("/api/presets").json()
    assert [p["id"] for p in presets if p["builtin"]] == ["calm", "balanced", "dynamic", "punchy"]
    settings = presets[1]["settings"] | {"wide_frequency": 0.8}

    created = api.post("/api/presets", json={"name": "My show", "settings": settings})
    assert created.status_code == 201, created.text
    pid = created.json()["id"]
    for clash in ("My show", "Calm"):
        resp = api.post("/api/presets", json={"name": clash, "settings": settings})
        assert resp.status_code == 409

    exported = api.get(f"/api/presets/{pid}/export").json()
    assert exported["format"] == "multicam-preset" and exported["settings"]["wide_frequency"] == 0.8
    imported = api.post("/api/presets/import", json=exported).json()
    assert imported["name"] == "My show (2)"

    assert api.delete("/api/presets/balanced").status_code == 409
    assert api.delete(f"/api/presets/{pid}").status_code == 204
    names = [p["name"] for p in api.get("/api/presets").json()]
    assert "My show" not in names and "My show (2)" in names
