"""Adding, updating, relinking and removing clips. Needs ffmpeg."""

import shutil
from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient

from ..media_factory import write_clip
from .conftest import Recording, add_clip, new_project


def test_add_clip_probes_and_sets_reference(api: TestClient, recording: Recording) -> None:
    pid = new_project(api)
    cam1 = add_clip(api, pid, recording.cam1)
    assert cam1["media"]["fps"] == {"num": 30000, "den": 1001}
    assert cam1["media"]["width"] == 160 and cam1["is_reference"]
    assert cam1["speaker_label"] == "cam1" and cam1["file_status"] == "ok"
    wide = add_clip(api, pid, recording.wide, role="wide")
    assert wide["speaker_label"] is None and not wide["is_reference"]

    project = api.get(f"/api/projects/{pid}").json()
    assert project["reference_clip_id"] == cam1["id"]
    assert project["output"] == {"fps": {"num": 30000, "den": 1001}, "width": 160, "height": 90}
    assert [c["name"] for c in api.get(f"/api/projects/{pid}/clips").json()] == [
        "cam1.mp4",
        "wide.mp4",
    ]


def test_add_clip_errors(api: TestClient, recording: Recording, tmp_path: Path) -> None:
    pid = new_project(api)
    add_clip(api, pid, recording.cam1)
    dup = api.post(f"/api/projects/{pid}/clips", json={"path": str(recording.cam1)})
    assert dup.status_code == 409
    missing = api.post(f"/api/projects/{pid}/clips", json={"path": str(tmp_path / "nope.mp4")})
    assert missing.status_code == 422 and "not found" in missing.json()["detail"]
    relative = api.post(f"/api/projects/{pid}/clips", json={"path": "cam1.mp4"})
    assert relative.status_code == 422
    junk = tmp_path / "junk.mp4"
    junk.write_bytes(b"not a video")
    assert api.post(f"/api/projects/{pid}/clips", json={"path": str(junk)}).status_code == 422


def test_update_roles_and_labels(api: TestClient, recording: Recording) -> None:
    pid = new_project(api)
    clip = add_clip(api, pid, recording.cam1)
    updated = api.patch(f"/api/clips/{clip['id']}", json={"speaker_label": "Host"}).json()
    assert updated["speaker_label"] == "Host"
    wide = api.patch(f"/api/clips/{clip['id']}", json={"role": "wide"}).json()
    assert wide["role"] == "wide" and wide["speaker_label"] is None
    bad = api.patch(f"/api/clips/{clip['id']}", json={"speaker_label": "X"})
    assert bad.status_code == 422
    back = api.patch(f"/api/clips/{clip['id']}", json={"role": "speaker"}).json()
    assert back["speaker_label"] == "cam1"


def test_missing_changed_and_relink(
    api: TestClient, recording: Recording, tmp_path: Path, ffmpeg: str
) -> None:
    moved = tmp_path / "cam2.mp4"
    shutil.copy(recording.cam2, moved)
    pid = new_project(api)
    add_clip(api, pid, recording.cam1)
    clip = add_clip(api, pid, moved)

    relocated = tmp_path / "moved" / "cam2.mp4"
    relocated.parent.mkdir()
    moved.rename(relocated)
    assert api.get(f"/api/clips/{clip['id']}").json()["file_status"] == "missing"
    relinked = api.patch(f"/api/clips/{clip['id']}", json={"path": str(relocated)}).json()
    assert relinked["file_status"] == "ok" and relinked["path"] == str(relocated)

    # A different (much shorter) file is refused unless forced.
    short = write_clip(ffmpeg, tmp_path / "short.mp4", np.zeros(8000 * 3), 8000)
    refused = api.patch(f"/api/clips/{clip['id']}", json={"path": str(short)})
    assert refused.status_code == 409 and "force" in refused.json()["detail"]
    forced = api.patch(f"/api/clips/{clip['id']}", json={"path": str(short), "force": True})
    assert forced.status_code == 200

    with short.open("ab") as fh:  # file changed on disk
        fh.write(b"\0" * 10)
    assert api.get(f"/api/clips/{clip['id']}").json()["file_status"] == "changed"


def test_delete_reference_promotes_next_clip(api: TestClient, recording: Recording) -> None:
    pid = new_project(api)
    cam1 = add_clip(api, pid, recording.cam1)
    cam2 = add_clip(api, pid, recording.cam2)
    assert api.delete(f"/api/clips/{cam1['id']}").status_code == 204
    project = api.get(f"/api/projects/{pid}").json()
    assert project["reference_clip_id"] == cam2["id"]
    assert [c["id"] for c in project["clips"]] == [cam2["id"]]
