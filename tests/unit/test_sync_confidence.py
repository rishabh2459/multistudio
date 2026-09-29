"""Confidence scoring: modest peaks on a long line of agreeing windows (real rooms)."""

from multicam_engine.sync.confidence import line_score, sync_confidence
from multicam_engine.sync.drift import DriftFit, WindowMeasurement


def _case(n: int, inliers: int, psr: float) -> float:
    windows = [WindowMeasurement(ref_position=i * 1000.0, offset=5.0, psr=psr) for i in range(n)]
    fit = DriftFit(offset_at_zero=5.0, slope=0.0, inliers=tuple(range(inliers)), residual_rms=0.1)
    return sync_confidence(windows, fit)


def test_line_score_needs_many_agreeing_windows() -> None:
    assert line_score(0) == 0.0
    assert line_score(6) == 0.0
    assert line_score(21) > 0.95


def test_reverberant_room_with_many_agreeing_windows_is_confident() -> None:
    # T1 (3 iPhones, 69 min): 21 of 28 windows on one line, PSR ~7-9.
    assert _case(28, 21, psr=8.0) > 0.7


def test_few_agreeing_windows_with_weak_peaks_stay_low() -> None:
    assert _case(10, 3, psr=6.0) < 0.3


def test_sharp_peaks_still_count_on_their_own() -> None:
    assert _case(3, 3, psr=40.0) > 0.9
