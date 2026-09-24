"""Render plan: exact mapping from output frames to source frames and samples.

Pure arithmetic on ``Fraction`` (no ffmpeg), so every cut is unit-testable.

Timeline convention
    Output frame ``n`` is shown at ``t = n / fps`` seconds on the *reference*
    timeline (time 0 = the reference clip's first audio sample). For a clip with
    sync result (offset ``o`` seconds, drift ``k``), reference time ``t`` is the
    clip's audio position ``t * (1 + k) + o``, i.e. container timestamp

        pts(t) = audio_start + t * (1 + k) + o

    Video is read at those timestamps (retimed by ``1 + k``, then converted to
    constant frame rate); audio is resampled along the same line. One formula for
    both, so picture and sound stay locked, cut after cut.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from uuid import UUID

from multicam_engine.media.probe import ProbeResult
from multicam_engine.models.cutlist import AudioMode, CutList, Reframe
from multicam_engine.models.project import Clip, Project


class RenderPlanError(ValueError):
    """The project/cutlist cannot be rendered as given."""


@dataclass(frozen=True)
class ClipTiming:
    """How one clip maps onto the reference timeline."""

    path: Path
    offset: Fraction  # seconds, project sign convention
    speed: Fraction  # 1 + drift
    audio_start: Fraction  # container time of audio sample 0
    video_start: Fraction  # container time of the first video frame
    video_end: Fraction  # container time just after the last video frame

    def pts_at(self, t: Fraction) -> Fraction:
        """Container timestamp in this clip that is on screen at reference time ``t``."""
        return self.audio_start + t * self.speed + self.offset

    def audio_position(self, t: Fraction) -> Fraction:
        """Seconds since this clip's first audio sample at reference time ``t``."""
        return t * self.speed + self.offset


@dataclass(frozen=True)
class VideoPiece:
    """One CutList segment: ``frames`` output frames from one clip (or black)."""

    index: int
    clip_id: UUID
    start_frame: int  # in the output
    frames: int
    head_black: int  # frames before the clip starts recording
    tail_black: int  # frames after it stops
    source_pts: Fraction | None  # container time shown on the first covered frame
    speed: Fraction
    path: Path | None
    reframe: Reframe | None = None

    @property
    def covered(self) -> int:
        return self.frames - self.head_black - self.tail_black

    @property
    def is_black(self) -> bool:
        return self.covered <= 0


@dataclass(frozen=True)
class AudioTrack:
    clip_id: UUID
    timing: ClipTiming
    gain: float  # linear


@dataclass(frozen=True)
class RenderPlan:
    fps: Fraction
    width: int
    height: int
    total_frames: int
    pieces: list[VideoPiece]
    chunks: list[list[int]]  # piece indices rendered together by one ffmpeg run
    audio: list[AudioTrack]
    warnings: list[str] = field(default_factory=list)

    @property
    def duration(self) -> Fraction:
        return Fraction(self.total_frames) / self.fps


def clip_timing(clip: Clip, probe: ProbeResult) -> ClipTiming:
    sync = clip.sync
    offset = Fraction(sync.offset_samples, sync.sample_rate) if sync else Fraction(0)
    drift = Fraction(sync.drift_ppm).limit_denominator(10**9) / 10**6 if sync else Fraction(0)
    audio_start = probe.audio_start if probe.audio_start is not None else probe.video_start
    return ClipTiming(
        path=Path(clip.path),
        offset=offset,
        speed=1 + drift,
        audio_start=audio_start,
        video_start=probe.video_start,
        video_end=probe.video_start + probe.duration,
    )


def _covered_frames(
    timing: ClipTiming, fps: Fraction, start_frame: int, frames: int, src_fps: Fraction
) -> tuple[int, int]:
    """(head, tail): uncovered frames at the start and end of a segment."""
    half = Fraction(1, 2) / src_fps  # a frame "exists" within half a source frame
    first_ok, last_ok = timing.video_start - half, timing.video_end - half

    def pts(j: int) -> Fraction:
        return timing.pts_at(Fraction(start_frame + j) / fps)

    step = timing.speed / fps
    # first j with pts(j) >= first_ok  /  last j with pts(j) < last_ok
    head = max(0, min(frames, math.ceil((first_ok - pts(0)) / step)))
    last = math.ceil((last_ok - pts(0)) / step) - 1
    tail = max(0, min(frames - head, frames - 1 - last))
    return head, tail


