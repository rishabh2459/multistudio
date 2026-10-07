"""CutList + layout + probes -> EditPlan (and back to an NleTimeline for the writers)."""

from __future__ import annotations

import math
from fractions import Fraction
from itertools import pairwise
from pathlib import Path
from uuid import UUID

from multicam_engine.editplan.model import (
    LOW_CONFIDENCE,
    TICKS_PER_SECOND,
    AudioTrack,
    EditPlan,
    HostApp,
    MarkerColor,
    PlanMarker,
    PlanMedia,
    PlanMethod,
    PlanPiece,
    PlanRemoval,
    PlanSequence,
    PlanTransformKey,
    TrackPiece,
    VideoEvent,
    VideoTrack,
)
from multicam_engine.editplan.transform import crop_transform
from multicam_engine.export._util import to_frames
from multicam_engine.export.timeline import (
    ClipMapper,
    Event,
    Marker,
    NleTimeline,
    Source,
    TransformKey,
    build_nle_timeline,
    make_source,
)
from multicam_engine.layout import LayoutError, resolve_layout, role_layout
from multicam_engine.media.probe import ProbeResult
from multicam_engine.models.cutlist import CutList
from multicam_engine.models.project import CameraLayout, Project, ShotType
from multicam_engine.models.time import Rational
from multicam_engine.render.plan import clip_timing, covered_frames


def _cameras(project: Project) -> list[CameraLayout]:
    try:
        return resolve_layout(project).all_cameras
    except LayoutError:
        return role_layout(project)[1]


def _piece_times(src: Source, source_in: Fraction) -> dict[str, int]:
    return {
        "source_in_frame": to_frames(source_in, src.fps),
        "source_in_sample": math.floor(source_in * src.sample_rate + Fraction(1, 2)),
        "source_in_ticks": math.floor(source_in * TICKS_PER_SECOND + Fraction(1, 2)),
    }


def _rational(value: Fraction) -> Rational:
    return Rational(num=value.numerator, den=value.denominator)


def build_edit_plan(
    project: Project,
    cutlist: CutList,
    probes: dict[UUID, ProbeResult],
    *,
    cutlist_version: int | None = None,
    method: PlanMethod = PlanMethod.STACKED_ENABLE,
    host: HostApp = HostApp.GENERIC,
    host_refs: dict[UUID, str] | None = None,
    name: str | None = None,
    host_start_frame: int = 0,
    low_confidence: float = LOW_CONFIDENCE,
) -> EditPlan:
    """The edit as host operations. Uses the same timing rules as the render and
    the XML export (offset + drift, unrecorded frames left empty)."""
    tl = build_nle_timeline(project, cutlist, probes, name=name)
    fps = tl.fps
    host_refs = host_refs or {}
    layouts = {c.clip_id: c for c in _cameras(project)}
    cameras = [c for c in _cameras(project) if c.shot is not ShotType.BROLL and c.clip_id in probes]
    # A clip shown in the cut gets an angle and a track even if it is not an
    # auto-selected camera (hand-placed B-roll), so every live shot has a source.
    shown = {s.clip_id for s in cutlist.segments}
    known = {c.clip_id for c in cameras}
    for clip in project.clips:
        if clip.id in shown and clip.id not in known and clip.id in probes:
            cameras.append(
                layouts.get(clip.id)
                or CameraLayout(clip_id=clip.id, shot=ShotType.BROLL, covers=[])
            )
            known.add(clip.id)

    # Every camera and every clip used for picture or sound becomes a media item.
    media_ids = [c.clip_id for c in cameras]
    media_ids += [cid for cid in tl.sources if cid not in media_ids]
    sources = {
        cid: tl.sources.get(cid) or make_source(project, cid, probes[cid]) for cid in media_ids
    }
    mappers = {
        cid: ClipMapper(clip_timing(project.clip(cid), probes[cid]), probes[cid], fps)
        for cid in media_ids
    }
    angles = {c.clip_id: i for i, c in enumerate(cameras, start=1)}
    audio_index = {cid: i for i, cid in enumerate(tl.audio, start=1)}

    media: list[PlanMedia] = []
    for cid in media_ids:
        src, mapper = sources[cid], mappers[cid]
        shot = layouts[cid].shot if cid in layouts else ShotType.BROLL
        media.append(
            PlanMedia(
                clip_id=cid,
                path=str(src.path),
                name=src.name,
                label=src.label,
                host_ref=host_refs.get(cid),
                fps=_rational(src.fps),
                duration_frames=to_frames(src.duration, src.fps),
                width=src.width,
                height=src.height,
                has_audio=src.has_audio,
                audio_channels=src.audio_channels,
                sample_rate=src.sample_rate,
                start_timecode_frames=src.start_tc_frames,
                has_timecode=src.has_timecode,
                shot=shot,
                angle=angles.get(cid),
                video_track=angles.get(cid),
                audio_track=audio_index.get(cid),
                record_start_frame=-to_frames(mapper.media_time(0), fps),
                drift_ppm=float(mapper.timing.speed - 1) * 1e6,
            )
        )

    events: list[VideoEvent] = []
    for ev in tl.video:
        seg = cutlist.segment_at(ev.start)
        events.append(
            VideoEvent(
                start=ev.start,
                end=ev.end,
                clip_id=ev.clip_id,
                **_piece_times(sources[ev.clip_id], ev.source_in),
                shot=layouts[ev.clip_id].shot if ev.clip_id in layouts else ShotType.BROLL,
                confidence=seg.confidence,
                reframe=seg.reframe,
                reframe_vertical=seg.reframe_vertical,
                transform=crop_transform(
                    seg.reframe,
                    (sources[ev.clip_id].width, sources[ev.clip_id].height),
                    (tl.width, tl.height),
                    ev.start,
                    ev.end,
                ),
            )
        )

    # Stacked: every camera on its own track, split at every cut, live piece enabled.
    bounds = [s.start_frame for s in cutlist.segments] + [cutlist.duration_frames]
    tracks: list[VideoTrack] = []
    for cam in cameras:
        cid, src, mapper = cam.clip_id, sources[cam.clip_id], mappers[cam.clip_id]
        pieces: list[TrackPiece] = []
        for (a, b), seg in zip(pairwise(bounds), cutlist.segments, strict=True):
            head, tail = covered_frames(mapper.timing, fps, a, b - a, src.fps)
            start, end = a + head, b - tail
            if end > start:
                on_air = seg.clip_id == cid
                pieces.append(
                    TrackPiece(
                        start=start,
                        end=end,
                        clip_id=cid,
                        **_piece_times(src, mapper.media_time(start)),
                        enabled=on_air,
                        transform=crop_transform(
                            seg.reframe, (src.width, src.height), (tl.width, tl.height), start, end
                        )
                        if on_air
                        else None,
                    )
                )
        tracks.append(VideoTrack(index=angles[cid], clip_id=cid, pieces=pieces))

    audio_tracks = [
        AudioTrack(
            index=audio_index[cid],
            clip_id=cid,
            gain_db=cutlist.audio.gains_db.get(cid, 0.0),
            pieces=[
                PlanPiece(
                    start=e.start,
                    end=e.end,
                    clip_id=cid,
                    **_piece_times(sources[cid], e.source_in),
                )
                for e in evs
            ],
        )
        for cid, evs in tl.audio.items()
    ]

    markers = [
        PlanMarker(
            frame=seg.start_frame,
            color=MarkerColor.YELLOW,
            kind="low_confidence",
            note=f"Check this cut: auto-edit is unsure (confidence {seg.confidence:.2f})",
        )
        for seg in cutlist.segments[1:]
        if seg.confidence is not None and seg.confidence < low_confidence
    ]
    removals = [
        PlanRemoval(start=r.start_frame, end=r.end_frame, kind=r.kind.value)
        for r in cutlist.removals
        if r.approved
    ]
    return EditPlan(
        project_id=project.id,
        cutlist_version=cutlist_version if cutlist_version is not None else cutlist.version,
        host=host,
        method=method,
        sequence=PlanSequence(
            name=tl.name,
            fps=cutlist.fps,
            width=tl.width,
            height=tl.height,
            duration_frames=tl.duration_frames,
            host_start_frame=host_start_frame,
        ),
        media=media,
        video_events=events,
        video_tracks=tracks,
        audio_mode=cutlist.audio.mode,
        audio_tracks=audio_tracks,
        removals=removals,
        markers=markers,
        warnings=list(tl.warnings),
    )


