"""One recorder, several mics: pick a channel of a multi-channel file (PL1)."""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

from multicam_engine.media.audio import extract_audio, load_audio


def _stereo(path: Path, sr: int = 8000) -> None:
    t = np.arange(sr) / sr
    left = 0.5 * np.sin(2 * np.pi * 440 * t)
    right = np.zeros_like(t)
    right[sr // 2 :] = 0.5  # silent first half, DC-free square-ish second half
    right[sr // 2 :: 2] = -0.5
    pcm = (np.stack([left, right], axis=1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


def test_channel_selection(tmp_path: Path, ffmpeg: str) -> None:
    src = tmp_path / "zoom.wav"
    _stereo(src)
    left = extract_audio(src, 8000, channel=0)
    right = extract_audio(src, 8000, channel=1)
    assert np.abs(left[:4000]).max() > 0.4
    assert np.abs(right[:3900]).max() < 0.01
    assert np.abs(right[4100:]).max() > 0.4
    cache = tmp_path / "cache"
    a = load_audio(src, 8000, cache, channel=0)
    b = load_audio(src, 8000, cache, channel=1)
    assert len(list(cache.glob("*.npy"))) == 2  # one cache entry per channel
    np.testing.assert_allclose(a, left)
    np.testing.assert_allclose(b, right)
