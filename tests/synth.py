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


# --------------------------------------------------------------- conversations
@dataclass(frozen=True)
class Turn:
    speaker: int
    start_s: float
    end_s: float


def conversation_turns(
    duration_s: float,
    n_speakers: int = 2,
    *,
    seed: int = 0,
    interjection_prob: float = 0.15,
    overlap_prob: float = 0.08,
) -> list[Turn]:
    """Alternating turns (1.5-10 s) with pauses, short interjections and overlaps."""
    rng = np.random.default_rng(seed)
    turns: list[Turn] = []
    t = 1.0
    speaker = 0
    while t < duration_s - 1.0:
        length = float(rng.uniform(1.5, 10.0))
        end = min(t + length, duration_s - 0.5)
        turns.append(Turn(speaker, t, end))
        listener = (speaker + 1 + int(rng.integers(0, max(1, n_speakers - 1)))) % n_speakers
        if n_speakers > 1 and rng.random() < interjection_prob and end - t > 4.0:
            at = float(rng.uniform(t + 1.0, end - 2.0))  # "mm-hmm" from the listener
            turns.append(Turn(listener, at, at + float(rng.uniform(0.3, 0.7))))
        if n_speakers > 1 and rng.random() < overlap_prob:
            turns.append(Turn(listener, end - 1.2, end + 0.3))  # talk over the end
            t = end + 0.3 + float(rng.uniform(0.2, 0.8))
            speaker = listener
            continue
        t = end + float(rng.uniform(0.2, 1.2))
        speaker = listener
    return sorted(turns, key=lambda turn: turn.start_s)


def voices(
    turns: list[Turn], n_speakers: int, duration_s: float, sr: int, seed: int = 0
) -> list[Audio]:
    """One dry voice signal per speaker: speech-like sound only during their turns."""
    n = int(duration_s * sr)
    out: list[Audio] = []
    for s in range(n_speakers):
        base = speech_like(duration_s, sr, seed=seed * 10 + s + 1, pause_ratio=0.15)
        mask = np.zeros(n)
        for turn in turns:
            if turn.speaker == s:
                a, b = int(turn.start_s * sr), min(n, int(turn.end_s * sr))
                mask[a:b] = 1.0
        ramp = np.hanning(int(0.02 * sr) * 2 + 1)
        mask = np.convolve(mask, ramp / ramp.sum(), mode="same")
        out.append(base * mask)
    return out


def mic_mix(
    voices_: list[Audio],
    own: int | None,
    *,
    bleed_db: float = -9.0,
    gain: float = 1.0,
    snr_db: float = 35.0,
    seed: int = 0,
) -> Audio:
    """What one camera mic hears: its own person at full level, the others at
    ``bleed_db``, plus room noise. ``own=None`` = a wide camera (everyone at -3 dB)."""
    rng = np.random.default_rng(seed)
    bleed = 10 ** (bleed_db / 20)
    mix = np.zeros_like(voices_[0])
    for i, v in enumerate(voices_):
        mix = mix + v * (1.0 if i == own else (0.7 if own is None else bleed))
    noise_rms = 0.05 * 10 ** (-snr_db / 20)
    result: Audio = (mix + rng.standard_normal(len(mix)) * noise_rms) * gain
    return result


def conversation_mics(
    duration_s: float,
    sr: int = 8000,
    *,
    n_speakers: int = 2,
    bleed_db: float = -8.0,
    gains: tuple[float, ...] = (1.0, 0.3, 0.6),
    seed: int = 3,
) -> tuple[list[Turn], list[Audio]]:
    """Turns + one mic signal per speaker camera (each hears everyone, own person loudest)."""
    turns = conversation_turns(duration_s, n_speakers, seed=seed)
    vs = voices(turns, n_speakers, duration_s, sr, seed=seed)
    mics = [
        mic_mix(vs, i, bleed_db=bleed_db, gain=gains[i % len(gains)], seed=seed + 10 + i)
        for i in range(n_speakers)
    ]
    return turns, mics
