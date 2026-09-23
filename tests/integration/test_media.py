"""probe + audio extraction on real (generated) media files. Needs ffmpeg."""

from pathlib import Path

import numpy as np
import pytest

from multicam_engine.media import (
    NoAudioError,
    ProbeError,
    extract_audio,
    load_audio,
    probe,
)
from multicam_engine.media.ffmpeg import FFmpegNotFoundError, find_tool

from ..media_factory import write_clip
from ..synth import speech_like

SR = 8000


def test_probe_cfr_clip(ffmpeg: str, tmp_path: Path) -> None:
    clip = write_clip(ffmpeg, tmp_path / "cam1.mp4", speech_like(4, SR), SR)
    r = probe(clip)
    m = r.media
    assert (m.fps.num, m.fps.den) == (30000, 1001)
    assert not m.is_vfr
    assert (m.width, m.height) == (160, 90)
    assert m.audio_codec == "aac" and m.audio_sample_rate == 48000
    assert abs(m.duration_frames - 120) <= 1  # 4 s at 29.97 fps
    assert r.audio_stream_index is not None


def test_probe_detects_vfr(ffmpeg: str, tmp_path: Path) -> None:
    clip = write_clip(ffmpeg, tmp_path / "phone.mp4", None, SR, duration_s=4, fps="30", vfr=True)
    r = probe(clip)
    assert r.media.is_vfr
    assert r.audio_stream_index is None


def test_probe_errors(ffmpeg: str, tmp_path: Path) -> None:
    with pytest.raises(ProbeError, match="not found"):
        probe(tmp_path / "missing.mp4")
    junk = tmp_path / "junk.mp4"
    junk.write_bytes(b"this is not a video")
    with pytest.raises(ProbeError):
        probe(junk)


def test_extract_audio_matches_source(ffmpeg: str, tmp_path: Path) -> None:
    source = speech_like(3, SR, seed=4)
    clip = write_clip(ffmpeg, tmp_path / "cam.mov", source, SR, audio_codec="pcm_s16le")
    audio = extract_audio(clip, SR)
    assert audio.dtype == np.float32
    assert abs(len(audio) - len(source)) <= SR // 50
    n = min(len(audio), len(source))
    corr = np.corrcoef(audio[:n], source[:n])[0, 1]
    assert corr > 0.99


def test_no_audio_raises(ffmpeg: str, tmp_path: Path) -> None:
    clip = write_clip(ffmpeg, tmp_path / "silent.mp4", None, SR, duration_s=2)
    with pytest.raises(NoAudioError):
        extract_audio(clip)


def test_cache_is_used(ffmpeg: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    clip = write_clip(ffmpeg, tmp_path / "cam.mp4", speech_like(2, SR), SR)
    cache = tmp_path / "cache"
    first = load_audio(clip, SR, cache)
    assert len(list(cache.glob("*.npy"))) == 1

    def fail(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("should have used the cache")

    monkeypatch.setattr("multicam_engine.media.audio.extract_audio", fail)
    second = load_audio(clip, SR, cache)
    np.testing.assert_array_equal(first, second)


def test_env_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MULTICAM_FFMPEG", str(tmp_path / "nope"))
    with pytest.raises(FFmpegNotFoundError, match="MULTICAM_FFMPEG"):
        find_tool("ffmpeg")
