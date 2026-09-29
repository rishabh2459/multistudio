"""Turn sync measurements into a 0-1 confidence score.

Two independent signals must agree for a high score:

* **Peak sharpness** - the correlation peak must stand far above the noise
  (peak-to-sidelobe ratio, PSR). Unrelated audio gives PSR around 3-5; a real
  match on speech gives 15-100+.
* **Window agreement** - the windows spread over the recording must fall on one
  straight offset line. Most windows agreeing is strong evidence; a lone window
  is not.

Real rooms (reverb, phone mics, AAC) give modest peaks (PSR 6-12) even when the
alignment is right. But many windows landing on one line within 1 ms cannot
happen by chance (two points define any line; each further window has roughly a
1-in-200 chance), so a long line of agreeing windows (more than ``LINE_FREE``)
also counts as sharpness.
"""

from __future__ import annotations

import math

import numpy as np

from multicam_engine.sync.drift import DriftFit, WindowMeasurement

PSR_FLOOR = 5.0  # at or below this, a peak says nothing
PSR_SCALE = 8.0  # PSR = floor + 3*scale gives ~0.95
FULL_SUPPORT_WINDOWS = 3  # windows that must agree for full confidence
#: Agreeing windows only count as sharpness beyond this many (a handful of weak
#: peaks can agree on a wrong lag with periodic sound, e.g. a music beat) ...
LINE_FREE = 6
LINE_SCALE = 5.0  # ... and LINE_FREE + 3 * LINE_SCALE of them give ~0.95


def psr_score(psr: float) -> float:
    if not math.isfinite(psr):
        return 1.0 if psr > 0 else 0.0
    return 1.0 - math.exp(-max(0.0, psr - PSR_FLOOR) / PSR_SCALE)


def line_score(inliers: int) -> float:
    """Evidence from many windows agreeing on one line."""
    return 1.0 - math.exp(-max(0, inliers - LINE_FREE) / LINE_SCALE)


def sync_confidence(measurements: list[WindowMeasurement], fit: DriftFit | None) -> float:
    measured = [m for m in measurements if m.offset is not None]
    if fit is None or not measured:
        return 0.0
    inlier_psr = [measurements[i].psr for i in fit.inliers]
    agreement = len(fit.inliers) / len(measured)
    peak = float(np.median([psr_score(p) for p in inlier_psr]))
    sharpness = 1.0 - (1.0 - peak) * (1.0 - line_score(len(fit.inliers)))
    support = min(1.0, len(fit.inliers) / FULL_SUPPORT_WINDOWS)
    return round(float(np.clip(agreement * sharpness * support, 0.0, 1.0)), 4)
