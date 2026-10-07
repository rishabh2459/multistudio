"""Premiere XML extras: reframe as Motion keyframes, the multicam source sequence."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from uuid import UUID

import pytest

from multicam_engine.editplan import (
    EditPlan,
    PlanMethod,
    build_edit_plan,
    multicam_source_timeline,
    plan_to_timeline,
    to_xmeml_multicam,
)
from multicam_engine.editplan.transform import crop_transform, shift_reframe, transform_at
from multicam_engine.export import NleFormat, write_nle
from multicam_engine.media.probe import ProbeResult
from multicam_engine.models import CutList, Project
from multicam_engine.models.cutlist import Reframe, ReframeKey

Setup = tuple[Project, CutList, dict[UUID, ProbeResult]]


def _xml(text: str) -> ET.Element:
    return ET.fromstring(text.split("\n", 2)[2])


# ----------------------------------------------------------------- transform
def test_crop_transform_fills_the_sequence_with_the_crop() -> None:
    # full frame 16:9 -> 16:9: 100 %, centred
    (key,) = crop_transform(Reframe(cx=0.5, cy=0.5, scale=1), (1920, 1080), (1920, 1080), 0, 10)  # type: ignore[misc]
    assert (key.scale, key.x, key.y) == (100.0, 960.0, 540.0)
    # 2x punch-in on the left third: 200 %, the crop centre moves to the middle
    (key,) = crop_transform(Reframe(cx=0.3, cy=0.5, scale=2), (1920, 1080), (1920, 1080), 5, 10)  # type: ignore[misc]
    assert key.frame == 5 and key.scale == 200.0
    assert key.x == pytest.approx(960 - 2 * (0.3 - 0.5) * 1920)
    # 4K source into a 1080p sequence: 50 %
    (key,) = crop_transform(Reframe(cx=0.5, cy=0.5, scale=1), (3840, 2160), (1920, 1080), 0, 1)  # type: ignore[misc]
    assert key.scale == 50.0
    # 16:9 source into 9:16: full height (1920/1080 = 177.78 %), centre clamped inside
    (key,) = crop_transform(Reframe(cx=0.0, cy=0.5, scale=1), (1920, 1080), (1080, 1920), 0, 1)  # type: ignore[misc]
    assert key.scale == pytest.approx(177.7778, abs=1e-3)
    crop_w = 1080 / (key.scale / 100)  # source pixels shown
    left_edge = 1920 / 2 - (key.x - 540) / (key.scale / 100) - crop_w / 2
    assert left_edge == pytest.approx(0, abs=0.01)  # clamped to the frame's left edge


def test_crop_transform_follows_the_path_and_is_optional() -> None:
    r = Reframe(
        cx=0.4,
        cy=0.5,
        scale=1.5,
        path=[
            ReframeKey(frame=0, cx=0.4, cy=0.5),
            ReframeKey(frame=50, cx=0.6, cy=0.5),
            ReframeKey(frame=500, cx=0.6, cy=0.4),
        ],
    )
    keys = crop_transform(r, (1920, 1080), (1920, 1080), 20, 100)
    assert keys is not None and [k.frame for k in keys] == [20, 50]
    assert keys[0].x > keys[1].x  # moving right in the source = clip moves left
    assert crop_transform(None, (1920, 1080), (1920, 1080), 0, 1) is None
    assert crop_transform(None, (1920, 1080), (1080, 1920), 0, 1, always=True) is not None
    mid = transform_at(keys, 35)
    assert keys[1].x < mid.x < keys[0].x
    shifted = shift_reframe(r, 30)
    assert shifted is not None and shifted.path is not None
    assert [k.frame for k in shifted.path] == [0, 20, 470]
    assert shifted.center_at(0) == pytest.approx(r.center_at(30))


def test_reframed_segments_get_basic_motion_in_xmeml(setup: Setup) -> None:
    project, cut, probes = setup
    framed = Reframe(
        cx=0.35,
        cy=0.45,
        scale=1.5,
        path=[ReframeKey(frame=300, cx=0.35, cy=0.45), ReframeKey(frame=900, cx=0.5, cy=0.45)],
    )
    segs = [
        cut.segments[0],
        cut.segments[1].model_copy(update={"reframe": framed}),
        cut.segments[2],
    ]
    plan = build_edit_plan(project, cut.model_copy(update={"segments": segs}), probes)
    ev = plan.video_events[1]
    assert ev.transform is not None and [k.frame for k in ev.transform] == [300, 900]
    assert plan.video_events[0].transform is None  # no reframe: as placed
    live = [p for t in plan.video_tracks for p in t.pieces if p.enabled and p.start == 300]
    assert live[0].transform == ev.transform  # stacked live piece is framed too

    root = _xml(write_nle(plan_to_timeline(plan), NleFormat.XMEML))
    motions = [e for e in root.iter("effect") if e.findtext("effectid") == "basic"]
    assert len(motions) == 1
    scale = next(p for p in motions[0].iter("parameter") if p.findtext("parameterid") == "scale")
    assert scale.findtext("value") == "150"
    whens = [int(k.findtext("when") or -1) for k in scale.iter("keyframe")]
    item = next(i for i in root.iter("clipitem") if i.find("filter") is not None)
    source_in = int(item.findtext("in") or 0)
    assert whens[0] == source_in and whens[1] > whens[0]  # media frames, from the in point
    center = next(p for p in motions[0].iter("parameter") if p.findtext("parameterid") == "center")
    horiz = float(center.findtext("value/horiz") or 0)
    assert horiz == pytest.approx((ev.transform[0].x - 960) / 1920, abs=1e-5)


# ----------------------------------------------------------------- multicam
def test_multicam_xmeml_has_the_stacked_edit_and_a_source_sequence(setup: Setup) -> None:
    project, cut, probes = setup
    plan: EditPlan = build_edit_plan(project, cut, probes, method=PlanMethod.MULTICAM)
    root = _xml(to_xmeml_multicam(plan))
    seqs = root.findall("project/children/sequence")
    assert [s.findtext("name") for s in seqs] == [
        plan.sequence.name,
        plan.sequence.name + " - Multicam Source",
    ]
    edit, source = seqs
    # the edit: one track per camera, disabled pieces present (stacked, same cuts)
    vtracks = edit.findall("media/video/track")
    assert len(vtracks) == 3
    assert any(i.findtext("enabled") == "FALSE" for i in edit.iter("clipitem"))
    # the source: each camera ONE enabled clip, synced like the plan's tracks
    src_tracks = source.findall("media/video/track")
    assert [len(t.findall("clipitem")) for t in src_tracks] == [1, 1, 1]
    assert all(i.findtext("enabled") == "TRUE" for t in src_tracks for i in t.iter("clipitem"))
    starts = [int(t.find("clipitem").findtext("start") or -1) for t in src_tracks]  # type: ignore[union-attr]
    assert starts == [min(p.start for p in t.pieces) for t in plan.video_tracks]
    assert source.findall("media/audio/track")  # mics come along
    assert not source.findall("marker")
    # every file is defined once in the document, later references are empty
    full = [f for f in root.iter("file") if f.find("pathurl") is not None]
    assert len(full) == len({f.get("id") for f in root.iter("file")})
    ids = [i.get("id") for i in root.iter("clipitem")]
    assert len(ids) == len(set(ids))


def test_source_timeline_joins_each_camera_into_one_clip(setup: Setup) -> None:
    project, cut, probes = setup
    plan = build_edit_plan(project, cut, probes)
    tl = multicam_source_timeline(plan)
    assert [len(t) for t in tl.stacked] == [1, 1, 1]
    for track, plan_track in zip(tl.stacked, plan.video_tracks, strict=True):
        ((ev, on),) = track
        assert on and ev.start == plan_track.pieces[0].start
        assert ev.end == plan_track.pieces[-1].end
