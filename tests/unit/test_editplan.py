"""EditPlan: the host-neutral edit (PL2)."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from fractions import Fraction
from uuid import UUID

import pytest

from multicam_engine.editplan import (
    TICKS_PER_SECOND,
    EditPlan,
    HostApp,
    PlanMethod,
    build_edit_plan,
    plan_to_timeline,
)
from multicam_engine.export import NleFormat, build_nle_timeline, write_nle
from multicam_engine.media.probe import ProbeResult
from multicam_engine.models import CutList, Project
from multicam_engine.models.cutlist import Removal, RemovalKind
from multicam_engine.models.project import ShotType

Setup = tuple[Project, CutList, dict[UUID, ProbeResult]]


def _plan(setup: Setup, **kw: object) -> EditPlan:
    project, cut, probes = setup
    return build_edit_plan(project, cut, probes, **kw)  # type: ignore[arg-type]


def test_live_events_match_the_nle_timeline(setup: Setup) -> None:
    project, cut, probes = setup
    plan = _plan(setup)
    tl = build_nle_timeline(project, cut, probes)
    assert [(e.clip_id, e.start, e.end) for e in plan.video_events] == [
        (e.clip_id, e.start, e.end) for e in tl.video
    ]
    for pe, te in zip(plan.video_events, tl.video, strict=True):
        assert abs(Fraction(pe.source_in_ticks, TICKS_PER_SECOND) - te.source_in) < Fraction(
            1, TICKS_PER_SECOND
        )
    assert [e.shot for e in plan.video_events] == [ShotType.WIDE, ShotType.SOLO, ShotType.SOLO]
    assert plan.cut_count == 2
    assert plan.method is PlanMethod.STACKED_ENABLE


def test_media_placement_and_tracks(setup: Setup) -> None:
    project, _cut, _ = setup
    host, guest, wide = project.clips
    plan = _plan(setup, host=HostApp.PREMIERE, host_refs={host.id: "pp:item:1"})
    media = plan.media_by_id()
    assert [m.clip_id for m in plan.media] == [host.id, guest.id, wide.id]
    assert [media[c.id].angle for c in (host, guest, wide)] == [1, 2, 3]
    assert media[host.id].host_ref == "pp:item:1" and media[guest.id].host_ref is None
    assert media[host.id].record_start_frame == 0
    assert media[guest.id].record_start_frame == -30  # started 1 s earlier (29.97 fps)
    assert media[wide.id].record_start_frame == 60  # started 2 s later
    assert media[wide.id].drift_ppm == pytest.approx(100.0)
    assert media[host.id].start_timecode_frames > 0 and media[host.id].has_timecode


def test_stacked_tracks_split_at_every_cut_with_one_live_piece(setup: Setup) -> None:
    _project, cut, _ = setup
    plan = _plan(setup)
    assert [t.index for t in plan.video_tracks] == [1, 2, 3]
    bounds = [s.start_frame for s in cut.segments]
    for track in plan.video_tracks:
        for piece in track.pieces:
            # a piece never crosses a cut
            inside = [b for b in bounds if piece.start < b < piece.end]
            assert not inside
    enabled = sorted(
        (p.start, p.end, p.clip_id) for t in plan.video_tracks for p in t.pieces if p.enabled
    )
    assert enabled == [(e.start, e.end, e.clip_id) for e in plan.video_events]


def test_audio_tracks_carry_gain_and_drift_pieces(setup: Setup) -> None:
    project, _cut, _ = setup
    wide = project.clips[2]
    plan = _plan(setup)
    tracks = {t.clip_id: t for t in plan.audio_tracks}
    assert tracks[wide.id].gain_db == -6.0
    assert len(tracks[wide.id].pieces) > 1  # 100 ppm drift -> split to stay in sync


def test_low_confidence_cuts_and_removals(setup: Setup) -> None:
    project, cut, probes = setup
    segs = [
        cut.segments[0],
        cut.segments[1].model_copy(update={"confidence": 0.95}),
        cut.segments[2].model_copy(update={"confidence": 0.3}),
    ]
    cut2 = cut.model_copy(
        update={
            "segments": segs,
            "removals": [
                Removal(start_frame=400, end_frame=420, kind=RemovalKind.FILLER, approved=True),
                Removal(start_frame=500, end_frame=520, kind=RemovalKind.SILENCE),
            ],
        }
    )
    plan = build_edit_plan(project, cut2, probes)
    assert [(m.frame, m.kind) for m in plan.markers] == [(1798, "low_confidence")]
    assert [(r.start, r.end) for r in plan.removals] == [(400, 420)]  # approved only
    assert plan.video_events[-1].confidence == 0.3

    tl = plan_to_timeline(plan)
    fcpxml = ET.fromstring(write_nle(tl, NleFormat.FCPXML).split("\n", 2)[2])
    assert next(m.get("value", "") for m in fcpxml.iter("marker")).startswith("Check this cut")
    xmeml = ET.fromstring(write_nle(tl, NleFormat.XMEML).split("\n", 2)[2])
    assert [m.findtext("in") for m in xmeml.iter("marker")] == ["1798"]
    assert "* LOC: 00:00:59;28 YELLOW" in write_nle(tl, NleFormat.EDL)


def test_plan_round_trips_and_writes_the_same_xml(setup: Setup) -> None:
    project, cut, probes = setup
    plan = _plan(setup)
    again = EditPlan.model_validate_json(plan.model_dump_json())
    assert again == plan
    direct = build_nle_timeline(project, cut, probes)
    via = plan_to_timeline(plan)
    assert [(e.clip_id, e.start, e.end) for e in via.video] == [
        (e.clip_id, e.start, e.end) for e in direct.video
    ]
    assert {k: [(e.start, e.end) for e in v] for k, v in via.audio.items()} == {
        k: [(e.start, e.end) for e in v] for k, v in direct.audio.items()
    }
    # Same cuts in the EDL (sources are listed in a different order, reels match by name).
    direct_edl = [ln for ln in write_nle(direct, NleFormat.EDL).splitlines() if ln[:3].isdigit()]
    via_edl = [ln for ln in write_nle(via, NleFormat.EDL).splitlines() if ln[:3].isdigit()]
    assert [ln.split()[4:] for ln in via_edl] == [ln.split()[4:] for ln in direct_edl]


def test_bad_plans_are_rejected(setup: Setup) -> None:
    plan = _plan(setup)
    data = plan.model_dump(mode="json")
    data["video_events"] = list(reversed(data["video_events"]))
    with pytest.raises(ValueError, match="sorted"):
        EditPlan.model_validate(data)


def _with_mic(setup: Setup) -> tuple[Setup, UUID]:
    import dataclasses
    from pathlib import Path

    from multicam_engine.models.project import AUDIO_ONLY_FPS, Clip, ClipRole, MediaInfo

    project, cut, probes = setup
    host = project.clips[0]
    media = MediaInfo(
        fps=AUDIO_ONLY_FPS,
        is_vfr=False,
        has_video=False,
        duration_frames=70_000,
        width=0,
        height=0,
        video_codec="",
        audio_codec="pcm_s24le",
        audio_sample_rate=48000,
        audio_channels=1,
    )
    mic = Clip(path="/rec/zoom h6.wav", role=ClipRole.MIC, media=media)
    assert host.sync is not None
    mic.sync = host.sync.model_copy(update={"offset_samples": 48000 // 2})  # 0.5 s early
    project = project.model_copy(update={"clips": [*project.clips, mic]})
    cut = cut.model_copy(update={"audio": cut.audio.model_copy(update={"gains_db": {mic.id: 0.0}})})
    probe = dataclasses.replace(
        probes[host.id],
        path=Path(mic.path),
        media=media,
        video_stream_index=None,
        audio_stream_index=0,
    )
    return (project, cut, {**probes, mic.id: probe}), mic.id


def test_sound_only_mic_is_audio_only_everywhere(setup: Setup) -> None:
    (project, cut, probes), mic_id = _with_mic(setup)
    plan = build_edit_plan(project, cut, probes)
    mic = plan.media_by_id()[mic_id]
    assert mic.width == 0 and mic.video_track is None and mic.angle is None
    assert mic.audio_track == 1 and [t.clip_id for t in plan.audio_tracks] == [mic_id]
    assert mic_id not in {t.clip_id for t in plan.video_tracks}
    assert mic_id not in {e.clip_id for e in plan.video_events}
    assert mic.record_start_frame == -15  # started 0.5 s before the reference

    tl = plan_to_timeline(plan)
    fcp = ET.fromstring(write_nle(tl, NleFormat.FCPXML).split("\n", 2)[2])
    assets = {a.get("id"): a for a in fcp.iter("asset")}
    formats = {f.get("id") for f in fcp.iter("format")}
    mic_asset = next(a for a in assets.values() if a.get("name") == "zoom h6.wav")
    assert mic_asset.get("hasVideo") is None and mic_asset.get("format") is None
    assert mic_asset.get("hasAudio") == "1"
    for a in assets.values():  # structural check: every reference resolves
        assert a.get("format") is None or a.get("format") in formats
    for clip in fcp.iter("asset-clip"):
        assert clip.get("ref") in assets

    xm = ET.fromstring(write_nle(tl, NleFormat.XMEML).split("\n", 2)[2])
    files = [f for f in xm.iter("file") if f.findtext("name") == "zoom h6.wav"]
    assert files and files[0].find("media/video") is None
    assert files[0].find("media/audio") is not None
    edl = write_nle(tl, NleFormat.EDL)
    assert "zoom h6" not in edl  # EDLs list the picture cut only
