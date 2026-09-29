"""Auto framing without video: tracking, smoothing, crops, punch-ins."""

from uuid import uuid4

import numpy as np
import pytest

from multicam_engine.analysis.speakers import SILENCE, SpeakerActivity
from multicam_engine.models import CutList, OutputSettings, Project, Segment
from multicam_engine.models.cutlist import Reframe
from multicam_engine.models.project import Clip, ClipRole
from multicam_engine.models.time import Rational
from multicam_engine.reframe import (
    ClipGeometry,
    Detections,
    Face,
    FaceTracks,
    ReframeSettings,
    auto_reframe,
    detections_from_json,
    detections_to_json,
    plan_crop,
)
from multicam_engine.reframe.detect import nms
from multicam_engine.reframe.framing import (
    PathPoint,
    clamp_center,
    crop_size,
    simplify,
    smooth,
)
from multicam_engine.reframe.punch import PUNCH_PRESETS, split_points
from multicam_engine.reframe.track import group_track, primary_track

FPS = Rational(num=30, den=1)
GEOM = ClipGeometry(width=1920, height=1080, speed=1.0, media_offset=0.0)


def face(cx: float, cy: float, h: float = 0.2) -> Face:
    return Face(cx - h * 0.4, cy - h / 2, h * 0.8, h, 0.9)


def test_crop_geometry() -> None:
    assert crop_size(1920, 1080, 1920, 1080, 1.0) == (1.0, 1.0)
    w, h = crop_size(1920, 1080, 1080, 1920, 1.0)  # 9:16 out of 16:9
    assert h == 1.0 and w == pytest.approx(0.31640625)
    assert crop_size(1920, 1080, 1920, 1080, 2.0) == (0.5, 0.5)
    w, h = crop_size(1440, 1080, 1920, 1080, 1.0)  # 4:3 source into 16:9
    assert w == 1.0 and h == pytest.approx(0.75)
    assert clamp_center(0.05, 0.5, 0.3, 1.0) == (0.15, 0.5)
    assert clamp_center(0.99, 0.2, 0.3, 0.5) == (0.85, 0.25)


def test_primary_track_follows_one_person_and_holds_gaps() -> None:
    dets = [
        Detections(0.0, (face(0.3, 0.4),)),
        Detections(0.5, (face(0.8, 0.5, 0.3), face(0.32, 0.4))),  # bigger passer-by
        Detections(1.0, ()),  # looked away
        Detections(5.0, ()),  # gone for long: back to centre
        Detections(6.0, (face(0.7, 0.4),)),
    ]
    track = primary_track(dets, hold_s=3.0)
    assert [round(p.cx, 2) for p in track] == [0.3, 0.32, 0.32, 0.5, 0.7]
    assert [p.seen for p in track] == [True, True, False, False, True]
    group = group_track(dets)
    assert group[1].cx == pytest.approx((0.32 - 0.08 + 0.8 + 0.12) / 2)


def test_smoothing_ignores_jitter_and_follows_real_moves() -> None:
    jitter = [PathPoint(i * 0.5, 0.5 + (0.01 if i % 2 else -0.01), 0.5) for i in range(20)]
    assert {round(p.cx, 3) for p in smooth(jitter, dead_zone=0.04, tau_s=1.0)} == {0.49}
    move = [PathPoint(i * 0.5, 0.3 if i < 4 else 0.7, 0.5) for i in range(20)]
    out = smooth(move, dead_zone=0.04, tau_s=1.0)
    xs = [p.cx for p in out]
    assert xs == sorted(xs) and xs[4] < 0.55 and xs[-1] > 0.69  # eases, no jump
    keys = simplify(out, 0.01)
    assert 2 < len(keys) < len(out)


def test_plan_crop_static_panning_and_fallback() -> None:
    still = [primary_track([Detections(t / 2, (face(0.4, 0.4),))])[0] for t in range(20)]
    reframe, followed = plan_crop(still, 0, 300, 30.0, GEOM, (1080, 1920), 1.0, ReframeSettings())
    assert followed and reframe.path is None
    assert reframe.cx == pytest.approx(0.4) and reframe.cy == 0.5  # full height: cy centred
    moving = primary_track([Detections(t / 2, (face(0.2 + t * 0.03, 0.4),)) for t in range(20)])
    panned, _ = plan_crop(moving, 0, 300, 30.0, GEOM, (1080, 1920), 1.0, ReframeSettings())
    assert panned.path and len(panned.path) >= 3
    assert panned.path[0].frame == 0 and panned.path[-1].frame <= 299
    assert panned.center_at(250)[0] > panned.center_at(10)[0] + 0.2
    nobody = primary_track([Detections(t / 2, ()) for t in range(10)])
    centred, followed = plan_crop(nobody, 0, 150, 30.0, GEOM, (1920, 1080), 1.3, ReframeSettings())
    assert not followed and (centred.cx, centred.cy, centred.scale) == (0.5, 0.5, 1.3)


