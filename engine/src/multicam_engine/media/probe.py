"""Read facts about a media file with ffprobe.

``probe(path)`` runs ffprobe; ``parse_probe(data)`` turns ffprobe's JSON into a
``ProbeResult`` and is pure (unit-tested without ffmpeg).

Frame rate
    ffprobe reports two rates: ``r_frame_rate`` (a rate that can represent every
    timestamp) and ``avg_frame_rate`` (frames / duration). The *nominal* rate is
    ``r_frame_rate`` when it is a standard rate, otherwise ``avg_frame_rate``
    snapped to the nearest standard rate (within 1 %).

Variable frame rate (phones)
    Decided from real packet timestamps of the first seconds of video: if the
    spacing between frames varies, the clip is VFR. Only when timestamps are not
    available do we fall back to comparing the two ffprobe rates.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from fractions import Fraction
from itertools import pairwise
from pathlib import Path
from typing import Any

from multicam_engine.media.ffmpeg import FFmpegError, run_tool
from multicam_engine.models.project import MediaInfo
from multicam_engine.models.time import Rational, Rounding, seconds_to_frames

STANDARD_RATES: tuple[Fraction, ...] = tuple(
    Fraction(n, d)
    for n, d in (
        (24000, 1001),
        (24, 1),
        (25, 1),
        (30000, 1001),
        (30, 1),
        (48, 1),
        (50, 1),
        (60000, 1001),
        (60, 1),
        (100, 1),
        (120000, 1001),
        (120, 1),
    )
)
_SNAP_TOLERANCE = Fraction(1, 100)  # 1 %
_VFR_PACKET_SECONDS = 20
_MIN_PACKETS_FOR_VFR_CHECK = 10


class ProbeError(RuntimeError):
    """The file could not be read or has no usable video stream."""


@dataclass(frozen=True)
class ProbeResult:
    path: Path
    media: MediaInfo
    video_stream_index: int
    audio_stream_index: int | None
    #: Exact duration of the video stream, in seconds.
    duration: Fraction
    #: Container start times (seconds). Needed when mapping audio to video (Phase 3).
    video_start: Fraction
    audio_start: Fraction | None
    rotation: int  # degrees, as displayed (0, 90, 180, 270)


# ----------------------------------------------------------------- helpers
def _rate(text: object) -> Fraction | None:
    if not isinstance(text, str):
        return None
    try:
        return Rational.parse(text).to_fraction()
    except ValueError:
        return None


def _decimal(text: object) -> Fraction | None:
    if text is None or text == "N/A":
        return None
    try:
        return Fraction(str(text))
    except (ValueError, ZeroDivisionError):
        return None


def _snap(rate: Fraction) -> Fraction | None:
    best = min(STANDARD_RATES, key=lambda s: abs(s - rate))
    return best if abs(best - rate) / best <= _SNAP_TOLERANCE else None


def nominal_fps(r_frame_rate: Fraction | None, avg_frame_rate: Fraction | None) -> Fraction:
    if r_frame_rate is not None and r_frame_rate in STANDARD_RATES:
        return r_frame_rate
    for candidate in (avg_frame_rate, r_frame_rate):
        if candidate is not None and 0 < candidate <= 1000:
            return _snap(candidate) or candidate.limit_denominator(1001)
    raise ProbeError("could not determine the frame rate")


def timestamps_vary(pts: list[int], tolerance: float = 0.1) -> bool:
    """True if frame spacing is irregular (VFR).

    ``pts`` are presentation timestamps in stream time-base ticks, in any order
    (B-frames reorder them). A spacing counts as irregular when it differs from
    the median spacing by more than ``tolerance`` of it (and by more than one
    tick, to ignore time-base rounding). More than 2 % irregular spacings -> VFR.
    """
    ordered = sorted(set(pts))
    if len(ordered) < 3:
        return False
    deltas = [b - a for a, b in pairwise(ordered)]
    median = sorted(deltas)[len(deltas) // 2]
    if median <= 0:
        return False
    limit = max(1.0, tolerance * median)
    irregular = sum(abs(d - median) > limit for d in deltas)
    return irregular / len(deltas) > 0.02


def _rotation(stream: dict[str, Any]) -> int:
    raw: object = None
    for side in stream.get("side_data_list") or []:
        if isinstance(side, dict) and "rotation" in side:
            raw = side["rotation"]
            break
    if raw is None:
        raw = (stream.get("tags") or {}).get("rotate")
    try:
        degrees = int(float(str(raw))) if raw is not None else 0
    except ValueError:
        degrees = 0
    return degrees % 360


def _is_attached_picture(stream: dict[str, Any]) -> bool:
    return bool((stream.get("disposition") or {}).get("attached_pic"))


# ------------------------------------------------------------------ parsing
def parse_probe(
    data: dict[str, Any], path: Path, video_pts: list[int] | None = None
) -> ProbeResult:
    """Build a ``ProbeResult`` from ffprobe ``-show_streams -show_format`` JSON."""
    streams: list[dict[str, Any]] = data.get("streams") or []
    video = next(
        (s for s in streams if s.get("codec_type") == "video" and not _is_attached_picture(s)),
        None,
    )
    if video is None:
        raise ProbeError(f"{path.name}: no video stream")
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)

    r_rate, avg_rate = _rate(video.get("r_frame_rate")), _rate(video.get("avg_frame_rate"))
    fps = nominal_fps(r_rate, avg_rate)

    if video_pts is not None and len(video_pts) >= _MIN_PACKETS_FOR_VFR_CHECK:
        is_vfr = timestamps_vary(video_pts)
    else:
        is_vfr = (
            r_rate is not None
            and avg_rate is not None
            and abs(r_rate - avg_rate) / r_rate > Fraction(1, 1000)
        )

    fmt: dict[str, Any] = data.get("format") or {}
    duration = _decimal(video.get("duration")) or _decimal(fmt.get("duration"))
    if duration is None or duration <= 0:
        raise ProbeError(f"{path.name}: unknown duration")

    width, height = int(video.get("width") or 0), int(video.get("height") or 0)
    if width <= 0 or height <= 0:
        raise ProbeError(f"{path.name}: unknown video dimensions")
    rotation = _rotation(video)
    if rotation in (90, 270):
        width, height = height, width

    sample_rate = int(audio["sample_rate"]) if audio and audio.get("sample_rate") else None
    media = MediaInfo(
        fps=Rational.from_fraction(fps),
        is_vfr=is_vfr,
        duration_frames=seconds_to_frames(duration, Rational.from_fraction(fps), Rounding.NEAREST),
        width=width,
        height=height,
        video_codec=str(video.get("codec_name") or "unknown"),
        audio_codec=str(audio.get("codec_name")) if audio else None,
        audio_sample_rate=sample_rate,
        audio_channels=int(audio.get("channels") or 0) if audio else 0,
    )
    return ProbeResult(
        path=path,
        media=media,
        video_stream_index=int(video["index"]),
        audio_stream_index=int(audio["index"]) if audio else None,
        duration=duration,
        video_start=_decimal(video.get("start_time")) or Fraction(0),
        audio_start=(_decimal(audio.get("start_time")) or Fraction(0)) if audio else None,
        rotation=rotation,
    )


# ------------------------------------------------------------------ running
def _read_video_pts(path: Path, stream_index: int) -> list[int] | None:
    """Presentation timestamps of the first seconds of video (no decoding)."""
    try:
        out = run_tool(
            "ffprobe",
            [
                "-v", "error",
                "-select_streams", str(stream_index),
                "-read_intervals", f"%+{_VFR_PACKET_SECONDS}",
                "-show_entries", "packet=pts",
                "-of", "csv=p=0",
                str(path),
            ],
        )  # fmt: skip
    except FFmpegError:
        return None
    pts: list[int] = []
    for line in out.decode(errors="replace").splitlines():
        value = line.strip().rstrip(",")
        if value and value != "N/A":
            try:
                pts.append(int(value))
            except ValueError:
                continue
    return pts


def probe(path: str | Path) -> ProbeResult:
    path = Path(path)
    if not path.is_file():
        raise ProbeError(f"file not found: {path}")
    try:
        out = run_tool(
            "ffprobe",
            ["-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        )
    except FFmpegError as exc:
        raise ProbeError(f"{path.name}: ffprobe could not read the file") from exc
    data: dict[str, Any] = json.loads(out)
    first = parse_probe(data, path)
    pts = _read_video_pts(path, first.video_stream_index)
    return parse_probe(data, path, pts) if pts is not None else first
