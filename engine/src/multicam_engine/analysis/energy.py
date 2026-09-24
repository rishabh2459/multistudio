"""Per-frame loudness of a microphone track.

All analysis features use one clock: ``FEATURE_RATE`` frames per second
(100 Hz = 10 ms frames). Loudness is RMS in dBFS, floored at ``SILENCE_DB``.
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt

FEATURE_RATE = 100  # frames per second
SILENCE_DB = -120.0

FloatArray = npt.NDArray[np.float64]


def frame_energy_db(audio: npt.NDArray[np.floating], sample_rate: int) -> FloatArray:
    """RMS level (dBFS) of consecutive 10 ms frames. A trailing partial frame is dropped."""
    hop = sample_rate // FEATURE_RATE
    if hop <= 0 or sample_rate % FEATURE_RATE:
        raise ValueError(f"sample_rate must be a multiple of {FEATURE_RATE}")
    n = len(audio) // hop
    if n == 0:
        return np.zeros(0)
    frames = np.asarray(audio[: n * hop], dtype=np.float64).reshape(n, hop)
    power = np.mean(np.square(frames), axis=1)
    return power_to_db(power)


def power_to_db(power: npt.NDArray[np.floating]) -> FloatArray:
    floor = 10.0 ** (SILENCE_DB / 10.0)
    out: FloatArray = 10.0 * np.log10(np.maximum(np.asarray(power, dtype=np.float64), floor))
    return out


def db_to_power(db: npt.NDArray[np.floating]) -> FloatArray:
    out: FloatArray = np.power(10.0, np.asarray(db, dtype=np.float64) / 10.0)
    return out


def smooth_db(db: FloatArray, window_frames: int) -> FloatArray:
    """Moving average in the power domain (so loud frames dominate), back to dB."""
    if window_frames <= 1 or len(db) == 0:
        return db.copy()
    kernel = np.ones(window_frames) / window_frames
    power = np.convolve(db_to_power(db), kernel, mode="same")
    return power_to_db(power)


def noise_floor_db(db: FloatArray, percentile: float = 10.0) -> float:
    """Background level of a track: a low percentile of its frame levels."""
    valid = db[db > SILENCE_DB]
    return float(np.percentile(valid, percentile)) if len(valid) else SILENCE_DB


def speech_level_db(
    db: FloatArray, speech: npt.NDArray[np.bool_], percentile: float = 90.0
) -> float:
    """Typical level of this mic when its own person talks: a high percentile of the
    frames where someone is speaking. Falls back to all frames without speech."""
    pool = db[speech & (db > SILENCE_DB)]
    if len(pool) < FEATURE_RATE:  # less than 1 s of speech: not enough to calibrate
        pool = db[db > SILENCE_DB]
    return float(np.percentile(pool, percentile)) if len(pool) else SILENCE_DB
