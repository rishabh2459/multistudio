"""Ripple (jump cuts), slices and social clips from an EditPlan (PL5)."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from fractions import Fraction
from pathlib import Path
from uuid import UUID

import pytest

from multicam_engine.editplan import (
    TICKS_PER_SECOND,
    EditPlan,
    PlanMarker,
    PlanRemoval,
    build_edit_plan,
    plan_to_timeline,
)
from multicam_engine.editplan.ripple import (
    apply_removals,
    kept_ranges,
    merged_ranges,
    removed_frames,
    slice_plan,
)
from multicam_engine.editplan.social import (
    ASPECT_SIZES,
    EndPage,
    Picture,
    SocialOptions,
    Watermark,
    build_social_plans,
    framing_for,
)
from multicam_engine.export import NleFormat, write_nle
from multicam_engine.media.probe import ProbeResult
from multicam_engine.models import CutList, Project
from multicam_engine.models.cutlist import Reframe, ReframeKey

Setup = tuple[Project, CutList, dict[UUID, ProbeResult]]
F = Fraction(30000, 1001)


def _plan(setup: Setup) -> EditPlan:
    project, cut, probes = setup
    plan = build_edit_plan(project, cut, probes)
    return plan.model_copy(
        update={
            "markers": [
                PlanMarker(frame=410, note="inside a removal"),
                PlanMarker(frame=1000, note="kept"),
            ]
        }
    )


def _secs(ticks: int) -> Fraction:
    return Fraction(ticks, TICKS_PER_SECOND)


# ------------------------------------------------------------------ ranges
def test_ranges_merge_and_complement() -> None:
    rs = [PlanRemoval(start=50, end=60, kind="silence"), PlanRemoval(start=10, end=20, kind="x")]
    rs.append(PlanRemoval(start=55, end=70, kind="filler"))
    assert merged_ranges(rs, 100) == [(10, 20), (50, 70)]
    assert kept_ranges(rs, 100) == [(0, 10), (20, 50), (70, 100)]
    assert removed_frames(rs, 100) == 30
    assert kept_ranges([PlanRemoval(start=0, end=5, kind="x")], 5) == []


# ------------------------------------------------------------------ ripple
def test_ripple_removes_the_same_frames_on_every_track(setup: Setup) -> None:
    plan = _plan(setup)
    removals = [
        PlanRemoval(start=400, end=420, kind="silence"),
        PlanRemoval(start=2000, end=2100, kind="silence"),
    ]
    out = apply_removals(plan, removals)
    assert out.rippled and out.removals == []
    assert out.sequence.duration_frames == plan.sequence.duration_frames - 120
    assert out.sequence.name.endswith(" - Jump Cuts")

    # the host shot (300..1798) is split at the removal; its tail starts 20 frames
    # earlier on the timeline and 120 frames later in the source
    host = [e for e in out.video_events if e.clip_id == plan.video_events[1].clip_id]
    assert [(e.start, e.end) for e in host] == [(300, 400), (400, 1778)]
    orig = plan.video_events[1]
    assert _secs(host[1].source_in_ticks) - _secs(orig.source_in_ticks) == pytest.approx(
        Fraction(120) / F, abs=1 / TICKS_PER_SECOND
    )
    # contiguous and inside the new duration
    assert out.video_events[-1].end == out.sequence.duration_frames

    # every audio track loses exactly what overlapped the removals (sync kept)
    for before, after in zip(plan.audio_tracks, out.audio_tracks, strict=True):
        lost = sum(
            max(0, min(p.end, r.end) - max(p.start, r.start))
            for p in before.pieces
            for r in removals
        )
        assert sum(p.frames for p in before.pieces) - sum(p.frames for p in after.pieces) == lost
    # stacked tracks follow too, one live piece per event
    live = sorted((p.start, p.end) for t in out.video_tracks for p in t.pieces if p.enabled)
    assert live == [(e.start, e.end) for e in out.video_events]
    # markers inside removed parts disappear, later ones move
    assert [(m.frame, m.note) for m in out.markers] == [(980, "kept")]
    # the XML writers accept it
    root = ET.fromstring(write_nle(plan_to_timeline(out), NleFormat.XMEML).split("\n", 2)[2])
    assert root.findtext("sequence/duration") == str(out.sequence.duration_frames)


def test_ripple_uses_the_approved_removals_by_default(setup: Setup) -> None:
    plan = _plan(setup).model_copy(
        update={"removals": [PlanRemoval(start=500, end=530, kind="silence")]}
    )
    assert apply_removals(plan).sequence.duration_frames == plan.sequence.duration_frames - 30
    with pytest.raises(ValueError, match="nothing left"):
        apply_removals(plan, [PlanRemoval(start=0, end=plan.sequence.duration_frames, kind="x")])


def test_slice_rebases_everything_to_zero(setup: Setup) -> None:
    plan = _plan(setup).model_copy(
        update={"removals": [PlanRemoval(start=1700, end=1900, kind="silence")]}
    )
    clip = slice_plan(plan, 1000, 2500, name="Clip")
    assert clip.sequence.duration_frames == 1500 and clip.sequence.name == "Clip"
    assert [(e.start, e.end) for e in clip.video_events] == [(0, 798), (798, 1500)]
    assert [(m.frame, m.note) for m in clip.markers] == [(0, "kept")]
    assert [(r.start, r.end) for r in clip.removals] == [(700, 900)]
    host = clip.video_events[0]
    assert _secs(host.source_in_ticks) == pytest.approx(
        _secs(plan.video_events[1].source_in_ticks) + Fraction(700) / F,
        abs=1 / TICKS_PER_SECOND,
    )
    with pytest.raises(ValueError):
        slice_plan(plan, 5, 5)


# ------------------------------------------------------------------ social
def _framed(setup: Setup) -> EditPlan:
    project, cut, probes = setup
    vertical = Reframe(
        cx=0.3,
        cy=0.4,
        scale=1.0,
        path=[ReframeKey(frame=300, cx=0.3, cy=0.4), ReframeKey(frame=1500, cx=0.35, cy=0.4)],
    )
    segs = [
        cut.segments[0],
        cut.segments[1].model_copy(
            update={"reframe_vertical": vertical, "reframe": Reframe(cx=0.4, cy=0.5, scale=1.2)}
        ),
        cut.segments[2],
    ]
    return build_edit_plan(project, cut.model_copy(update={"segments": segs}), probes)


def test_one_plan_per_aspect_with_the_right_size_and_framing(setup: Setup) -> None:
    plan = _framed(setup)
    plans = build_social_plans(plan, 900, 2700, ["9:16", "4:5", "1:1", "16:9", "9:16"])
    assert [p.aspect for p in plans] == ["9:16", "4:5", "1:1", "16:9"]
    for p in plans:
        assert (p.sequence.width, p.sequence.height) == ASPECT_SIZES[p.aspect or ""]
        assert p.sequence.duration_frames == 1800
        assert p.method.value == "cuts" and p.video_tracks == []
        assert all(e.transform for e in p.video_events)  # every shot is framed (filled)
        assert p.sequence.name.endswith(p.aspect.replace(":", "x"))  # type: ignore[union-attr]
    vert = plans[0].video_events[0]
    assert vert.transform is not None
    # 9:16 follows the vertical path from the clip's frame 0 (old frame 900)
    assert len(vert.transform) == 2 and vert.transform[1].frame == 600
    # the 9:16 crop of a 1920x1080 source is full height: 177.8 %
    assert vert.transform[0].scale == pytest.approx(177.78, abs=0.01)
    # 16:9 uses the horizontal framing (1.2x punch-in)
    assert plans[3].video_events[0].transform[0].scale == pytest.approx(120.0)  # type: ignore[index]
    # 4:5 / 1:1 take the vertical path at the widest crop
    r = framing_for(plan.video_events[1], "1:1")
    assert r is not None and r.scale == 1.0 and r.path == plan.video_events[1].reframe_vertical.path  # type: ignore[union-attr]
    # a shot without framing is centred and filled
    guest = plans[2].video_events[1].transform
    assert guest is not None and (guest[0].x, guest[0].y) == (540.0, 540.0)
    assert guest[0].scale == pytest.approx(100.0)  # 1080 high source in a 1080x1080 frame


def test_watermark_end_page_and_jump_cuts(setup: Setup) -> None:
    plan = _framed(setup).model_copy(
        update={"removals": [PlanRemoval(start=1000, end=1060, kind="silence")]}
    )
    logo = Picture(path=Path("/brand/logo.png"), width=600, height=200)
    outro = Picture(
        path=Path("/brand/outro.mp4"),
        width=1080,
        height=1920,
        duration_s=5.0,
        fps=Fraction(30),
        has_audio=True,
    )
    options = SocialOptions(
        watermark=Watermark(logo, corner="top_right", size=0.2, opacity=0.8),
        end_page=EndPage(outro, seconds=3.0),
        jump_cuts=True,
    )
    (p,) = build_social_plans(plan, 900, 2700, ["9:16"], options)
    clip_frames = 1800 - 60  # the removal inside the range is rippled out
    end_frames = 89  # 3 s at 29.97
    assert p.sequence.duration_frames == clip_frames + end_frames
    assert p.removals == [] and p.rippled
    # end page: last event, fitted inside 1080x1920 (100 %), with its audio
    last = p.video_events[-1]
    assert (last.start, last.end) == (clip_frames, clip_frames + end_frames)
    assert last.transform is not None and last.transform[0].scale == pytest.approx(100.0)
    assert p.media_by_id()[last.clip_id].name == "outro.mp4"
    assert p.audio_tracks[-1].clip_id == last.clip_id
    # watermark: 20 % of 1080 wide = 216 px, top-right inside the margin, 80 % opacity
    (wm,) = p.overlays
    assert (wm.start, wm.end, wm.track, wm.opacity) == (0, clip_frames, 1, 0.8)
    assert wm.transform is not None
    key = wm.transform[0]
    assert key.scale == pytest.approx(36.0)  # 216 / 600
    margin = 0.04 * 1080
    assert key.x == pytest.approx(1080 - margin - 108)
    assert key.y == pytest.approx(margin + 36)

    xml = write_nle(plan_to_timeline(p), NleFormat.XMEML)
    root = ET.fromstring(xml.split("\n", 2)[2])
    assert root.findtext("sequence/media/video/format/samplecharacteristics/width") == "1080"
    tracks = root.findall("sequence/media/video/track")
    assert len(tracks) == 2  # picture + watermark
    assert [e.findtext("effectid") for e in tracks[1].iter("effect")] == ["basic", "opacity"]
    assert "logo.png" in xml and "outro.mp4" in xml


def test_bad_social_requests(setup: Setup) -> None:
    plan = _framed(setup)
    with pytest.raises(ValueError, match="aspects"):
        build_social_plans(plan, 0, 100, ["2:1"])
    with pytest.raises(ValueError, match="aspects"):
        build_social_plans(plan, 0, 100, [])


def test_still_sizes_come_from_the_header(tmp_path: Path) -> None:
    import struct
    import zlib

    from multicam_engine.editplan.social import load_picture
    from multicam_engine.media.image import ImageError, image_size

    ihdr = struct.pack(">IIBBBBB", 640, 360, 8, 2, 0, 0, 0)
    png = (
        b"\x89PNG\r\n\x1a\n"
        + struct.pack(">I", len(ihdr))
        + b"IHDR"
        + ihdr
        + struct.pack(">I", zlib.crc32(b"IHDR" + ihdr))
    )
    (tmp_path / "logo.png").write_bytes(png)
    assert image_size(tmp_path / "logo.png") == (640, 360)
    pic = load_picture(tmp_path / "logo.png")
    assert (pic.width, pic.height, pic.duration_s) == (640, 360, None)
    (tmp_path / "bad.png").write_bytes(b"not an image")
    with pytest.raises(ImageError):
        image_size(tmp_path / "bad.png")
