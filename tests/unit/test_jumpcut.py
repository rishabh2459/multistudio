"""Jump cuts: pauses -> removals (dB cutoff and speech detection)."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import numpy as np
import pytest

from multicam_engine.analysis.speakers import CROSSTALK, SILENCE, SpeakerActivity
from multicam_engine.jumpcut import (
    JumpCutParams,
    find_silences,
    jump_cut_cutlist,
    removals_for,
    silent_frames,
    with_silences,
)
from multicam_engine.models import CutList
from multicam_engine.models.cutlist import Removal, RemovalKind, Segment
from multicam_engine.models.time import Rational
from multicam_engine.pipeline import Analysis

RATE = 100
FPS = Rational(num=25, den=1)


def _levels(spans: list[tuple[float, float, float]], seconds: float, floor: float) -> np.ndarray:
    """A loudness track: `floor` dB, with (start_s, end_s, level) spans of speech."""
    x = np.full(round(seconds * RATE), floor)
    for a, b, level in spans:
        x[round(a * RATE) : round(b * RATE)] = level
    return x


def _close(got: list[tuple[float, float]], want: list[tuple[float, float]]) -> bool:
    """Within 30 ms: loudness smoothing (50 ms) keeps a little more around words."""
    return len(got) == len(want) and bool(np.allclose(got, want, atol=0.03))


def _cutlist(seconds: int) -> CutList:
    return CutList(
        project_id=uuid4(),
        fps=FPS,
        segments=[Segment(clip_id=uuid4(), start_frame=0, end_frame=seconds * 25)],
    )


def test_db_mode_needs_every_mic_quiet() -> None:
    host = _levels([(0, 2, -20), (5, 8, -18)], 10, -60)
    guest = _levels([(3, 4, -22)], 10, -58)  # guest talks inside the host's pause
    energy = np.vstack([host, guest])
    mask = silent_frames(JumpCutParams(threshold_db=-40), rate=RATE, energy_db=energy)
    assert not mask[round(3.5 * RATE)]  # guest speaking: not silent
    assert mask[round(2.5 * RATE)] and mask[round(4.5 * RATE)]
    silences = find_silences(mask, RATE, JumpCutParams(min_silence_s=0.6, pad_s=0.1))
    # pauses: 2..3 (1 s), 4..5 (1 s), 8..10 (end of recording: no pad at the end)
    assert _close(silences, [(2.1, 2.9), (4.1, 4.9), (8.1, 10.0)])


def test_padding_min_pause_and_per_mic_cutoff() -> None:
    host = _levels([(0, 1, -20), (1.4, 3, -20), (4, 5, -20)], 5, -45)  # noisy room: -45
    energy = host[None, :]
    strict = silent_frames(JumpCutParams(threshold_db=-50), rate=RATE, energy_db=energy)
    assert not strict.any()  # the room noise is above -50 dB
    per_mic = JumpCutParams(threshold_db=-50, mic_threshold_db={0: -40})
    mask = silent_frames(per_mic, rate=RATE, energy_db=energy)
    params = JumpCutParams(min_silence_s=0.6, pad_s=0.15, min_removal_s=0.2)
    # the 0.4 s gap at 1..1.4 is too short; 3..4 becomes 3.15..3.85
    assert _close(find_silences(mask, RATE, params), [(3.15, 3.85)])
    big_pad = JumpCutParams(min_silence_s=0.6, pad_s=0.45, min_removal_s=0.2)
    assert find_silences(mask, RATE, big_pad) == []  # only 0.1 s would be left
    with pytest.raises(ValueError):
        JumpCutParams(min_silence_s=0)


def test_vad_mode_uses_the_speaker_labels() -> None:
    labels = np.array(
        [0] * 100 + [SILENCE] * 120 + [CROSSTALK] * 50 + [SILENCE] * 30, dtype=np.int64
    )
    mask = silent_frames(JumpCutParams(mode="vad"), rate=RATE, labels=labels)
    assert mask.sum() == 150
    got = find_silences(mask, RATE, JumpCutParams(mode="vad", min_silence_s=0.5, pad_s=0.1))
    assert _close(got, [(1.1, 2.1)])  # the last 0.3 s pause is too short
    with pytest.raises(ValueError, match="labels"):
        silent_frames(JumpCutParams(mode="vad"), rate=RATE)
    with pytest.raises(ValueError, match="analyse again"):
        silent_frames(JumpCutParams(), rate=RATE)


def test_removals_round_inwards_and_merge_with_fillers() -> None:
    cut = _cutlist(10)
    rem = removals_for([(1.01, 1.99), (3.0, 3.03), (9.5, 12.0)], FPS, cut.duration_frames)
    # 1.01 s -> frame 26 (ceil), 1.99 s -> frame 49 (floor); 3.0..3.03 is < 1 frame
    assert [(r.start_frame, r.end_frame) for r in rem] == [(26, 49), (238, 250)]
    assert all(r.kind is RemovalKind.SILENCE and r.approved for r in rem)
    filler = Removal(start_frame=40, end_frame=45, kind=RemovalKind.FILLER, approved=True)
    old = Removal(start_frame=100, end_frame=120, kind=RemovalKind.SILENCE)
    merged = with_silences(cut.model_copy(update={"removals": [filler, old]}), rem)
    # the old silence is replaced; the new one overlapping the filler is dropped
    assert [(r.start_frame, r.kind) for r in merged.removals] == [
        (40, RemovalKind.FILLER),
        (238, RemovalKind.SILENCE),
    ]


def test_jump_cut_cutlist_end_to_end() -> None:
    cut = _cutlist(10)
    energy = _levels([(0, 3, -20), (5, 10, -20)], 10, -60)[None, :]
    out = jump_cut_cutlist(cut, JumpCutParams(pad_s=0.2), rate=RATE, energy_db=energy)
    assert [(r.start_frame, r.end_frame) for r in out.removals] == [(81, 119)]  # ~3.2 .. 4.8 s
    review = jump_cut_cutlist(
        cut, JumpCutParams(pad_s=0.2), rate=RATE, energy_db=energy, approved=False
    )
    assert not review.removals[0].approved


def test_analysis_keeps_the_mic_levels(tmp_path: Path) -> None:
    activity = SpeakerActivity(
        labels=np.array([0, SILENCE, 1], dtype=np.int64),
        speakers=("A", "B"),
        margin_db=np.zeros(3),
        available=np.ones((2, 3), dtype=bool),
    )
    energy = np.array([[-20.0, -60.0, -50.0], [-55.0, -61.0, -21.0]])
    a = Analysis(activity, [uuid4(), uuid4()], "energy", energy_db=energy)
    a.save(tmp_path / "a.npz")
    b = Analysis.load(tmp_path / "a.npz")
    assert b.energy_db is not None and np.allclose(b.energy_db, energy)
    old = Analysis(activity, a.speaker_clip_ids, "energy")
    old.save(tmp_path / "old.npz")
    assert Analysis.load(tmp_path / "old.npz").energy_db is None  # saved before the field
