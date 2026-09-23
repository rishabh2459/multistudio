"""Decode a clip's audio to a mono float32 array at a fixed sample rate.

Sync runs at 8 kHz: speech content below 4 kHz is plenty for correlation, and with
sub-sample peak interpolation the precision is far below 1 ms, while a one-hour
clip needs only ~115 MB of memory.

Decoded audio is cached on disk (``.npy``), keyed by the file's path, size and
modification time, so re-running sync after an edit does not decode again.
"""

from __future__ import annotations

import hashlib
import os
import sys
import tempfile
from pathlib import Path

import numpy as np
import numpy.typing as npt

from multicam_engine.media.ffmpeg import FFmpegError, run_tool

SYNC_SAMPLE_RATE = 8_000
_CACHE_VERSION = 1

AudioArray = npt.NDArray[np.float32]


class NoAudioError(RuntimeError):
    """The file has no audio stream."""


class AudioExtractionError(RuntimeError):
    """ffmpeg could not decode the audio."""


def default_cache_dir() -> Path:
    """Per-user cache folder. Override with ``MULTICAM_CACHE_DIR``."""
    override = os.environ.get("MULTICAM_CACHE_DIR")
    if override:
        return Path(override)
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Caches"
    elif sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return base / "multicam-studio" / "audio"


def extract_audio(path: str | Path, sample_rate: int = SYNC_SAMPLE_RATE) -> AudioArray:
    """Decode the first audio stream, downmixed to mono, resampled to ``sample_rate``."""
    path = Path(path)
    if sample_rate <= 0:
        raise ValueError("sample_rate must be positive")
    if not path.is_file():
        raise FileNotFoundError(path)
    try:
        raw = run_tool(
            "ffmpeg",
            [
                "-loglevel", "error",
                "-i", str(path),
                "-map", "0:a:0?",  # '?' -> no error if missing; we detect empty output
                "-vn", "-sn", "-dn",
                "-ac", "1",
                "-ar", str(sample_rate),
                "-f", "f32le", "-c:a", "pcm_f32le",
                "pipe:1",
            ],
        )  # fmt: skip
    except FFmpegError as exc:
        if "does not contain any stream" in exc.stderr:
            raise NoAudioError(f"{path.name}: no audio stream") from exc
        raise AudioExtractionError(f"{path.name}: could not decode audio: {exc}") from exc
    if not raw:
        raise NoAudioError(f"{path.name}: no audio stream")
    samples: AudioArray = np.frombuffer(raw, dtype="<f4").astype(np.float32, copy=True)
    return samples


def _cache_key(path: Path, sample_rate: int) -> str:
    stat = path.stat()
    ident = f"{path.resolve()}|{stat.st_size}|{stat.st_mtime_ns}|{sample_rate}|v{_CACHE_VERSION}"
    return hashlib.sha256(ident.encode()).hexdigest()[:32]


def load_audio(
    path: str | Path,
    sample_rate: int = SYNC_SAMPLE_RATE,
    cache_dir: Path | None = None,
) -> AudioArray:
    """``extract_audio`` with an optional on-disk cache (``cache_dir=None`` disables it)."""
    path = Path(path)
    if cache_dir is None:
        return extract_audio(path, sample_rate)
    if not path.is_file():
        raise FileNotFoundError(path)
    cached = cache_dir / f"{_cache_key(path, sample_rate)}.npy"
    if cached.is_file():
        try:
            data: AudioArray = np.load(cached, allow_pickle=False).astype(np.float32, copy=False)
            return data
        except (OSError, ValueError):
            cached.unlink(missing_ok=True)  # corrupt cache entry: decode again
    samples = extract_audio(path, sample_rate)
    cache_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=cache_dir, suffix=".npy.part")
    try:
        with os.fdopen(fd, "wb") as fh:
            np.save(fh, samples, allow_pickle=False)
        Path(tmp_name).replace(cached)
    except OSError:
        Path(tmp_name).unlink(missing_ok=True)  # caching is best-effort
    return samples
