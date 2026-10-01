"""The edit as an NLE sees it: clips placed on video/audio tracks, with source
in-points, ready to be written as FCPXML, Premiere XML or EDL.

Uses the render plan's timing (offset + clock drift), so an exported timeline
cuts exactly where the render does:

* video: one event per CutList segment, trimmed to what the camera recorded
  (a gap stays empty = black, like in the render);
* audio: one track per camera. Clock drift cannot be expressed in an NLE, so a
  camera's audio is split into pieces whenever continuous playback would drift
  more than a quarter frame away from sync; without drift it is one clip.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from fractions import Fraction
from itertools import pairwise
from pathlib import Path
from uuid import UUID

from multicam_engine.export.timecode import timecode_rate, timecode_to_frames
from multicam_engine.media.probe import ProbeResult
from multicam_engine.models.cutlist import AudioMode, CutList
from multicam_engine.models.project import Project
from multicam_engine.render.plan import ClipTiming, clip_timing, covered_frames


@dataclass(frozen=True)
class Source:
    """One camera file as a media item in the NLE."""

    clip_id: UUID
    path: Path
    name: str
    label: str
    fps: Fraction
    duration: Fraction  # seconds
    width: int
    height: int
    has_audio: bool
    audio_channels: int
    sample_rate: int
    #: Start timecode in frames at the file's rate (0 if none embedded).
    start_tc_frames: int
    has_timecode: bool
    has_video: bool = True

    @property
    def start_seconds(self) -> Fraction:
        """Media time of the first frame in the NLE's clock (the start timecode)."""
        return self.start_tc_frames / self.fps if self.has_timecode else Fraction(0)


@dataclass(frozen=True)
class Event:
    """A clip on a track: timeline frames [start, end) show media from ``source_in``."""

    clip_id: UUID
    start: int  # timeline frames
    end: int
    source_in: Fraction  # seconds since the file's first frame

    @property
    def frames(self) -> int:
        return self.end - self.start


@dataclass(frozen=True)
class Marker:
    """A note at a timeline frame (e.g. "check this cut")."""

    frame: int
    note: str
    color: str = "yellow"  # red | yellow | green | blue


@dataclass
class NleTimeline:
    name: str
    fps: Fraction
    width: int
    height: int
    duration_frames: int
    sources: dict[UUID, Source]
    video: list[Event]
    audio: dict[UUID, list[Event]]  # one track per camera, in source order
    warnings: list[str] = field(default_factory=list)
    markers: list[Marker] = field(default_factory=list)

    def source_out(self, event: Event) -> Fraction:
        return event.source_in + Fraction(event.frames) / self.fps


class ClipMapper:
    """Timeline frame -> media time for one clip (seconds since its first frame)."""

    def __init__(self, timing: ClipTiming, probe: ProbeResult, fps: Fraction) -> None:
        self.timing = timing
        self.fps = fps
        starts = [probe.video_start]
        if probe.audio_start is not None:
            starts.append(probe.audio_start)
        self.zero = min(starts)

    def media_time(self, frame: int) -> Fraction:
        return self.timing.pts_at(Fraction(frame) / self.fps) - self.zero


def make_source(project: Project, clip_id: UUID, probe: ProbeResult) -> Source:
    clip = project.clip(clip_id)
    media = probe.media
    fps = media.fps.to_fraction()
    tc_frames, has_tc = 0, False
    if media.start_timecode:
        try:
            tc_frames = timecode_to_frames(media.start_timecode, timecode_rate(fps))
            has_tc = True
        except ValueError:
            pass
    return Source(
        clip_id=clip_id,
        path=Path(clip.path),
        name=Path(clip.path).name,
        label=clip.speaker_label or Path(clip.path).stem,
        fps=fps,
        duration=probe.duration,
        width=media.width,
        height=media.height,
        has_audio=probe.audio_stream_index is not None,
        audio_channels=media.audio_channels or 2,
        sample_rate=media.audio_sample_rate or 48000,
        start_tc_frames=tc_frames,
        has_timecode=has_tc,
        has_video=media.has_video,
    )


def _audio_clip_ids(
    project: Project, cutlist: CutList, probes: dict[UUID, ProbeResult]
) -> list[UUID]:
    with_audio = [
        c.id
        for c in project.clips
        if c.id in probes and probes[c.id].audio_stream_index is not None
    ]
    cfg = cutlist.audio
    if cfg.mode is AudioMode.SINGLE and cfg.single_clip_id in with_audio:
        return [cfg.single_clip_id]
    chosen = [cid for cid in with_audio if cid in cfg.gains_db]
    return chosen or with_audio


