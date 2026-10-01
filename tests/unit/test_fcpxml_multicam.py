"""Multicam FCPXML for Final Cut (PL7): structure, timing, angle sync, markers."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from fractions import Fraction
from uuid import UUID

import pytest

from multicam_engine.editplan import EditPlan, PlanMethod, build_edit_plan, to_fcpxml_multicam
from multicam_engine.export import NleFormat, write_nle
from multicam_engine.media.probe import ProbeResult
from multicam_engine.models import CutList, Project

from .test_editplan import _with_mic

Setup = tuple[Project, CutList, dict[UUID, ProbeResult]]


def _time(value: str) -> Fraction:
    assert value.endswith("s"), value
    num, _, den = value[:-1].partition("/")
    return Fraction(int(num), int(den or 1))


def _xml(plan: EditPlan) -> ET.Element:
    text = to_fcpxml_multicam(plan)
    assert text.startswith('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE fcpxml>')
    return ET.fromstring(text.split("\n", 2)[2])


def _plan(setup: Setup, **kw: object) -> EditPlan:
    project, cut, probes = setup
    return build_edit_plan(project, cut, probes, method=PlanMethod.MULTICAM, **kw)  # type: ignore[arg-type]


def test_structure_and_references(setup: Setup) -> None:
    plan = _plan(setup)
    root = _xml(plan)
    assert root.tag == "fcpxml" and root.get("version") == "1.9"
    formats = {f.get("id"): f for f in root.iter("format")}
    assets = {a.get("id"): a for a in root.iter("asset")}
    medias = list(root.iter("media"))
    assert len(medias) == 1 and len(assets) == 3
    multicam = medias[0].find("multicam")
    assert multicam is not None and multicam.get("format") in formats
    angles = multicam.findall("mc-angle")
    assert [a.get("name") for a in angles] == ["Host", "Guest", "wide"]
    assert len({a.get("angleID") for a in angles}) == 3
    for a in assets.values():
        assert a.get("format") in formats
        assert a.find("media-rep") is not None
    for clip in root.iter("asset-clip"):
        assert clip.get("ref") in assets
    for clip in root.iter("mc-clip"):
        assert clip.get("ref") == medias[0].get("id")


def test_angles_sit_at_their_sync_positions(setup: Setup) -> None:
    plan = _plan(setup)
    fps = Fraction(30000, 1001)
    angles = {a.get("name"): a for a in _xml(plan).iter("mc-angle")}
    host, guest, wide = (angles[n] for n in ("Host", "Guest", "wide"))
    # host = reference: from frame 0, from its timecode start (01:00:00;00)
    host_clip = host.find("asset-clip")
    assert host_clip is not None and host.find("gap") is None
    assert _time(host_clip.get("offset", "")) == 0
    media = plan.media_by_id()
    host_media = next(m for m in media.values() if m.label == "Host")
    assert _time(host_clip.get("start", "")) * fps == host_media.start_timecode_frames
    # guest started 1 s (30 frames) earlier: trimmed by its first second
    g = guest.find("asset-clip")
    assert g is not None and guest.find("gap") is None
    assert _time(g.get("start", "")) * fps == 30
    # wide started 2 s (60 frames) later: a 60-frame gap first, then the clip
    gap, clip = list(wide)
    assert gap.tag == "gap" and _time(gap.get("duration", "")) * fps == 60
    assert clip.tag == "asset-clip" and _time(clip.get("offset", "")) * fps == 60
    assert _time(clip.get("start", "")) == 0
    # every angle ends inside the edit
    for angle in angles.values():
        end = sum(_time(c.get("duration", "")) for c in angle)
        assert end * fps <= plan.sequence.duration_frames


def test_mc_clips_rebuild_the_cut_on_the_frame_grid(setup: Setup) -> None:
    plan = _plan(setup)
    root = _xml(plan)
    fps = Fraction(30000, 1001)
    angle_cam = {a.get("angleID"): a.get("name") for a in root.iter("mc-angle")}
    label = {m.clip_id: m.label for m in plan.media}
    rebuilt = []
    position = Fraction(0)
    spine = root.find("library/event/project/sequence/spine")
    assert spine is not None
    for clip in spine:
        offset, start, dur = (_time(clip.get(k, "")) for k in ("offset", "start", "duration"))
        assert offset == position  # the spine is contiguous
        position += dur
        if clip.tag == "gap":  # frames the live camera had not recorded
            continue
        assert start == offset  # multicam time = sequence time
        for t in (offset, dur):
            assert (t * fps).denominator == 1  # exact frame multiples
        video = [s for s in clip.findall("mc-source") if s.get("srcEnable") in ("video", "all")]
        assert len(video) == 1
        rebuilt.append(
            (int(offset * fps), int((offset + dur) * fps), angle_cam[video[0].get("angleID")])
        )
    assert rebuilt == [(e.start, e.end, label[e.clip_id]) for e in plan.video_events]
    assert position * fps == plan.sequence.duration_frames
    seq = root.find("library/event/project/sequence")
    assert seq is not None and seq.get("tcFormat") == "DF"


def test_markers_land_inside_their_mc_clip(setup: Setup) -> None:
    project, cut, probes = setup
    segs = [
        cut.segments[0],
        cut.segments[1],
        cut.segments[2].model_copy(update={"confidence": 0.2}),
    ]
    plan = build_edit_plan(
        project, cut.model_copy(update={"segments": segs}), probes, method=PlanMethod.MULTICAM
    )
    fps = Fraction(30000, 1001)
    found = []
    for clip in _xml(plan).iter("mc-clip"):
        start, dur = _time(clip.get("start", "")), _time(clip.get("duration", ""))
        for m in clip.findall("marker"):
            t = _time(m.get("start", ""))
            assert start <= t < start + dur
            found.append(int(t * fps))
    assert found == [m.frame for m in plan.markers] == [1798]


def test_sound_only_mic_is_an_audio_angle(setup: Setup) -> None:
    (project, cut, probes), _mic_id = _with_mic(setup)
    plan = build_edit_plan(project, cut, probes, method=PlanMethod.MULTICAM)
    root = _xml(plan)
    angles = {a.get("name"): a for a in root.iter("mc-angle")}
    mic_angle = angles["zoom h6"]
    clip = mic_angle.find("asset-clip")
    assert clip is not None and clip.get("srcEnable") == "audio"
    mic_asset = next(a for a in root.iter("asset") if a.get("name") == "zoom h6.wav")
    assert mic_asset.get("hasVideo") is None and mic_asset.get("hasAudio") == "1"
    for mc in root.iter("mc-clip"):
        audio = [s.get("angleID") for s in mc.findall("mc-source") if s.get("srcEnable") == "audio"]
        assert audio == [mic_angle.get("angleID")]


def test_write_nle_refuses_multicam_without_a_plan(setup: Setup) -> None:
    from multicam_engine.export import build_nle_timeline

    project, cut, probes = setup
    with pytest.raises(ValueError, match="EditPlan"):
        write_nle(build_nle_timeline(project, cut, probes), NleFormat.FCPXML_MULTICAM)