def test_punch_in_splits_at_pauses_only() -> None:
    p = PUNCH_PRESETS["balanced"]
    assert p is not None
    assert split_points(0, 240, None, 30.0, p) == []  # 8 s: too short
    assert split_points(0, 600, None, 30.0, p) == [300]  # 20 s, unknown speech: middle
    speaking = np.ones(600, dtype=bool)
    assert split_points(0, 600, speaking, 30.0, p) == []  # never pauses: no cut mid-word
    speaking[350:360] = False
    assert split_points(0, 600, speaking, 30.0, p) == [350]
    long = split_points(0, 1800, None, 30.0, p)  # 60 s -> several parts, none too long
    parts = np.diff([0, *long, 1800]) / 30
    assert parts.max() <= p.min_shot_s and parts.min() >= p.min_part_s


def _project() -> tuple[Project, Clip, Clip]:
    host = Clip(path="/r/host.mp4", role=ClipRole.SPEAKER, speaker_label="Host")
    wide = Clip(path="/r/wide.mp4", role=ClipRole.WIDE)
    project = Project(name="p", output=OutputSettings(fps=FPS, width=1920, height=1080),
                      clips=[host, wide], reference_clip_id=host.id)  # fmt: skip
    return project, host, wide


def test_auto_reframe_whole_edit() -> None:
    project, host, wide = _project()
    cut = CutList(project_id=project.id, fps=FPS, segments=[
        Segment(clip_id=wide.id, start_frame=0, end_frame=150),
        Segment(clip_id=host.id, start_frame=150, end_frame=900),  # 25 s
    ])  # fmt: skip
    host_dets = [Detections(t / 2, (face(0.6, 0.35),)) for t in range(70)]
    wide_dets = [Detections(t / 2, (face(0.3, 0.4, 0.1), face(0.7, 0.4, 0.1))) for t in range(70)]
    tracks = {
        host.id: FaceTracks.build(host_dets, GEOM),
        wide.id: FaceTracks.build(wide_dets, GEOM),
    }
    geoms = {host.id: GEOM, wide.id: GEOM}
    labels = np.full(3000, 0)
    labels[1190:1210] = SILENCE  # a pause at ~12 s (frames 357-362)
    activity = SpeakerActivity(labels, ("Host",), np.zeros(3000), np.ones((1, 3000), bool))
    new, report = auto_reframe(project, cut, tracks, geoms, ReframeSettings(),
                               activity=activity, speaker_ids=[host.id])  # fmt: skip
    assert [(s.start_frame, s.end_frame) for s in new.segments] == [
        (0, 150),
        (150, 362),
        (362, 900),
    ]
    assert report.punch_ins == 1
    wide_seg, host_normal, host_tight = new.segments
    assert wide_seg.reframe is None and host_normal.reframe is None  # 16:9 fits already
    assert host_tight.reframe is not None and host_tight.reframe.scale == pytest.approx(1.3)
    assert host_tight.reframe.cx == pytest.approx(0.6, abs=0.02)
    assert wide_seg.reframe_vertical is not None and wide_seg.reframe_vertical.cx == pytest.approx(
        0.5, abs=0.02
    )
    assert (
        host_normal.reframe_vertical is not None
        and host_normal.reframe_vertical.cx == pytest.approx(0.6, abs=0.02)
    )

    # Re-running gives the same result (the split shot is treated as one), and a
    # framing the user set by hand is kept.
    again, _ = auto_reframe(project, new, tracks, geoms, ReframeSettings(),
                            activity=activity, speaker_ids=[host.id])  # fmt: skip
    assert [(s.start_frame, s.end_frame) for s in again.segments] == [
        (0, 150),
        (150, 362),
        (362, 900),
    ]
    edited = new.model_copy(deep=True)
    edited.segments[0].reframe_vertical = Reframe(cx=0.2, cy=0.5, scale=1.0, manual=True)
    kept, _ = auto_reframe(project, edited, tracks, geoms, ReframeSettings(punch="off"))
    assert kept.segments[0].reframe_vertical == edited.segments[0].reframe_vertical


def test_no_faces_gives_centred_crops_and_a_warning() -> None:
    project, host, _ = _project()
    cut = CutList(project_id=project.id, fps=FPS,
                  segments=[Segment(clip_id=host.id, start_frame=0, end_frame=300)])  # fmt: skip
    tracks = {host.id: FaceTracks.build([Detections(t / 2, ()) for t in range(20)], GEOM)}
    new, report = auto_reframe(project, cut, tracks, {host.id: GEOM}, ReframeSettings(punch="off"))
    v = new.segments[0].reframe_vertical
    assert v is not None and (v.cx, v.cy) == (0.5, 0.5)
    assert report.centred == 1 and "no faces" in report.warnings[0]


def test_helpers() -> None:
    boxes = np.array([[0, 0, 10, 10], [1, 1, 11, 11], [50, 50, 60, 60]], dtype=float)
    assert nms(boxes, np.array([0.9, 0.8, 0.7]), 0.3) == [0, 2]
    dets = [Detections(1.5, (face(0.3, 0.4),)), Detections(2.0, ())]
    back = detections_from_json(detections_to_json(dets))
    assert back[0].t == 1.5 and back[0].faces[0].cx == pytest.approx(0.3, abs=1e-4)
    assert back[1].faces == ()
    assert uuid4()  # (keeps the import list honest)
