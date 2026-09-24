"""Choose a video encoder and its arguments; output presets.

Licensing (plan §5.3): the shipped app uses an LGPL ffmpeg, so encoding goes to
OS/GPU encoders (VideoToolbox, Media Foundation, NVENC, Quick Sync, AMF), with
OpenH264 (BSD) as the CPU fallback. ``libx264`` is only used when present, which
is the case in GPL development builds (Homebrew); ``mpeg4`` is a last resort so
tests run anywhere.

An encoder listed by ``ffmpeg -encoders`` may still fail (e.g. NVENC without an
NVIDIA GPU), so each candidate is tried on a tiny test clip before being chosen.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from typing import Literal

from multicam_engine.media.ffmpeg import FFmpegError, run_tool

Codec = Literal["h264", "hevc"]

# Most preferred first, per codec. Platform-specific ones are simply absent elsewhere.
_CANDIDATES: dict[Codec, tuple[str, ...]] = {
    "h264": (
        "h264_videotoolbox",
        "h264_nvenc",
        "h264_qsv",
        "h264_amf",
        "h264_mf",
        "libopenh264",
        "libx264",
        "mpeg4",
    ),
    "hevc": ("hevc_videotoolbox", "hevc_nvenc", "hevc_qsv", "hevc_amf", "hevc_mf", "libx265"),
}


@dataclass(frozen=True)
class OutputPreset:
    name: str
    description: str
    width: int | None  # None = project output size
    height: int | None
    codec: Codec
    video_kbps: int
    audio_kbps: int
    fast: bool = False  # favour speed over quality (drafts)


_PRESET_LIST = (
    OutputPreset("youtube-1080p", "YouTube 1080p (H.264, 12 Mbps)",
                 1920, 1080, "h264", 12_000, 320),
    OutputPreset("youtube-4k", "YouTube 4K (H.264, 45 Mbps)", 3840, 2160, "h264", 45_000, 320),
    OutputPreset("master", "High-quality master at project size (HEVC, 80 Mbps)",
                 None, None, "hevc", 80_000, 320),
    OutputPreset("draft", "Fast preview (H.264, 4 Mbps, 720p)",
                 1280, 720, "h264", 4_000, 160, fast=True),
)  # fmt: skip
PRESETS: dict[str, OutputPreset] = {p.name: p for p in _PRESET_LIST}


def encoder_args(encoder: str, kbps: int, fps: float, *, fast: bool = False) -> list[str]:
    """Rate control + GOP arguments for ``encoder`` at roughly ``kbps``."""
    rate = ["-b:v", f"{kbps}k", "-maxrate", f"{int(kbps * 1.5)}k", "-bufsize", f"{kbps * 2}k"]
    gop = ["-g", str(max(1, round(fps * 2)))]
    if encoder.endswith("_videotoolbox"):
        return [*rate, *gop, "-allow_sw", "1", "-realtime", "0"]
    if encoder.endswith("_nvenc"):
        return ["-preset", "p2" if fast else "p5", "-rc", "vbr", *rate, *gop]
    if encoder.endswith("_qsv"):
        return ["-preset", "veryfast" if fast else "slower", *rate, *gop]
    if encoder.endswith("_amf"):
        return ["-quality", "quality", "-rc", "vbr_peak", *rate, *gop]
    if encoder.endswith("_mf"):
        return ["-b:v", f"{kbps}k", *gop, "-hw_encoding", "1"]
    if encoder == "libopenh264":
        return ["-b:v", f"{kbps}k", *gop]
    if encoder in ("libx264", "libx265"):
        speed, crf = ("veryfast", "20") if fast else ("medium", "18")
        return ["-preset", speed, "-crf", crf, "-maxrate", f"{int(kbps * 1.5)}k",
                "-bufsize", f"{kbps * 2}k", *gop]  # fmt: skip
    if encoder == "mpeg4":
        return ["-q:v", "3", *gop]
    return [*rate, *gop]


def listed_encoders() -> set[str]:
    out = run_tool("ffmpeg", ["-encoders"]).decode(errors="replace")
    names = set()
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 2 and len(parts[0]) == 6 and parts[0][0] == "V":
            names.add(parts[1])
    return names


def encoder_works(encoder: str) -> bool:
    """Encode one second of a tiny test pattern; False if the encoder fails."""
    try:
        run_tool(
            "ffmpeg",
            ["-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=size=256x144:rate=30:duration=1",
             "-c:v", encoder, *encoder_args(encoder, 1000, 30), "-pix_fmt", "yuv420p",
             "-f", "null", "-"],
            timeout=60,
        )  # fmt: skip
    except FFmpegError:
        return False
    return True


@cache
def available_encoders(codec: Codec) -> tuple[str, ...]:
    """Working encoders for ``codec``, most preferred first (cached per process)."""
    listed = listed_encoders()
    return tuple(e for e in _CANDIDATES[codec] if e in listed and encoder_works(e))


def codec_of(encoder: str) -> Codec:
    return "hevc" if ("hevc" in encoder or "265" in encoder) else "h264"


def choose_encoder(codec: Codec, requested: str | None = None) -> tuple[str, Codec]:
    """Best working encoder. HEVC falls back to H.264 if no HEVC encoder works."""
    if requested and requested != "auto":
        if not encoder_works(requested):
            raise FFmpegError(f"encoder {requested!r} is not available or does not work here")
        return requested, codec_of(requested)
    for c in (codec, "h264") if codec == "hevc" else (codec,):
        found = available_encoders(c)
        if found:
            return found[0], c
    raise FFmpegError("no working video encoder found in this ffmpeg build")