def chunk_pieces(
    pieces: list[VideoPiece], fps: Fraction, chunk_seconds: float, max_pieces: int
) -> list[list[int]]:
    """Group consecutive pieces so no ffmpeg run gets too big a filter graph."""
    limit = Fraction(chunk_seconds).limit_denominator(1000) * fps
    chunks: list[list[int]] = []
    current: list[int] = []
    frames = 0
    for piece in pieces:
        if current and (frames + piece.frames > limit or len(current) >= max_pieces):
            chunks.append(current)
            current, frames = [], 0
        current.append(piece.index)
        frames += piece.frames
    if current:
        chunks.append(current)
    return chunks


def build_plan(
    project: Project,
    cutlist: CutList,
    probes: dict[UUID, ProbeResult],
    *,
    width: int | None = None,
    height: int | None = None,
    chunk_seconds: float = 300.0,
    max_pieces_per_chunk: int = 24,
) -> RenderPlan:
    cutlist.check_against(project)
    fps = cutlist.fps.to_fraction()
    warnings: list[str] = []
    timings: dict[UUID, ClipTiming] = {}
    for clip in project.clips:
        if clip.id in probes:
            timings[clip.id] = clip_timing(clip, probes[clip.id])

    pieces: list[VideoPiece] = []
    for i, seg in enumerate(cutlist.segments):
        if seg.clip_id not in timings:
            raise RenderPlanError(f"segment {i}: clip {seg.clip_id} was not probed")
        clip = project.clip(seg.clip_id)
        timing = timings[seg.clip_id]
        if clip.sync is None and clip.id != project.reference_clip_id:
            warnings.append(f"{Path(clip.path).name}: not synced; assuming offset 0")
        src_fps = probes[seg.clip_id].media.fps.to_fraction()
        n = seg.duration_frames
        head, tail = _covered_frames(timing, fps, seg.start_frame, n, src_fps)
        covered = n - head - tail
        if covered <= 0:
            warnings.append(
                f"segment {i} ({Path(clip.path).name}, frames {seg.start_frame}-{seg.end_frame}): "
                "camera was not recording; rendered black"
            )
            head, tail = n, 0
        elif head or tail:
            warnings.append(
                f"segment {i} ({Path(clip.path).name}): {head + tail} frame(s) outside the "
                "recording rendered black"
            )
        first = Fraction(seg.start_frame + head) / fps
        pieces.append(
            VideoPiece(
                index=i,
                clip_id=seg.clip_id,
                start_frame=seg.start_frame,
                frames=n,
                head_black=head,
                tail_black=tail,
                source_pts=timing.pts_at(first) if covered > 0 else None,
                speed=timing.speed,
                path=timing.path if covered > 0 else None,
                reframe=seg.reframe,
            )
        )

    audio: list[AudioTrack] = []
    cfg = cutlist.audio
    if cfg.mode is AudioMode.SINGLE:
        if cfg.single_clip_id not in timings:
            raise RenderPlanError("audio clip for 'single' mode was not probed")
        audio.append(AudioTrack(cfg.single_clip_id, timings[cfg.single_clip_id], 1.0))
    else:
        for clip_id, gain_db in cfg.gains_db.items():
            if clip_id in timings and probes[clip_id].audio_stream_index is not None:
                audio.append(AudioTrack(clip_id, timings[clip_id], 10 ** (gain_db / 20)))
    if not audio:
        warnings.append("no audio tracks selected; the output will be silent")

    out_w = width or project.output.width
    out_h = height or project.output.height
    if out_w % 2 or out_h % 2:
        raise RenderPlanError("output width and height must be even")
    return RenderPlan(
        fps=fps,
        width=out_w,
        height=out_h,
        total_frames=cutlist.duration_frames,
        pieces=pieces,
        chunks=chunk_pieces(pieces, fps, chunk_seconds, max_pieces_per_chunk),
        audio=audio,
        warnings=warnings,
    )
