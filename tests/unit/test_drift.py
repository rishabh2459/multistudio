import numpy as np
import pytest

from multicam_engine.sync.confidence import psr_score, sync_confidence
from multicam_engine.sync.drift import (
    WindowMeasurement,
    fit_drift,
    overlap_range,
    read_at,
    rms_dbfs,
)


def _windows(
    offset0: float, slope: float, n: int = 8, psr: float = 40.0
) -> list[WindowMeasurement]:
    xs = np.linspace(0, 1_000_000, n)
    return [WindowMeasurement(float(x), offset0 + slope * float(x), psr=psr) for x in xs]


def test_fit_recovers_line() -> None:
    fit = fit_drift(_windows(1234.5, 80e-6), inlier_tolerance=2.0)
    assert fit is not None
    assert fit.offset_at_zero == pytest.approx(1234.5, abs=1e-6)
    assert fit.drift_ppm == pytest.approx(80.0, abs=1e-6)
    assert len(fit.inliers) == 8
    assert fit.offset_at(1_000_000) == pytest.approx(1234.5 + 80, abs=1e-6)


def test_fit_ignores_outlier_windows() -> None:
    ws = _windows(-500.0, -120e-6, n=10)
    ws[2] = WindowMeasurement(ws[2].ref_position, 9000.0, psr=40)  # wrong match
    ws[7] = WindowMeasurement(ws[7].ref_position, -3000.0, psr=40)
    fit = fit_drift(ws, inlier_tolerance=2.0)
    assert fit is not None
    assert fit.drift_ppm == pytest.approx(-120.0, abs=1e-6)
    assert 2 not in fit.inliers and 7 not in fit.inliers
    assert len(fit.inliers) == 8


def test_fit_skips_unusable_windows() -> None:
    ws = [
        *_windows(10.0, 0.0, n=3),
        WindowMeasurement(5.0, None, skipped_reason="silence"),
        WindowMeasurement(6.0, 99.0, psr=2.0),  # peak too weak
    ]
    fit = fit_drift(ws, inlier_tolerance=1.0, min_psr=6.0)
    assert fit is not None and fit.inliers == (0, 1, 2)
    assert fit_drift([WindowMeasurement(0.0, None)], inlier_tolerance=1.0) is None


def test_single_window_gives_zero_drift() -> None:
    fit = fit_drift([WindowMeasurement(100.0, 42.0, psr=30)], inlier_tolerance=1.0)
    assert fit is not None and fit.slope == 0.0 and fit.offset_at_zero == 42.0


def test_confidence_rewards_agreement_and_sharpness() -> None:
    good = _windows(0.0, 0.0, n=6, psr=60)
    good_fit = fit_drift(good, inlier_tolerance=1.0)
    assert sync_confidence(good, good_fit) > 0.95

    weak = _windows(0.0, 0.0, n=6, psr=9)
    assert sync_confidence(weak, fit_drift(weak, inlier_tolerance=1.0)) < 0.5

    offsets = [0.0, 7000.0, -3000.0, 12000.0, 500.0, -9000.0]  # no 3 on one line
    scattered = [WindowMeasurement(float(i * 1000), off, psr=60) for i, off in enumerate(offsets)]
    fit = fit_drift(scattered, inlier_tolerance=1.0, min_psr=6.0)
    # A line through two points always fits 2 windows; 2 of 6 is weak evidence.
    assert sync_confidence(scattered, fit) < 0.5
    assert sync_confidence([], None) == 0.0


def test_psr_score_bounds() -> None:
    assert psr_score(3.0) == 0.0
    assert 0.9 < psr_score(40.0) <= 1.0
    assert psr_score(float("inf")) == 1.0


def test_overlap_range() -> None:
    assert overlap_range(1000, 1000, 0) == (0, 1000)
    assert overlap_range(1000, 1000, 200) == (0, 800)  # clip started earlier
    assert overlap_range(1000, 1000, -200) == (200, 1000)  # clip started later
    assert overlap_range(1000, 100, -2000) == (2000, 2000)  # no overlap -> empty


def test_read_at_interpolates_and_zero_pads() -> None:
    x = np.array([0.0, 10.0, 20.0, 30.0])
    out = read_at(x, np.array([-1.0, 0.0, 0.5, 2.25, 3.5]))
    assert out.tolist() == [0.0, 0.0, 5.0, 22.5, 0.0]


def test_rms_dbfs() -> None:
    assert rms_dbfs(np.ones(10)) == pytest.approx(0.0)
    assert rms_dbfs(np.full(10, 0.1)) == pytest.approx(-20.0)
    assert rms_dbfs(np.zeros(10)) == -np.inf
