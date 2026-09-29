"""Auto framing for a whole edit: face tracks -> punch-ins + crops (16:9 and 9:16).

Face positions are measured in each clip's media time and mapped onto the
timeline with the clip's sync (offset, drift), exactly like the render does.
Anything the user framed by hand (``manual``) is kept.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from itertools import pairwise
from pathlib import Path
from uuid import UUID

import numpy as np
import numpy.typing as npt

from multicam_engine.analysis.speakers import SILENCE, SpeakerActivity
from multicam_engine.media.probe import ProbeResult
from multicam_engine.models.cutlist import CutList, Reframe, ReframeKey, Segment
from multicam_engine.models.project import Clip, ClipRole, Project
from multicam_engine.reframe.detect import Face, FaceDetector
from multicam_engine.reframe.framing import (
    PathPoint,
    clamp_center,
    crop_size,
    frame_subject,
    simplify,
    smooth,
)
from multicam_engine.reframe.punch import PUNCH_PRESETS, split_points
from multicam_engine.reframe.sample import sample_frames
from multicam_engine.reframe.track import Detections, SubjectPoint, group_track, primary_track
from multicam_engine.render.plan import clip_timing

VERTICAL_SIZE = (1080, 1920)


class ReframeCancelledError(Exception):
    pass


# ------------------------------------------------------------------ detection
def detect_faces(
    path: str | Path,
    detector: FaceDetector,
    *,
    every_s: float = 0.5,
    info: ProbeResult | None = None,
    on_progress: Callable[[float], None] | None = None,
    cancel: threading.Event | None = None,
) -> list[Detections]:
    """Faces in frames sampled about every ``every_s`` s (media time)."""
    duration = float(info.duration) if info else 0.0
    out: list[Detections] = []
    for sample in sample_frames(path, every_s=every_s, info=info):
        if cancel is not None and cancel.is_set():
            raise ReframeCancelledError
        out.append(Detections(sample.t, tuple(detector.detect(sample.image))))
        if on_progress and duration:
            on_progress(min(1.0, sample.t / duration))
    return out


def detections_to_json(detections: list[Detections]) -> str:
    return json.dumps(
        [
            {
                "t": round(d.t, 4),
                "faces": [[round(v, 5) for v in (f.x, f.y, f.w, f.h, f.score)] for f in d.faces],
            }
            for d in detections
        ]
    )


def detections_from_json(text: str) -> list[Detections]:
    return [
        Detections(float(d["t"]), tuple(Face(*map(float, f)) for f in d["faces"]))
        for d in json.loads(text)
    ]


# ------------------------------------------------------------------ geometry
@dataclass(frozen=True)
class ClipGeometry:
    width: int
    height: int
    speed: float  # media time = timeline time * speed + media_offset
    media_offset: float

    def to_timeline(self, media_t: float) -> float:
        return (media_t - self.media_offset) / self.speed


def clip_geometry(clip: Clip, info: ProbeResult) -> ClipGeometry:
    timing = clip_timing(clip, info)
    zero = min([info.video_start] + ([info.audio_start] if info.audio_start is not None else []))
    return ClipGeometry(
        width=info.media.width,
        height=info.media.height,
        speed=float(timing.speed),
        media_offset=float(timing.audio_start + timing.offset - zero),
    )


@dataclass
class FaceTracks:
    """Subject tracks of one clip on the timeline (seconds)."""

    primary: list[SubjectPoint]
    group: list[SubjectPoint]
    seen: int  # samples with at least one face

    @classmethod
    def build(cls, detections: list[Detections], geom: ClipGeometry) -> FaceTracks:
        on_timeline = [Detections(geom.to_timeline(d.t), d.faces) for d in detections]
        return cls(
            primary=primary_track(on_timeline),
            group=group_track(on_timeline),
            seen=sum(1 for d in detections if d.faces),
        )


# ------------------------------------------------------------------ planning
@dataclass(frozen=True)
class ReframeSettings:
    punch: str = "balanced"  # off | calm | balanced | dynamic
    horizontal: bool = True
    vertical: bool = True
    dead_zone: float = 0.04  # fraction of the frame the subject may move before we follow
    tau_s: float = 1.2  # how softly the crop follows
    key_tolerance: float = 0.01  # keyframes keep the path within 1 % of the frame
    headroom: float = 0.1


@dataclass
class ReframeReport:
    punch_ins: int = 0
    framed: int = 0  # crops that follow a face
    centred: int = 0  # crops without a face (centred fallback)
    warnings: list[str] = field(default_factory=list)


def plan_crop(
    points: list[SubjectPoint],
    start: int,
    end: int,
    fps: float,
    geom: ClipGeometry,
    out_size: tuple[int, int],
    scale: float,
    settings: ReframeSettings,
) -> tuple[Reframe, bool]:
    """Crop for timeline frames [start, end). Returns (reframe, followed_a_face)."""
    cw, ch = crop_size(geom.width, geom.height, out_size[0], out_size[1], scale)
    t0, t1 = start / fps, end / fps
    near = [p for p in points if t0 - 2.0 <= p.t <= t1 + 1.0]
    if not any(p.seen for p in near if t0 <= p.t <= t1) and not any(p.seen for p in near):
        cx, cy = clamp_center(0.5, 0.5, cw, ch)
        return Reframe(cx=cx, cy=cy, scale=scale), False
    raw = [
        PathPoint(p.t, *frame_subject(p.cx, p.cy, p.size, cw, ch, headroom=settings.headroom))
        for p in near
    ]
    smoothed = smooth(raw, dead_zone=settings.dead_zone, tau_s=settings.tau_s)
    inside = [p for p in smoothed if t0 <= p.t < t1]
    before = [p for p in smoothed if p.t < t0]
    first = inside[0] if inside else (before[-1] if before else smoothed[0])
    if not inside:
        return Reframe(cx=first.cx, cy=first.cy, scale=scale), True
    keys = simplify([PathPoint(t0, first.cx, first.cy), *inside], settings.key_tolerance)
    if max(max(abs(k.cx - first.cx), abs(k.cy - first.cy)) for k in keys) <= settings.key_tolerance:
        return Reframe(cx=first.cx, cy=first.cy, scale=scale), True
    frames: list[ReframeKey] = []
    for k in keys:
        frame = min(max(start, round(k.t * fps)), end - 1)
        if frames and frame <= frames[-1].frame:
            continue
        cx, cy = clamp_center(k.cx, k.cy, cw, ch)
        frames.append(ReframeKey(frame=frame, cx=cx, cy=cy))
    return Reframe(cx=frames[0].cx, cy=frames[0].cy, scale=scale, path=frames), True


def _speaking(
    activity: SpeakerActivity | None, speaker_index: int | None, n_frames: int, fps: float
) -> npt.NDArray[np.bool_] | None:
    if activity is None or speaker_index is None:
        return None
    idx = np.minimum(
        (np.arange(n_frames) / fps * activity.frame_rate).astype(np.int64), activity.n_frames - 1
    )
    labels = activity.labels[idx]
    speaking: npt.NDArray[np.bool_] = (labels == speaker_index) | (
        (labels < 0) & (labels != SILENCE)
    )
    return speaking


def _runs(segments: list[Segment]) -> list[list[Segment]]:
    """Consecutive segments of the same camera = one shot (so re-running is stable)."""
    runs: list[list[Segment]] = []
    for seg in segments:
        manual = bool(seg.reframe and seg.reframe.manual)
        if (
            runs
            and runs[-1][-1].clip_id == seg.clip_id
            and not manual
            and not (runs[-1][-1].reframe and runs[-1][-1].reframe.manual)
        ):
            runs[-1].append(seg)
        else:
            runs.append([seg])
    return runs


def auto_reframe(
    project: Project,
    cutlist: CutList,
    tracks: dict[UUID, FaceTracks],
    geoms: dict[UUID, ClipGeometry],
    settings: ReframeSettings,
    *,
    activity: SpeakerActivity | None = None,
    speaker_ids: list[UUID] | None = None,
) -> tuple[CutList, ReframeReport]:
    fps = float(cutlist.fps.to_fraction())
    out_size = (project.output.width, project.output.height)
    params = PUNCH_PRESETS.get(settings.punch)
    report = ReframeReport()
    n_frames = cutlist.duration_frames
    speaking_cache: dict[UUID, npt.NDArray[np.bool_] | None] = {}
    segments: list[Segment] = []

    for run in _runs(cutlist.segments):
        first, last = run[0], run[-1]
        clip = project.clip(first.clip_id)
        geom = geoms.get(clip.id)
        manual_h = first.reframe if first.reframe and first.reframe.manual else None
        manual_v = (
            first.reframe_vertical
            if first.reframe_vertical and first.reframe_vertical.manual
            else None
        )
        if geom is None or clip.id not in tracks:
            segments.extend(run)
            continue
        track = tracks[clip.id]
        is_speaker = clip.role is ClipRole.SPEAKER
        points = track.primary if is_speaker else track.group

        bounds = [first.start_frame, last.end_frame]
        if params and is_speaker and manual_h is None and len(run) >= 1:
            if clip.id not in speaking_cache:
                index = (
                    speaker_ids.index(clip.id) if speaker_ids and clip.id in speaker_ids else None
                )
                speaking_cache[clip.id] = _speaking(activity, index, n_frames, fps)
            cuts = split_points(bounds[0], bounds[1], speaking_cache[clip.id], fps, params)
            bounds = [bounds[0], *cuts, bounds[1]]
            report.punch_ins += len(cuts)
        elif len(run) > 1:
            bounds = [first.start_frame, *[s.start_frame for s in run[1:]], last.end_frame]

        for k, (a, b) in enumerate(pairwise(bounds)):
            scale = params.tight_scale if (params and is_speaker and k % 2 == 1) else 1.0
            template = next((s for s in run if s.start_frame <= a < s.end_frame), first)
            seg = template.model_copy(update={"start_frame": a, "end_frame": b})
            if settings.horizontal and manual_h is None:
                same_shape = abs(geom.width / geom.height - out_size[0] / out_size[1]) < 0.01
                if scale > 1.0 or not same_shape:
                    seg.reframe, followed = plan_crop(
                        points, a, b, fps, geom, out_size, scale, settings
                    )
                    report.framed += followed
                    report.centred += not followed
                else:
                    seg.reframe = None  # the whole frame already fits
            elif manual_h is not None:
                seg.reframe = manual_h
            if settings.vertical and manual_v is None:
                seg.reframe_vertical, followed = plan_crop(
                    points, a, b, fps, geom, VERTICAL_SIZE, 1.0, settings
                )
                report.framed += followed
                report.centred += not followed
            elif manual_v is not None:
                seg.reframe_vertical = manual_v
            segments.append(seg)

    for cid, track in tracks.items():
        if track.seen == 0 and any(s.clip_id == cid for s in cutlist.segments):
            name = Path(project.clip(cid).path).name
            report.warnings.append(f"{name}: no faces found; centred framing used")
    new = cutlist.model_copy(update={"segments": segments})
    return CutList.model_validate(new.model_dump()), report