def piece_seconds(piece: PlanPiece) -> Fraction:
    """Source position of a piece in exact seconds (from its Premiere ticks)."""
    return Fraction(piece.source_in_ticks, TICKS_PER_SECOND)


def _keys(keys: list[PlanTransformKey] | None) -> tuple[TransformKey, ...]:
    return tuple(TransformKey(k.frame, k.scale, k.x, k.y) for k in keys or [])


def _event(piece: PlanPiece, transform: list[PlanTransformKey] | None = None) -> Event:
    return Event(piece.clip_id, piece.start, piece.end, piece_seconds(piece), _keys(transform))


def plan_to_timeline(plan: EditPlan, *, stacked: bool | None = None) -> NleTimeline:
    """The plan as the XML/EDL writers' input (Rule C fallback).

    ``stacked`` forces (True) or suppresses (False) the one-track-per-camera layout;
    default: stacked for the ``stacked_enable`` method."""
    if stacked is None:
        stacked = plan.method is PlanMethod.STACKED_ENABLE
    sources: dict[UUID, Source] = {}
    for m in plan.media:
        fps = m.fps.to_fraction()
        sources[m.clip_id] = Source(
            clip_id=m.clip_id,
            path=Path(m.path),
            name=m.name,
            label=m.label,
            fps=fps,
            duration=Fraction(m.duration_frames) / fps,
            width=m.width,
            height=m.height,
            has_audio=m.has_audio,
            audio_channels=m.audio_channels,
            sample_rate=m.sample_rate,
            start_tc_frames=m.start_timecode_frames,
            has_timecode=m.has_timecode,
            has_video=m.width > 0,
        )
    return NleTimeline(
        name=plan.sequence.name,
        fps=plan.sequence.fps.to_fraction(),
        width=plan.sequence.width,
        height=plan.sequence.height,
        duration_frames=plan.sequence.duration_frames,
        sources=sources,
        video=[_event(e, e.transform) for e in plan.video_events],
        audio={
            t.clip_id: [_event(p) for p in t.pieces]
            for t in sorted(plan.audio_tracks, key=lambda t: t.index)
        },
        warnings=list(plan.warnings),
        markers=[Marker(m.frame, m.note, m.color.value) for m in plan.markers],
        stacked=[
            [(_event(p, p.transform), p.enabled) for p in t.pieces]
            for t in sorted(plan.video_tracks, key=lambda t: t.index)
        ]
        if stacked
        else [],
        overlays=[
            [
                Event(
                    o.clip_id,
                    o.start,
                    o.end,
                    piece_seconds(o),
                    _keys(o.transform),
                    None if o.opacity >= 1.0 else o.opacity,
                )
                for o in plan.overlays
                if o.track == track
            ]
            for track in sorted({o.track for o in plan.overlays})
        ],
    )