def _audio_events(
    clip_id: UUID, mapper: ClipMapper, probe: ProbeResult, cuts: list[int], fps: Fraction
) -> list[Event]:
    timing = mapper.timing
    audio_start = probe.audio_start if probe.audio_start is not None else probe.video_start
    audio_end_pos = probe.duration + probe.video_start - audio_start  # seconds of audio
    tolerance = Fraction(1, 4) / fps
    step = timing.speed / fps
    drift = abs(timing.speed - 1)
    # Without drift one clip plays in sync for ever; with drift, at most this long.
    max_frames = math.floor(tolerance / drift * fps) if drift else None

    def pos(frame: int) -> Fraction:
        return timing.audio_position(Fraction(frame) / fps)

    def in_sync(start: int, source_in: Fraction, frame: int) -> bool:
        continuous = source_in + Fraction(frame - start) / fps
        return abs(continuous - mapper.media_time(frame)) <= tolerance

    events: list[Event] = []
    for a, b in pairwise(cuts):
        # frames of [a, b) where the camera has audio: 0 <= position < audio_end_pos
        first = a + max(0, math.ceil(-pos(a) / step))
        last = a + math.ceil((audio_end_pos - pos(a)) / step)  # exclusive
        start, end = max(a, first), min(b, last)
        while end > start:
            piece_end = min(end, start + max_frames) if max_frames else end
            prev = events[-1] if events else None
            if prev and prev.end == start and in_sync(prev.start, prev.source_in, piece_end):
                events[-1] = Event(clip_id, prev.start, piece_end, prev.source_in)
            else:
                events.append(Event(clip_id, start, piece_end, mapper.media_time(start)))
            start = piece_end
    return events


def build_nle_timeline(
    project: Project, cutlist: CutList, probes: dict[UUID, ProbeResult], name: str | None = None
) -> NleTimeline:
    cutlist.check_against(project)
    fps = cutlist.fps.to_fraction()
    used = {s.clip_id for s in cutlist.segments} | set(_audio_clip_ids(project, cutlist, probes))
    missing = [str(cid) for cid in used if cid not in probes]
    if missing:
        raise ValueError(f"clips not probed: {', '.join(missing)}")

    sources = {cid: make_source(project, cid, probes[cid]) for cid in sorted(used, key=str)}
    mappers = {
        cid: ClipMapper(clip_timing(project.clip(cid), probes[cid]), probes[cid], fps)
        for cid in used
    }
    warnings: list[str] = []

    video: list[Event] = []
    for seg in cutlist.segments:
        mapper = mappers[seg.clip_id]
        src_fps = sources[seg.clip_id].fps
        head, tail = covered_frames(
            mapper.timing, fps, seg.start_frame, seg.duration_frames, src_fps
        )
        start, end = seg.start_frame + head, seg.end_frame - tail
        if end > start:
            video.append(Event(seg.clip_id, start, end, mapper.media_time(start)))
        if head or tail:
            warnings.append(
                f"{sources[seg.clip_id].name}: {head + tail} frame(s) at "
                f"{seg.start_frame}-{seg.end_frame} were not recorded (left empty)"
            )

    cuts = sorted({0, cutlist.duration_frames} | {s.start_frame for s in cutlist.segments})
    audio = {
        cid: _audio_events(cid, mappers[cid], probes[cid], cuts, fps)
        for cid in _audio_clip_ids(project, cutlist, probes)
    }

    for cid, source in sources.items():
        drift = mappers[cid].timing.speed - 1
        if drift and cid in audio and len(audio[cid]) > 1:
            warnings.append(
                f"{source.name}: clock drift {float(drift) * 1e6:.1f} ppm; audio split into "
                f"{len(audio[cid])} pieces to stay in sync"
            )
        if source.fps != fps:
            warnings.append(
                f"{source.name}: {float(source.fps):.3f} fps on a {float(fps):.3f} fps timeline"
            )
    return NleTimeline(
        name=name or project.name,
        fps=fps,
        width=project.output.width,
        height=project.output.height,
        duration_frames=cutlist.duration_frames,
        sources=sources,
        video=video,
        audio=audio,
        warnings=warnings,
    )
