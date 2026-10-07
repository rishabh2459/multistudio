"""Pauses -> removals.

Two ways to call a moment "silent", both on the analysis clock (10 ms frames on
the reference timeline):

* ``db``  every mic is below a loudness cutoff (AutoPod's method: the user sets
  the dB level that fits their mics; per-mic cutoffs are allowed);
* ``vad`` nobody is speaking according to the speaker analysis (Silero VAD +
  levels): robust to fans, AC and room noise where a fixed dB level fails.

A silence must hold on ALL mics, so one person pausing while another talks is
never cut. Only pauses of at least ``min_silence_s`` count; ``pad_s`` of each
pause is kept next to the speech on both sides (breaths, word endings), and what
is left after padding must be at least ``min_removal_s``. Removals are converted
to output frames, rounded inwards so no speech frame is ever removed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Literal

import numpy as np
import numpy.typing as npt

from multicam_engine.analysis.energy import smooth_db
from multicam_engine.analysis.speakers import SILENCE
from multicam_engine.models.cutlist import CutList, Removal, RemovalKind
from multicam_engine.models.time import Rational

FloatArray = npt.NDArray[np.float64]
BoolArray = npt.NDArray[np.bool_]
Mode = Literal["db", "vad"]


@dataclass(frozen=True)
class JumpCutParams:
    mode: Mode = "db"
    #: Everyone below this level (dBFS) = silence (db mode).
    threshold_db: float = -40.0
    #: Per-mic cutoff by row index (db mode); others use ``threshold_db``.
    mic_threshold_db: dict[int, float] = field(default_factory=dict)
    min_silence_s: float = 0.6
    pad_s: float = 0.15
    min_removal_s: float = 0.2
    #: Loudness is smoothed over this window first, so single quiet 10 ms
    #: frames inside a word never count as a pause.
    smooth_s: float = 0.05

    def __post_init__(self) -> None:
        if self.min_silence_s <= 0 or self.pad_s < 0 or self.min_removal_s < 0:
            raise ValueError("min_silence_s must be > 0; pad_s and min_removal_s >= 0")


def silent_frames(
    params: JumpCutParams,
    *,
    rate: int,
    energy_db: FloatArray | None = None,
    labels: npt.NDArray[np.int64] | None = None,
) -> BoolArray:
    """Per analysis frame: is everyone quiet?"""
    if params.mode == "vad":
        if labels is None:
            raise ValueError("vad mode needs the speaker labels of an analysis")
        out: BoolArray = labels == SILENCE
        return out
    if energy_db is None or energy_db.ndim != 2 or energy_db.shape[0] == 0:
        raise ValueError("db mode needs the loudness of every mic (analyse again)")
    window = max(1, round(params.smooth_s * rate))
    quiet = np.ones(energy_db.shape[1], dtype=bool)
    for i, row in enumerate(energy_db):
        cutoff = params.mic_threshold_db.get(i, params.threshold_db)
        quiet &= smooth_db(np.asarray(row, dtype=np.float64), window) < cutoff
    return quiet


def _runs(mask: BoolArray) -> list[tuple[int, int]]:
    """[start, end) of every run of True."""
    if not len(mask):
        return []
    padded = np.concatenate([[False], mask, [False]]).astype(np.int8)
    edges = np.flatnonzero(np.diff(padded))
    return [(int(a), int(b)) for a, b in zip(edges[0::2], edges[1::2], strict=True)]


def find_silences(mask: BoolArray, rate: int, params: JumpCutParams) -> list[tuple[float, float]]:
    """Pauses to remove, in seconds of the reference timeline (after padding)."""
    min_run = params.min_silence_s * rate
    out: list[tuple[float, float]] = []
    for a, b in _runs(mask):
        if b - a < min_run:
            continue
        start = a / rate + params.pad_s
        end = b / rate - params.pad_s
        # the very start / end of the recording has no speech to protect
        if a == 0:
            start = 0.0
        if b == len(mask):
            end = b / rate
        if end - start >= max(params.min_removal_s, 1e-9):
            out.append((start, end))
    return out


def removals_for(
    silences: list[tuple[float, float]],
    fps: Rational,
    duration_frames: int,
    *,
    approved: bool = True,
) -> list[Removal]:
    """Seconds -> output-frame removals, rounded inwards, sorted, non-overlapping."""
    rate = fps.to_fraction()
    out: list[Removal] = []
    last = 0
    for start_s, end_s in silences:
        a = max(last, math.ceil(Fraction(start_s).limit_denominator(100_000) * rate))
        b = min(duration_frames, math.floor(Fraction(end_s).limit_denominator(100_000) * rate))
        if b > a:
            out.append(
                Removal(start_frame=a, end_frame=b, kind=RemovalKind.SILENCE, approved=approved)
            )
            last = b
    return out


def with_silences(cutlist: CutList, silences: list[Removal]) -> CutList:
    """The cutlist with its silence removals replaced by ``silences``. Filler and
    manual removals stay; a new silence overlapping one of them is dropped."""
    kept = [r for r in cutlist.removals if r.kind is not RemovalKind.SILENCE]
    merged = list(kept)
    for s in silences:
        if all(s.end_frame <= r.start_frame or s.start_frame >= r.end_frame for r in kept):
            merged.append(s)
    merged.sort(key=lambda r: r.start_frame)
    return cutlist.model_copy(update={"removals": merged})


def jump_cut_cutlist(
    cutlist: CutList,
    params: JumpCutParams,
    *,
    rate: int,
    energy_db: FloatArray | None = None,
    labels: npt.NDArray[np.int64] | None = None,
    approved: bool = True,
) -> CutList:
    """Pauses of an analysis as (approved) silence removals on the cutlist."""
    mask = silent_frames(params, rate=rate, energy_db=energy_db, labels=labels)
    silences = find_silences(mask, rate, params)
    removals = removals_for(silences, cutlist.fps, cutlist.duration_frames, approved=approved)
    return CutList.model_validate(with_silences(cutlist, removals).model_dump())
