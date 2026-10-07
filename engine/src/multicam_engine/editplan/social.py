"""Social clips: an in/out range of the edit as one sequence per aspect ratio
(AutoPod's Social Clip Creator, with speaker-aware framing).

For every aspect the clip gets:

* the sequence size (16:9 1920x1080, 4:5 1080x1350, 9:16 1080x1920, 1:1 1080x1080);
* Motion keys per shot from the face-tracked framing: 9:16 uses the vertical
  framing, 16:9 the horizontal one, 4:5 and 1:1 follow the vertical framing's
  centre path at the largest crop of their shape; without framing the crop is
  centred (filled, never letterboxed);
* optionally a watermark (picture above the edit, in a corner, with opacity) and
  an end page (still or video appended after the clip, fitted inside the frame);
* optionally the approved removals (jump cuts) rippled out.

The result is a list of ordinary EditPlans (method ``cuts``), so the XML writers
and the host adapters need nothing special.
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Final, Literal

from multicam_engine.editplan.model import (
    AudioTrack,
    EditPlan,
    PlanMedia,
    PlanMethod,
    PlanOverlay,
    PlanPiece,
    PlanTransformKey,
    VideoEvent,
)
from multicam_engine.editplan.ripple import apply_removals, slice_plan
from multicam_engine.editplan.transform import crop_transform, fit_transform
from multicam_engine.media.image import IMAGE_SUFFIXES, image_size
from multicam_engine.media.probe import probe
from multicam_engine.models.cutlist import Reframe
from multicam_engine.models.project import ShotType
from multicam_engine.models.time import Rational

Aspect = Literal["16:9", "4:5", "9:16", "1:1"]
ASPECT_SIZES: Final[dict[str, tuple[int, int]]] = {
    "16:9": (1920, 1080),
    "4:5": (1080, 1350),
    "9:16": (1080, 1920),
    "1:1": (1080, 1080),
}
Corner = Literal["top_left", "top_right", "bottom_left", "bottom_right", "center"]
_NS = uuid.UUID("5f0b8f7e-3c11-4c5e-9d55-0d9f7c1e1a01")


@dataclass(frozen=True)
class Picture:
    """A still or video file (watermark / end page) and what probing it found."""

    path: Path
    width: int
    height: int
    #: Seconds of a video file; None for a still image.
    duration_s: float | None = None
    fps: Fraction | None = None
    has_audio: bool = False
    sample_rate: int = 48000
    audio_channels: int = 2


@dataclass(frozen=True)
class Watermark:
    picture: Picture
    corner: Corner = "bottom_right"
    #: Width of the watermark as a fraction of the sequence width.
    size: float = 0.18
    opacity: float = 0.9
    #: Distance from the edges as a fraction of the sequence width.
    margin: float = 0.04


@dataclass(frozen=True)
class EndPage:
    picture: Picture
    #: How long a still stays up (a video plays to its end, capped at this).
    seconds: float = 3.0


@dataclass(frozen=True)
class SocialOptions:
    watermark: Watermark | None = None
    end_page: EndPage | None = None
    #: Take the approved removals (jump cuts) out of the clip.
    jump_cuts: bool = False


def load_picture(path: str | Path) -> Picture:
    """Size (and for a video: duration, rate, audio) of a watermark / end page file."""
    p = Path(path)
    if p.suffix.lower() in IMAGE_SUFFIXES:
        w, h = image_size(p)
        return Picture(path=p, width=w, height=h)
    info = probe(p)
    media = info.media
    if not media.has_video:
        raise ValueError(f"{p.name}: has no picture")
    fps = media.fps.to_fraction()
    return Picture(
        path=p,
        width=media.width,
        height=media.height,
        duration_s=float(Fraction(media.duration_frames) / fps),
        fps=fps,
        has_audio=media.audio_channels > 0,
        sample_rate=media.audio_sample_rate or 48000,
        audio_channels=media.audio_channels or 2,
    )


def _clip_id(path: Path, role: str) -> uuid.UUID:
    return uuid.uuid5(_NS, f"{role}:{path}")


def _picture_media(pic: Picture, role: str, seq_fps: Rational, frames: int) -> PlanMedia:
    fps = Rational(num=pic.fps.numerator, den=pic.fps.denominator) if pic.fps else seq_fps
    duration = (
        max(1, math.floor(Fraction(pic.duration_s).limit_denominator(1000) * fps.to_fraction()))
        if pic.duration_s
        else max(frames, 1)
    )
    return PlanMedia(
        clip_id=_clip_id(pic.path, role),
        path=str(pic.path),
        name=pic.path.name,
        label=role.replace("_", " ").title(),
        host_ref=None,
        fps=fps,
        duration_frames=duration,
        width=pic.width,
        height=pic.height,
        has_audio=pic.has_audio,
        audio_channels=pic.audio_channels if pic.has_audio else 0,
        sample_rate=pic.sample_rate if pic.has_audio else 0,
        start_timecode_frames=0,
        has_timecode=False,
        shot=ShotType.BROLL,
        angle=None,
        video_track=None,
        audio_track=None,
        record_start_frame=0,
    )


def _start(clip_id: uuid.UUID, start: int, end: int) -> dict[str, object]:
    return {
        "start": start,
        "end": end,
        "clip_id": clip_id,
        "source_in_frame": 0,
        "source_in_sample": 0,
        "source_in_ticks": 0,
    }


def framing_for(ev: VideoEvent, aspect: str) -> Reframe | None:
    """Which framing a shot uses at an aspect (None: centred)."""
    if aspect == "16:9":
        return ev.reframe
    vertical = ev.reframe_vertical
    if aspect == "9:16":
        return vertical
    base = vertical or ev.reframe
    if base is None:
        return None
    # 4:5 / 1:1: follow the subject (the vertical framing's path), widest crop
    return Reframe(cx=base.cx, cy=base.cy, scale=1.0, path=base.path)


def _corner_xy(
    corner: Corner, size: tuple[float, float], out: tuple[int, int], margin: float
) -> tuple[float, float]:
    (w, h), (ow, oh) = size, out
    m = margin * ow
    x = {"left": m + w / 2, "right": ow - m - w / 2, "center": ow / 2}
    y = {"top": m + h / 2, "bottom": oh - m - h / 2, "center": oh / 2}
    if corner == "center":
        return x["center"], y["center"]
    v, hz = corner.split("_")
    return x[hz], y[v]


def watermark_overlay(
    wm: Watermark, clip_id: uuid.UUID, out: tuple[int, int], frames: int
) -> PlanOverlay:
    target_w = wm.size * out[0]
    k = target_w / wm.picture.width
    x, y = _corner_xy(wm.corner, (target_w, wm.picture.height * k), out, wm.margin)
    return PlanOverlay.model_validate(
        {
            **_start(clip_id, 0, frames),
            "track": 1,
            "opacity": wm.opacity,
            "transform": [{"frame": 0, "scale": round(100 * k, 4), "x": x, "y": y}],
        }
    )


def _end_page(
    plan: EditPlan, page: EndPage, media: PlanMedia, out: tuple[int, int]
) -> tuple[VideoEvent, AudioTrack | None, int]:
    fps = plan.sequence.fps.to_fraction()
    seconds = Fraction(page.seconds).limit_denominator(1000)
    if page.picture.duration_s:
        seconds = min(seconds, Fraction(page.picture.duration_s).limit_denominator(1000))
    frames = max(1, math.floor(seconds * fps))
    start = plan.sequence.duration_frames
    ev = VideoEvent.model_validate(
        {
            **_start(media.clip_id, start, start + frames),
            "shot": ShotType.BROLL,
            "transform": [
                k.model_dump() for k in fit_transform((media.width, media.height), out, start)
            ],
        }
    )
    audio = None
    if media.has_audio:
        index = max((t.index for t in plan.audio_tracks), default=0) + 1
        audio = AudioTrack(
            index=index,
            clip_id=media.clip_id,
            pieces=[PlanPiece.model_validate(_start(media.clip_id, start, start + frames))],
        )
    return ev, audio, frames


def _for_aspect(base: EditPlan, aspect: str, options: SocialOptions) -> EditPlan:
    out = ASPECT_SIZES[aspect]
    media = base.media_by_id()
    events: list[VideoEvent] = []
    for ev in base.video_events:
        m = media[ev.clip_id]
        keys: list[PlanTransformKey] | None = crop_transform(
            framing_for(ev, aspect), (m.width, m.height), out, ev.start, ev.end, always=True
        )
        events.append(ev.model_copy(update={"transform": keys}))

    plan_media = list(base.media)
    audio_tracks = list(base.audio_tracks)
    overlays: list[PlanOverlay] = []
    duration = base.sequence.duration_frames
    if options.end_page is not None:
        page_media = _picture_media(options.end_page.picture, "end_page", base.sequence.fps, 0)
        ev, audio, frames = _end_page(base, options.end_page, page_media, out)
        page_media = page_media.model_copy(
            update={"duration_frames": max(page_media.duration_frames, frames)}
        )
        plan_media.append(page_media)
        events.append(ev)
        if audio is not None:
            audio_tracks.append(audio)
        duration += frames
    if options.watermark is not None:
        clip_frames = base.sequence.duration_frames  # not over the end page
        wm_media = _picture_media(
            options.watermark.picture, "watermark", base.sequence.fps, clip_frames
        )
        plan_media.append(wm_media)
        # a video watermark (animated logo) plays once; a still lasts the whole clip
        frames = clip_frames
        if options.watermark.picture.duration_s:
            seconds = Fraction(options.watermark.picture.duration_s).limit_denominator(1000)
            frames = max(1, min(clip_frames, math.floor(seconds * base.sequence.fps.to_fraction())))
        overlays.append(watermark_overlay(options.watermark, wm_media.clip_id, out, frames))

    label = aspect.replace(":", "x")
    sequence = base.sequence.model_copy(
        update={
            "name": f"{base.sequence.name} - {label}",
            "width": out[0],
            "height": out[1],
            "duration_frames": duration,
        }
    )
    return EditPlan.model_validate(
        {
            **{name: getattr(base, name) for name in type(base).model_fields},
            "method": PlanMethod.CUTS,
            "sequence": sequence,
            "media": plan_media,
            "video_events": events,
            "video_tracks": [],
            "audio_tracks": audio_tracks,
            "overlays": overlays,
            "aspect": aspect,
        }
    )


def build_social_plans(
    plan: EditPlan,
    in_frame: int,
    out_frame: int,
    aspects: list[str],
    options: SocialOptions | None = None,
    *,
    name: str | None = None,
) -> list[EditPlan]:
    """One plan per aspect for frames [in_frame, out_frame) of ``plan``."""
    options = options or SocialOptions()
    unknown = [a for a in aspects if a not in ASPECT_SIZES]
    if unknown or not aspects:
        raise ValueError(f"aspects must be some of {sorted(ASPECT_SIZES)}, got {aspects}")
    clip = slice_plan(plan, in_frame, out_frame, name=name or f"{plan.sequence.name} - Social")
    if options.jump_cuts and clip.removals:
        clip = apply_removals(clip, suffix="")
    return [_for_aspect(clip, a, options) for a in dict.fromkeys(aspects)]
