import numpy as np
import pytest

from multicam_engine.sync.gcc_phat import find_peaks, gcc_phat, gcc_phat_curve

from ..synth import record, speech_like

SR = 8000


def _shifted(x: np.ndarray, lag: int) -> np.ndarray:
    """Event at position p in x appears at p + lag in the result (same length)."""
    out = np.zeros_like(x)
    if lag >= 0:
        out[lag:] = x[: len(x) - lag]
    else:
        out[:lag] = x[-lag:]
    return out


@pytest.mark.parametrize("lag", [0, 1, 37, 800, -1, -523, -4000])
def test_integer_lags_are_exact(lag: int) -> None:
    ref = speech_like(8, SR, seed=1)
    peak = gcc_phat(ref, _shifted(ref, lag))
    assert peak.lag == pytest.approx(lag, abs=0.05)
    assert peak.psr > 50


def test_sign_convention_clip_started_earlier_is_positive() -> None:
    # The clip started recording 0.5 s before the reference, so every event
    # appears 0.5 s LATER inside the clip -> positive offset.
    room = speech_like(12, SR, seed=2)
    ref = room[SR:]  # reference started at t = 1.0 s
    clip = room[SR // 2 :]  # clip started at t = 0.5 s (earlier)
    assert gcc_phat(ref, clip).lag == pytest.approx(SR / 2, abs=0.05)


@pytest.mark.parametrize("frac", [0.25, 0.5, 0.8])
def test_sub_sample_precision(frac: float) -> None:
    room = speech_like(10, SR, seed=3)
    ref = record(room, SR, room_start_s=0, start_s=1.0, length_s=8, snr_db=None)
    clip = record(room, SR, room_start_s=0, start_s=1.0 - (100 + frac) / SR, length_s=8,
                  snr_db=None)  # fmt: skip
    assert gcc_phat(ref, clip).lag == pytest.approx(100 + frac, abs=0.2)


def test_robust_to_noise_and_different_microphones() -> None:
    room = speech_like(20, SR, seed=4)
    ref = record(room, SR, room_start_s=0, start_s=2.0, length_s=15, snr_db=0, colour_seed=7)
    clip = record(room, SR, room_start_s=0, start_s=1.25, length_s=15, snr_db=0,
                  colour_seed=8, gain=0.2, seed=9)  # fmt: skip
    peak = gcc_phat(ref, clip)
    assert peak.lag == pytest.approx(0.75 * SR, abs=4)  # within 0.5 ms
    assert peak.psr > 15


def test_unrelated_audio_has_low_psr() -> None:
    a = speech_like(10, SR, seed=10)
    b = speech_like(10, SR, seed=11)
    assert gcc_phat(a, b).psr < 10


def test_polarity_inversion_still_found() -> None:
    ref = speech_like(6, SR, seed=12)
    assert gcc_phat(ref, -_shifted(ref, 250)).lag == pytest.approx(250, abs=0.05)


def test_lag_range_restricts_search() -> None:
    ref = speech_like(6, SR, seed=13)
    clip = _shifted(ref, 300)
    lags, _ = gcc_phat_curve(ref, clip, lag_range=(-100, 100))
    assert lags[0] == -100 and lags[-1] == 100
    assert abs(gcc_phat(ref, clip, lag_range=(-100, 100)).lag) <= 100
    with pytest.raises(ValueError, match="does not overlap"):
        gcc_phat_curve(ref[:10], clip[:10], lag_range=(1000, 2000))


def test_find_peaks_returns_distinct_peaks() -> None:
    lags = np.arange(100, dtype=np.int64)
    values = np.zeros(100)
    values[[20, 22, 70]] = [5.0, 4.0, 3.0]
    peaks = find_peaks(lags, values, count=2, exclusion=5)
    assert [round(p.lag) for p in peaks] == [20, 70]


def test_empty_signal_rejected() -> None:
    with pytest.raises(ValueError, match="empty"):
        gcc_phat(np.zeros(0), np.ones(10))
