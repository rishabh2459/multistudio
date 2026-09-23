"""Synthetic "room" audio and simulated camera recordings with known truth.

A room signal is speech-like: band-limited noise shaped into syllables and
pauses. Each simulated camera records that room with its own start time, clock
speed (drift), microphone colouring and background noise.

Truth for a simulated clip (project sign convention), in samples at ``sr``:
    offset(t) = offset_s * sr * (1 + k) - clip_start_s * sr + k * t,   k = drift_ppm * 1e-6
where t is the position in the reference clip (see ``SimClip.true_offset_at``).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
from scipy import signal as sp_signal

Audio = npt.NDArray[np.float64]


def speech_like(duration_s: float, sr: int, seed: int = 0, pause_ratio: float = 0.3) -> Audio:
    """Band-limited noise shaped like speech: syllables (80-350 ms) and pauses."""
    rng = np.random.default_rng(seed)
    n = int(duration_s * sr)
    sos = sp_signal.butter(4, [150, min(3000, sr * 0.4)], btype="bandpass", fs=sr, output="sos")
    carrier = sp_signal.sosfilt(sos, rng.standard_normal(n))
    env = np.zeros(n)
    pos = 0
    while pos < n:
        if rng.random() < pause_ratio:
            pos += int(rng.uniform(0.1, 0.8) * sr)
            continue
        length = int(rng.uniform(0.08, 0.35) * sr)
        env[pos : pos + length] = rng.uniform(0.3, 1.0) * np.hanning(length)[: max(0, n - pos)]
        pos += length
    out: Audio = np.asarray(carrier, dtype=np.float64) * env
    scaled: Audio = out / (np.max(np.abs(out)) + 1e-12) * 0.5
    return scaled


@dataclass(frozen=True)
class SimClip:
    audio: Audio
    offset0: float  # true offset at reference position 0, samples
    drift_ppm: float
    sr: int

    def true_offset_at(self, ref_position: float) -> float:
        return self.offset0 + self.drift_ppm * 1e-6 * ref_position


def record(
    room: Audio,
    sr: int,
    *,
    room_start_s: float,
    start_s: float,
    length_s: float,
    drift_ppm: float = 0.0,
    snr_db: float | None = 30.0,
    colour_seed: int | None = None,
    gain: float = 1.0,
    seed: int = 1,
) -> Audio:
    """Sample ``room`` as a camera would.

    ``room`` starts at real time ``room_start_s`` (may be negative = pre-roll).
    The camera starts at real time ``start_s`` and its clock runs ``drift_ppm`` fast.
    """
    rng = np.random.default_rng(seed)
    k = drift_ppm * 1e-6
    n = int(length_s * sr)
    real_t = start_s + np.arange(n) / (sr * (1 + k))
    idx = (real_t - room_start_s) * sr
    out = np.interp(idx, np.arange(len(room)), room, left=0.0, right=0.0)
    if colour_seed is not None:  # a different microphone / room response
        crng = np.random.default_rng(colour_seed)
        taps = crng.standard_normal(12) * np.exp(-np.arange(12) / 3.0)
        taps[0] += 1.5
        out = sp_signal.lfilter(taps / np.sum(np.abs(taps)), [1.0], out)
    out = out * gain
    if snr_db is not None:
        power = float(np.mean(out**2)) or 1e-12
        out = out + rng.standard_normal(n) * np.sqrt(power / 10 ** (snr_db / 10))
    result: Audio = out
    return result


def camera_pair(
    *,
    sr: int = 8000,
    duration_s: float = 120.0,
    offset_s: float = 2.5,
    drift_ppm: float = 0.0,
    snr_db: float | None = 30.0,
    clip_start_s: float = 0.0,
    clip_length_s: float | None = None,
    seed: int = 0,
) -> tuple[Audio, SimClip]:
    """Reference recording + a second camera with known offset and drift.

    The reference starts at real time 0. The clip starts ``offset_s`` earlier
    (positive = earlier), then is optionally trimmed by ``clip_start_s`` /
    ``clip_length_s`` (in the clip's own timeline) to simulate partial overlap.
    """
    pre = abs(offset_s) + 5.0
    room = speech_like(duration_s + 2 * pre, sr, seed=seed)
    ref = record(room, sr, room_start_s=-pre, start_s=0.0, length_s=duration_s,
                 snr_db=snr_db, colour_seed=seed + 100, seed=seed + 1)  # fmt: skip
    k = drift_ppm * 1e-6
    cam_start = -offset_s + clip_start_s / (1 + k)
    length = clip_length_s if clip_length_s is not None else duration_s + offset_s - clip_start_s
    sig = record(room, sr, room_start_s=-pre, start_s=cam_start, length_s=length,
                 drift_ppm=drift_ppm, snr_db=snr_db, colour_seed=seed + 200,
                 gain=0.6, seed=seed + 2)  # fmt: skip
    # Trimming the clip's start moves every event earlier in the clip by clip_start_s.
    offset0 = offset_s * sr * (1 + k) - clip_start_s * sr
    return ref, SimClip(sig, offset0, drift_ppm, sr)
