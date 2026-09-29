"""Layout resolution: role-derived layouts and explicit ones (PL1)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from multicam_engine.layout import LayoutError, derived_speaker_id, resolve_layout
from multicam_engine.models.project import (
    CameraLayout,
    Clip,
    ClipRole,
    OutputSettings,
    Project,
    ShotType,
    Speaker,
)
from multicam_engine.models.time import FPS_25


def _project(
    *clips: Clip,
    speakers: list[Speaker] | None = None,
    cameras: list[CameraLayout] | None = None,
) -> Project:
    return Project(
        name="p", output=OutputSettings(fps=FPS_25, width=1920, height=1080),
        clips=list(clips), speakers=speakers or [], cameras=cameras or [],
    )  # fmt: skip


def test_roles_give_solo_per_speaker_and_wide_for_everyone() -> None:
    a = Clip(path="/r/host.mov", speaker_label="Host")
    b = Clip(path="/r/guest.mov")
    w = Clip(path="/r/wide.mov", role=ClipRole.WIDE)
    x = Clip(path="/r/broll.mov", role=ClipRole.BROLL)
    layout = resolve_layout(_project(a, b, w, x))
    assert not layout.custom
    assert [s.name for s in layout.speakers] == ["Host", "guest"]
    assert [s.id for s in layout.speakers] == [derived_speaker_id(a.id), derived_speaker_id(b.id)]
    assert [c.shot for c in layout.cameras] == [ShotType.SOLO, ShotType.SOLO, ShotType.WIDE]
    assert layout.cameras[2].covers == [s.id for s in layout.speakers]
    assert [c.shot for c in layout.all_cameras][-1] is ShotType.BROLL
    assert layout.mic_keys == [(a.id, None), (b.id, None)]


def test_explicit_layout_with_one_multichannel_recorder() -> None:
    cam1, cam2 = Clip(path="/r/c1.mov"), Clip(path="/r/c2.mov")
    rec = Clip(path="/r/zoom.wav", role=ClipRole.BROLL)
    h, g = (
        Speaker(name="Host", mic_clip_id=rec.id, mic_channel=0),
        Speaker(name="Guest", mic_clip_id=rec.id, mic_channel=1),
    )
    p = _project(
        cam1, cam2, rec,
        speakers=[h, g],
        cameras=[
            CameraLayout(clip_id=cam1.id, shot=ShotType.SOLO, covers=[h.id]),
            CameraLayout(clip_id=cam2.id, shot=ShotType.TWO, covers=[h.id, g.id]),
        ],
    )  # fmt: skip
    layout = resolve_layout(p)
    assert layout.custom
    assert [c.clip_id for c in layout.cameras] == [cam1.id, cam2.id]  # recorder = B-roll
    assert layout.mic_keys == [(rec.id, 0), (rec.id, 1)]


def test_speaker_without_mic_is_a_clear_error() -> None:
    cam = Clip(path="/r/c1.mov")
    s = Speaker(name="Solo")
    p = _project(
        cam, speakers=[s], cameras=[CameraLayout(clip_id=cam.id, shot=ShotType.SOLO, covers=[s.id])]
    )
    with pytest.raises(LayoutError, match="no microphone"):
        _ = resolve_layout(p).mic_keys


def test_only_broll_is_an_error() -> None:
    with pytest.raises(LayoutError):
        resolve_layout(_project(Clip(path="/r/b.mov", role=ClipRole.BROLL)))


def test_project_validates_layout_references() -> None:
    cam = Clip(path="/r/c1.mov")
    s = Speaker(name="A", mic_clip_id=cam.id)
    with pytest.raises(ValidationError, match="unknown speaker"):
        _project(cam, speakers=[s], cameras=[
            CameraLayout(clip_id=cam.id, shot=ShotType.SOLO, covers=[Speaker(name="x").id])
        ])  # fmt: skip
    with pytest.raises(ValidationError, match="only one camera layout"):
        _project(cam, speakers=[s], cameras=[
            CameraLayout(clip_id=cam.id, shot=ShotType.SOLO, covers=[s.id]),
            CameraLayout(clip_id=cam.id, shot=ShotType.WIDE, covers=[s.id]),
        ])  # fmt: skip
    with pytest.raises(ValidationError):
        _project(*[Clip(path=f"/r/{i}.mov") for i in range(11)], cameras=[
            CameraLayout(clip_id=Clip(path="/x").id, shot=ShotType.SOLO) for _ in range(11)
        ])  # fmt: skip
