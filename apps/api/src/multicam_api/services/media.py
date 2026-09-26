"""Per-clip media facts for the editor: timing on the timeline, proxies,
waveforms. Probing is cached by (path, size, mtime), so the editor can ask often."""

from __future__ import annotations

import base64
import threading
from fractions import Fraction
from pathlib import Path

import numpy as np

from multicam_api.db.models import ClipRow
from multicam_api.services.projects import clip_to_engine, file_stat
from multicam_engine.media.audio import SYNC_SAMPLE_RATE, load_audio
from multicam_engine.media.probe import ProbeResult, probe
from multicam_engine.render.plan import clip_timing
from multicam_engine.render.proxy import proxy_path

_lock = threading.Lock()
_probes: dict[tuple[str, int, int], ProbeResult] = {}


def probe_cached(path: str) -> ProbeResult:
    """ffprobe once per file version (raises ProbeError / FileNotFoundError)."""
    stat = file_stat(path)
    if stat is None:
        raise FileNotFoundError(path)
    key = (path, stat[0], stat[1])
    with _lock:
        cached = _probes.get(key)
    if cached is None:
        cached = probe(path)
        with _lock:
            if len(_probes) > 256:
                _probes.clear()
            _probes[key] = cached
    return cached


def media_zero(result: ProbeResult) -> Fraction:
    """Container time that players and NLEs call 0 (the earliest stream start)."""
    starts = [result.video_start]
    if result.audio_start is not None:
        starts.append(result.audio_start)
    return min(starts)


def timeline_mapping(row: ClipRow, result: ProbeResult) -> tuple[Fraction, Fraction, Fraction]:
    """(speed, media offset, audio offset) in seconds: media time = t * speed + media
    offset; audio position = t * speed + audio offset."""
    timing = clip_timing(clip_to_engine(row), result)
    media_offset = timing.audio_start + timing.offset - media_zero(result)
    return timing.speed, media_offset, timing.offset


def existing_proxy(row: ClipRow, proxies_dir: Path) -> Path | None:
    source = Path(row.path)
    if not source.is_file():
        return None
    path = proxy_path(source, proxies_dir)
    return path if path.is_file() else None


def waveform(path: str, cache_dir: Path | None, rate: int) -> bytes:
    """Peak level per 1/rate s of the clip's audio, as bytes (0..255 on a 60 dB scale)."""
    audio = load_audio(path, SYNC_SAMPLE_RATE, cache_dir)
    hop = max(1, SYNC_SAMPLE_RATE // rate)
    n = len(audio) // hop
    if n == 0:
        return b""
    peaks = np.abs(audio[: n * hop]).reshape(n, hop).max(axis=1)
    db = 20 * np.log10(np.maximum(peaks, 1e-6))
    scaled = np.clip((db + 60.0) / 60.0, 0.0, 1.0) * 255.0
    return bytes(np.round(scaled).astype(np.uint8).tobytes())


def encode_peaks(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")
