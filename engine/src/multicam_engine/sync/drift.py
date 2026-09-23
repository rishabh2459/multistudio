"""Clock drift: measure the offset in many windows and fit a straight line.

Two devices never run at exactly the same speed (typically 10-100 ppm, i.e.
36-360 ms per hour). So the offset between two clips is not one number but a
line over time:

    offset(t) = offset_at_zero + slope * t        (t = position in the reference)

``slope * 1e6`` is the drift in parts per million. Positive slope -> this clip's
clock runs faster (it accumulates more samples per real second).

The line is fitted robustly: windows with no speech, music or wrong matches
become outliers and are ignored (a RANSAC-style consensus on window pairs,
followed by least squares on the agreeing windows).
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

import numpy as np
import numpy.typing as npt

from multicam_engine.sync.gcc_phat import FloatArray, gcc_phat


@dataclass(frozen=True)
class WindowMeasurement:
    ref_position: float  # window centre in the reference, samples
    offset: float | None  # measured offset (samples); None if the window was skipped
    psr: float = 0.0
    skipped_reason: str | None = None


@dataclass(frozen=True)
class DriftFit:
    offset_at_zero: float  # samples
    slope: float  # dimensionless (ppm / 1e6)
    inliers: tuple[int, ...]  # indices into the measurement list
    residual_rms: float  # samples, over the inliers

    @property
    def drift_ppm(self) -> float:
        return self.slope * 1e6

    def offset_at(self, ref_position: float) -> float:
        return self.offset_at_zero + self.slope * ref_position


def rms_dbfs(x: FloatArray) -> float:
    if len(x) == 0:
        return -np.inf
    rms = float(np.sqrt(np.mean(np.square(x, dtype=np.float64))))
    return 20.0 * np.log10(rms) if rms > 0 else -np.inf


def read_at(x: FloatArray, positions: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    """Linear interpolation of ``x`` at fractional sample positions (0 outside)."""
    base = np.floor(positions)
    frac = positions - base
    i0 = base.astype(np.int64)
    valid = (i0 >= 0) & (i0 < len(x) - 1)
    i0c = np.clip(i0, 0, max(0, len(x) - 2))
    lo = x[i0c].astype(np.float64)
    hi = x[np.minimum(i0c + 1, len(x) - 1)].astype(np.float64)
    out: npt.NDArray[np.float64] = np.where(valid, lo + (hi - lo) * frac, 0.0)
    return out


def overlap_range(n_ref: int, n_sig: int, offset: float) -> tuple[int, int]:
    """Reference positions ``[start, end)`` that also exist in the other clip."""
    start = max(0, int(np.ceil(-offset)))
    end = min(n_ref, int(np.floor(n_sig - offset)))
    return start, max(start, end)


def measure_windows(
    ref: FloatArray,
    sig: FloatArray,
    *,
    offset_at_zero: float,
    slope: float = 0.0,
    sample_rate: int,
    search_s: float,
    window_s: float = 20.0,
    spacing_s: float = 150.0,
    min_windows: int = 5,
    max_windows: int = 30,
    silence_dbfs: float = -55.0,
) -> list[WindowMeasurement]:
    """Refine the offset in windows spread evenly over the overlapping part.

    The clip is read along the predicted line ``offset_at_zero + slope * t``
    (resampled by ``1 + slope``), so drift does not smear the correlation peak
    inside a window. Each window then measures the small residual, searching
    +/- ``search_s`` around the prediction.
    """
    start, end = overlap_range(len(ref), len(sig), offset_at_zero + slope * len(ref) / 2)
    overlap = end - start
    if overlap <= 0:
        return []
    win = min(int(window_s * sample_rate), overlap)
    count = round(overlap / (spacing_s * sample_rate)) + 1
    count = max(min_windows, min(max_windows, count))
    count = max(1, min(count, overlap // max(1, win // 2)))
    search = max(2, int(search_s * sample_rate))

    starts = np.linspace(start, end - win, count) if count > 1 else np.array([start])
    results: list[WindowMeasurement] = []
    for w0f in starts:
        w0 = int(w0f)
        centre = w0 + win / 2.0
        ref_seg = ref[w0 : w0 + win]
        # Positions in sig predicted for reference samples w0-search .. w0+win+search.
        t = np.arange(w0 - search, w0 + win + search, dtype=np.float64)
        positions = t + offset_at_zero + slope * t
        inside = (positions >= 0) & (positions <= len(sig) - 1)
        if np.count_nonzero(inside[search : search + win]) < win // 2:
            results.append(WindowMeasurement(centre, None, skipped_reason="outside clip"))
            continue
        sig_seg = read_at(sig, positions)
        if rms_dbfs(ref_seg) < silence_dbfs or rms_dbfs(sig_seg[inside]) < silence_dbfs:
            results.append(WindowMeasurement(centre, None, skipped_reason="silence"))
            continue
        peak = gcc_phat(ref_seg, sig_seg, lag_range=(0, 2 * search))
        residual = (peak.lag - search) * (1.0 + slope)
        predicted = offset_at_zero + slope * centre
        results.append(WindowMeasurement(centre, predicted + residual, psr=peak.psr))
    return results


def fit_drift(
    measurements: list[WindowMeasurement],
    *,
    inlier_tolerance: float,
    min_psr: float = 4.0,
) -> DriftFit | None:
    """Robust line fit. ``inlier_tolerance`` is in samples. None if nothing usable."""
    usable = [i for i, m in enumerate(measurements) if m.offset is not None and m.psr >= min_psr]
    if not usable:
        return None
    xs = np.array([measurements[i].ref_position for i in usable], dtype=np.float64)
    ys = np.array([measurements[i].offset for i in usable], dtype=np.float64)
    ws = np.array([measurements[i].psr for i in usable], dtype=np.float64)

    def inliers_of(a: float, b: float) -> npt.NDArray[np.bool_]:
        return np.abs(ys - (a + b * xs)) <= inlier_tolerance

    # Candidate lines: every pair of windows, plus "no drift" through each window.
    best_mask = np.zeros(len(usable), dtype=bool)
    best_score = (-1, 0.0)
    candidates: list[tuple[float, float]] = [(float(y), 0.0) for y in ys]
    for i, j in combinations(range(len(usable)), 2):
        if xs[j] != xs[i]:
            b = (ys[j] - ys[i]) / (xs[j] - xs[i])
            candidates.append((float(ys[i] - b * xs[i]), float(b)))
    for a, b in candidates:
        mask = inliers_of(a, b)
        score = (int(mask.sum()), float(ws[mask].sum()))
        if score > best_score:
            best_score, best_mask = score, mask

    x_in, y_in, w_in = xs[best_mask], ys[best_mask], ws[best_mask]
    if len(x_in) >= 2 and np.ptp(x_in) > 0:
        b, a = np.polyfit(x_in, y_in, 1, w=np.sqrt(w_in))
    else:
        a, b = float(np.average(y_in, weights=w_in)), 0.0
    resid = y_in - (a + b * x_in)
    inliers = tuple(usable[k] for k in np.flatnonzero(best_mask))
    return DriftFit(
        offset_at_zero=float(a),
        slope=float(b),
        inliers=inliers,
        residual_rms=float(np.sqrt(np.mean(np.square(resid)))) if len(resid) else 0.0,
    )
