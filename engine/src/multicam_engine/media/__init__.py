"""media — probing files and decoding audio (ffmpeg/ffprobe wrappers)."""

from multicam_engine.media.audio import (
    SYNC_SAMPLE_RATE,
    AudioExtractionError,
    NoAudioError,
    extract_audio,
    load_audio,
)
from multicam_engine.media.ffmpeg import FFmpegError, FFmpegNotFoundError, find_tool
from multicam_engine.media.probe import ProbeError, ProbeResult, probe

__all__ = [
    "SYNC_SAMPLE_RATE",
    "AudioExtractionError",
    "FFmpegError",
    "FFmpegNotFoundError",
    "NoAudioError",
    "ProbeError",
    "ProbeResult",
    "extract_audio",
    "find_tool",
    "load_audio",
    "probe",
]
