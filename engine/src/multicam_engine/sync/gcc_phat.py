"""GCC-PHAT: generalized cross-correlation with phase transform.

Given a reference signal and another recording of the same sound, find the lag
(in samples) at which they line up. PHAT whitens the spectrum so every frequency
votes equally; this gives a very sharp peak and is robust to the different
colouring of different microphones and rooms.

Two safeguards against PHAT's known weakness (every bin votes equally, even
bins that contain no real sound):

* ``band`` - only frequencies inside the band vote. Removes DC, rumble and mains
  hum at the bottom and resampler roll-off near Nyquist, which are common to
  both recordings but say nothing about alignment.
* ``floor`` - bins much quieter than typical are down-weighted instead of being
  boosted to full weight.

Sign convention (project-wide, see ``SyncResult``):
    ``lag = position of an event in sig - position of the same event in ref``.
    Positive lag -> ``sig`` started recording earlier than ``ref``.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
from scipy import fft as sp_fft

FloatArray = npt.NDArray[np.floating]

#: Samples excluded around a peak when measuring side lobes / picking more peaks.
DEFAULT_PEAK_EXCLUSION = 16
#: Frequencies that vote, as fractions of Nyquist (at 8 kHz: 80 Hz - 3.8 kHz).
DEFAULT_BAND = (0.02, 0.95)
DEFAULT_FLOOR = 0.1


@dataclass(frozen=True)
class Peak:
    lag: float  # samples, sub-sample precision
    height: float  # |correlation| at the peak
    psr: float  # peak-to-sidelobe ratio: (peak - mean) / std of the rest


def _parabolic_offset(left: float, centre: float, right: float) -> float:
    denom = left - 2.0 * centre + right
    if denom == 0.0:
        return 0.0
    return float(np.clip(0.5 * (left - right) / denom, -0.5, 0.5))


def gcc_phat_curve(
    ref: FloatArray,
    sig: FloatArray,
    *,
    lag_range: tuple[int, int] | None = None,
    beta: float = 1.0,
    band: tuple[float, float] | None = DEFAULT_BAND,
    floor: float = DEFAULT_FLOOR,
) -> tuple[npt.NDArray[np.int64], npt.NDArray[np.float64]]:
    """Return ``(lags, |correlation|)`` for every lag in ``lag_range`` (inclusive).

    Without ``lag_range`` every lag with at least one overlapping sample is returned.
    ``beta`` < 1 is "PHAT-beta": partial whitening.
    ``band`` is ``(low, high)`` as fractions of the Nyquist frequency (0..1).
    ``floor``: bins weaker than ``floor`` x the median in-band magnitude are not boosted.
    """
    n_ref, n_sig = len(ref), len(sig)
    if n_ref == 0 or n_sig == 0:
        raise ValueError("signals must not be empty")
    lo_all, hi_all = -(n_ref - 1), n_sig - 1
    lo, hi = lag_range if lag_range is not None else (lo_all, hi_all)
    lo, hi = max(lo, lo_all), min(hi, hi_all)
    if lo > hi:
        raise ValueError(f"lag range {lag_range} does not overlap the signals")

    n = sp_fft.next_fast_len(n_ref + n_sig - 1, real=True)
    spec_ref = sp_fft.rfft(np.asarray(ref, dtype=np.float64), n)
    spec_sig = sp_fft.rfft(np.asarray(sig, dtype=np.float64), n)
    cross = spec_sig * np.conj(spec_ref)
    mag = np.abs(cross)
    if band is not None:
        freq = np.linspace(0.0, 1.0, len(cross))  # fraction of Nyquist
        cross[(freq < band[0]) | (freq > band[1])] = 0.0
        in_band = mag[(freq >= band[0]) & (freq <= band[1])]
    else:
        in_band = mag
    level = float(np.median(in_band)) if len(in_band) else 0.0
    denom = np.maximum(mag, floor * level) + (float(mag.max()) * 1e-12 + 1e-30)
    weighted = cross / np.power(denom, beta)
    cc = np.asarray(sp_fft.irfft(weighted, n), dtype=np.float64)

    lags = np.arange(lo, hi + 1, dtype=np.int64)
    values = np.abs(cc[lags % n])  # negative lags wrap around to the end
    return lags, values


def find_peaks(
    lags: npt.NDArray[np.int64],
    values: npt.NDArray[np.float64],
    *,
    count: int = 1,
    exclusion: int = DEFAULT_PEAK_EXCLUSION,
) -> list[Peak]:
    """Best ``count`` peaks, each at least ``exclusion`` samples from the others."""
    if len(values) == 0:
        return []
    work = values.copy()
    peaks: list[Peak] = []
    for _ in range(count):
        idx = int(np.argmax(work))
        if not np.isfinite(work[idx]) or work[idx] <= 0:
            break
        height = float(values[idx])
        frac = 0.0
        if 0 < idx < len(values) - 1:
            frac = _parabolic_offset(float(values[idx - 1]), height, float(values[idx + 1]))
        lo, hi = max(0, idx - exclusion), min(len(values), idx + exclusion + 1)
        side = np.concatenate([values[:lo], values[hi:]])
        if len(side) >= 2:
            std = float(side.std())
            psr = (height - float(side.mean())) / std if std > 0 else float("inf")
        else:
            psr = 0.0
        peaks.append(Peak(lag=float(lags[idx]) + frac, height=height, psr=psr))
        work[lo:hi] = -np.inf
    return peaks


def gcc_phat(
    ref: FloatArray,
    sig: FloatArray,
    *,
    lag_range: tuple[int, int] | None = None,
    beta: float = 1.0,
    band: tuple[float, float] | None = DEFAULT_BAND,
    exclusion: int = DEFAULT_PEAK_EXCLUSION,
) -> Peak:
    """Single best alignment of ``sig`` against ``ref``."""
    lags, values = gcc_phat_curve(ref, sig, lag_range=lag_range, beta=beta, band=band)
    peaks = find_peaks(lags, values, count=1, exclusion=exclusion)
    if not peaks:
        return Peak(lag=0.0, height=0.0, psr=0.0)
    return peaks[0]
