"""End-to-end sync on simulated cameras (no ffmpeg needed)."""

import numpy as np
import pytest

from multicam_engine.sync.engine import PairSync, SyncParams, active_seconds, sync_signals

from ..synth import SimClip, camera_pair, speech_like

SR = 8000
# Mic colouring differs between simulated cameras (like real devices), which shifts
# the correlation peak by a fraction of a millisecond; the target is < 1 frame.
TOLERANCE_MS = 1.0


def _errors_ms(ref: np.ndarray, clip: SimClip, result: PairSync) -> tuple[float, float]:
    """Sync error (ms) at the start and at the end of the reference."""
    end = len(ref)
    e0 = (result.offset_at_zero - clip.true_offset_at(0)) / SR * 1000
    e1 = (result.offset_at_zero + result.slope * end - clip.true_offset_at(end)) / SR * 1000
    return e0, e1


@pytest.mark.parametrize("offset_s", [2.5, -3.2, 1.234567, 0.0])
def test_offset_without_drift(offset_s: float) -> None:
    ref, clip = camera_pair(offset_s=offset_s, duration_s=90)
    result = sync_signals(ref, clip.audio, SR)
    e0, e1 = _errors_ms(ref, clip, result)
    assert abs(e0) < TOLERANCE_MS and abs(e1) < TOLERANCE_MS
    assert abs(result.drift_ppm) < 2
    assert result.confidence > 0.9
    assert result.warnings == ()


@pytest.mark.parametrize(("offset_s", "drift_ppm"), [(4.0, 120.0), (-1.5, -250.0), (2.0, 40.0)])
def test_drift_is_measured_and_corrected(offset_s: float, drift_ppm: float) -> None:
    ref, clip = camera_pair(offset_s=offset_s, drift_ppm=drift_ppm, duration_s=300, seed=5)
    result = sync_signals(ref, clip.audio, SR)
    e0, e1 = _errors_ms(ref, clip, result)
    assert abs(e0) < TOLERANCE_MS, e0
    assert abs(e1) < TOLERANCE_MS, e1  # end of recording also within 1 ms
    assert result.drift_ppm == pytest.approx(drift_ppm, abs=2.0)
    assert result.confidence > 0.9


def test_partial_overlap_clip_starts_late_and_ends_early() -> None:
    ref, clip = camera_pair(
        offset_s=0.7, clip_start_s=60, clip_length_s=120, duration_s=300, drift_ppm=80, seed=6
    )
    result = sync_signals(ref, clip.audio, SR)
    e0, e1 = _errors_ms(ref, clip, result)
    assert abs(e0) < TOLERANCE_MS and abs(e1) < TOLERANCE_MS
    assert 115 < result.overlap_s < 125
    assert result.confidence > 0.9


def test_noisy_room() -> None:
    ref, clip = camera_pair(offset_s=2.0, snr_db=0, duration_s=90, seed=7)
    result = sync_signals(ref, clip.audio, SR)
    e0, _ = _errors_ms(ref, clip, result)
    assert abs(e0) < TOLERANCE_MS
    assert result.confidence > 0.8


def test_float32_input_works() -> None:
    ref, clip = camera_pair(offset_s=-0.4, duration_s=60, seed=8)
    result = sync_signals(ref.astype(np.float32), clip.audio.astype(np.float32), SR)
    e0, _ = _errors_ms(ref, clip, result)
    assert abs(e0) < TOLERANCE_MS


def test_silent_clip_warns_instead_of_crashing() -> None:
    ref, _ = camera_pair(duration_s=30)
    result = sync_signals(ref, np.zeros(30 * SR), SR)
    assert result.confidence == 0.0
    assert any("silent" in w for w in result.warnings)


def test_silent_reference_warns() -> None:
    _, clip = camera_pair(duration_s=30)
    result = sync_signals(np.full(30 * SR, 1e-5), clip.audio, SR)
    assert result.confidence == 0.0
    assert any("reference" in w for w in result.warnings)


def test_unrelated_recordings_get_low_confidence() -> None:
    a = speech_like(90, SR, seed=20)
    b = speech_like(90, SR, seed=21)
    result = sync_signals(a, b, SR)
    assert result.confidence < SyncParams().low_confidence
    assert any("low sync confidence" in w for w in result.warnings)


def test_short_clips_warn_about_overlap() -> None:
    ref, clip = camera_pair(offset_s=0.3, duration_s=8, seed=9)
    result = sync_signals(ref, clip.audio, SR)
    assert any("overlap" in w for w in result.warnings)


def test_active_seconds() -> None:
    x = np.zeros(10 * SR)
    x[: 3 * SR] = 0.1
    assert active_seconds(x, SR, -55.0) == pytest.approx(3.0)
    assert active_seconds(np.zeros(5), SR, -55.0) == 0.0
