"""Who is speaking, frame by frame, on the reference timeline.

Every speaker camera records everyone in the room, so each person is heard on
every mic ("bleed"). What differs is *how loud*: a person is loudest on the mic
of the camera pointed at them. So for each mic we:

1. measure loudness per 10 ms frame (``energy``) and speech probability (``vad``),
2. move both onto the reference timeline using the sync result (offset + drift),
3. express loudness relative to that mic's own speech level (calibrates away
   different gains / distances; "0 dB" = this mic's person talking normally),
4. pick the mic that is clearly louder than the rest (``margin_db``).

When two mics are both close to their own speech level at once, two people are
talking over each other: ``CROSSTALK``. No speech on any mic: ``SILENCE``.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from multicam_engine.analysis.energy import (
    FEATURE_RATE,
    SILENCE_DB,
    FloatArray,
    frame_energy_db,
    smooth_db,
    speech_level_db,
)
from multicam_engine.analysis.vad import Vad

SILENCE = -1
CROSSTALK = -2

IntArray = npt.NDArray[np.int64]
BoolArray = npt.NDArray[np.bool_]


@dataclass(frozen=True)
class TrackFeatures:
    """Features of one mic on its own clip timeline (``FEATURE_RATE`` frames/s)."""

    energy_db: FloatArray
    vad: FloatArray


@dataclass(frozen=True)
class DetectParams:
    vad_threshold: float = 0.5
    smooth_s: float = 0.25
    #: The loudest mic must beat the runner-up by this much (relative levels).
    margin_db: float = 3.0
    #: If the runner-up is also within this of its own speech level: crosstalk.
    crosstalk_db: float = 4.0
    #: The loudest mic must be within this of its own speech level to count.
    min_level_db: float = -25.0
    #: Talking over each other: within a window of this length, at least two
    #: people each hold ``crosstalk_share`` of the voiced frames.
    crosstalk_window_s: float = 1.0
    crosstalk_share: float = 0.3


@dataclass(frozen=True)
class SpeakerActivity:
    labels: IntArray  # per frame: speaker index, SILENCE or CROSSTALK
    speakers: tuple[str, ...]
    margin_db: FloatArray  # winner's lead over the runner-up (0 when not speech)
    available: BoolArray  # shape (n_speakers, n_frames): clip covers this frame
    frame_rate: int = FEATURE_RATE

    @property
    def n_frames(self) -> int:
        return len(self.labels)

    def seconds(self, label: int) -> float:
        return float(np.count_nonzero(self.labels == label)) / self.frame_rate


def analyze_track(audio: npt.NDArray[np.floating], sample_rate: int, vad: Vad) -> TrackFeatures:
    energy = frame_energy_db(audio, sample_rate)
    prob = vad.speech_probability(audio, sample_rate)
    n = min(len(energy), len(prob))
    return TrackFeatures(energy_db=energy[:n], vad=prob[:n])


def to_reference(
    features: TrackFeatures, n_frames: int, offset_s: float, drift_ppm: float
) -> tuple[FloatArray, FloatArray, BoolArray]:
    """Resample a clip's features onto ``n_frames`` reference frames.

    Reference time ``t`` is clip time ``t + offset_s + drift * t`` (project sign
    convention). Frames the clip does not cover get silence and ``available=False``.
    """
    t = np.arange(n_frames, dtype=np.float64) / FEATURE_RATE
    pos = (t + offset_s + drift_ppm * 1e-6 * t) * FEATURE_RATE
    n = len(features.energy_db)
    available = (pos >= 0) & (pos <= n - 1) if n else np.zeros(n_frames, dtype=bool)
    idx = np.arange(n, dtype=np.float64)
    if n == 0:
        return np.full(n_frames, SILENCE_DB), np.zeros(n_frames), available
    energy = np.interp(pos, idx, features.energy_db, left=SILENCE_DB, right=SILENCE_DB)
    vad = np.interp(pos, idx, features.vad, left=0.0, right=0.0)
    return energy, vad, available


def detect_speakers(
    speakers: list[str],
    energies: list[FloatArray],
    vads: list[FloatArray],
    available: list[BoolArray],
    params: DetectParams | None = None,
) -> SpeakerActivity:
    """Frame labels from per-speaker features that are already on the reference timeline."""
    p = params or DetectParams()
    if not speakers:
        raise ValueError("need at least one speaker track")
    if not (len(speakers) == len(energies) == len(vads) == len(available)):
        raise ValueError("one energy, vad and availability track per speaker")
    n = len(energies[0])
    avail = np.vstack(available).astype(bool)
    vad = np.where(avail, np.vstack(vads), 0.0)
    speech = vad.max(axis=0) >= p.vad_threshold

    window = max(1, round(p.smooth_s * FEATURE_RATE))
    rel = np.full((len(speakers), n), -np.inf)
    for i, energy in enumerate(energies):
        level = speech_level_db(energy, speech & avail[i])
        rel[i] = np.where(avail[i], smooth_db(energy, window) - level, -np.inf)

    labels = np.full(n, SILENCE, dtype=np.int64)
    margin = np.zeros(n)
    if len(speakers) == 1:
        labels[speech & avail[0] & (rel[0] >= p.min_level_db)] = 0
        return SpeakerActivity(labels, tuple(speakers), margin, avail)

    order = np.argsort(-rel, axis=0)
    best, second = order[0], order[1]
    cols = np.arange(n)
    rel_best, rel_second = rel[best, cols], rel[second, cols]
    finite = np.isfinite(rel_second)
    with np.errstate(invalid="ignore"):  # -inf - -inf where no camera covers a frame
        lead = np.where(finite, rel_best - rel_second, np.inf)

    voiced = speech & np.isfinite(rel_best) & (rel_best >= p.min_level_db)
    clear = voiced & (lead >= p.margin_db)
    both = voiced & ~clear & finite & (rel_second >= -p.crosstalk_db)
    unsure = voiced & ~clear & ~both

    labels[clear | unsure] = best[clear | unsure]
    labels[both] = CROSSTALK
    margin[voiced] = np.where(np.isfinite(lead[voiced]), lead[voiced], 99.0)
    labels[_sustained_overlap(labels, len(speakers), p) & voiced] = CROSSTALK
    return SpeakerActivity(labels, tuple(speakers), margin, avail)


def _sustained_overlap(labels: IntArray, n_speakers: int, p: DetectParams) -> BoolArray:
    """Frames inside a window where two or more people each speak a real share.

    Two voices talking at once alternate in loudness syllable by syllable, so
    frame-level labels flicker between them; over a 1 s window both show up.
    """
    window = max(1, round(p.crosstalk_window_s * FEATURE_RATE))
    kernel = np.ones(window)
    voiced = np.convolve((labels != SILENCE).astype(np.float64), kernel, mode="same")
    busy = np.zeros(len(labels), dtype=np.int64)
    for i in range(n_speakers):
        mine = np.convolve((labels == i).astype(np.float64), kernel, mode="same")
        busy += (mine >= p.crosstalk_share * np.maximum(voiced, 1.0)) & (mine > 0)
    out: BoolArray = busy >= 2
    return out
