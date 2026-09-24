from itertools import pairwise
from uuid import uuid4

import numpy as np
import pytest

from multicam_engine.analysis import CROSSTALK, SILENCE, EnergyVad, SpeakerActivity
from multicam_engine.analysis.speakers import analyze_track, detect_speakers, to_reference
from multicam_engine.decide import WIDE, Shot, params_for, plan_shots, shots_to_segments
from multicam_engine.decide.presets import SwitchParams
from multicam_engine.decide.switch import _best_path, fill_short_gaps
from multicam_engine.models.cutlist import CutList
from multicam_engine.models.project import Preset
from multicam_engine.models.time import FPS_25, FPS_29_97

from ..synth import conversation_mics

RATE = 100
BALANCED = params_for(Preset.BALANCED)

A, B = 0, 1


def activity(*parts: tuple[int, float], speakers: int = 2) -> SpeakerActivity:
    """Build labels from (label, seconds) pieces."""
    labels = np.concatenate([np.full(round(s * RATE), lab, dtype=np.int64) for lab, s in parts])
    n = len(labels)
    return SpeakerActivity(
        labels=labels,
        speakers=tuple(f"S{i}" for i in range(speakers)),
        margin_db=np.zeros(n),
        available=np.ones((speakers, n), dtype=bool),
    )


def shown(shots: list[Shot], n: int) -> np.ndarray:
    out = np.zeros(n, dtype=np.int64)
    for i, s in enumerate(shots):
        end = shots[i + 1].start if i + 1 < len(shots) else n
        out[s.start : end] = s.target
    return out


def lengths_s(shots: list[Shot], n: int) -> list[float]:
    starts = [s.start for s in shots] + [n]
    return [(b - a) / RATE for a, b in pairwise(starts)]


def test_simple_turn_change_cuts_just_before_new_speaker() -> None:
    act = activity((A, 6.0), (SILENCE, 0.5), (B, 6.0))
    shots = plan_shots(act, BALANCED, has_wide=False)
    assert [s.target for s in shots] == [A, B]
    cut_s = shots[1].start / RATE
    assert 6.5 - BALANCED.lead_s - 0.11 <= cut_s <= 6.5  # on a 100 ms grid


def test_interjection_does_not_cause_a_cut() -> None:
    act = activity((A, 5.0), (B, 0.5), (A, 5.0))
    assert [s.target for s in plan_shots(act, BALANCED, has_wide=False)] == [A]


def test_short_pauses_do_not_end_a_turn() -> None:
    act = activity((A, 3.0), (SILENCE, 0.5), (A, 3.0), (SILENCE, 0.4), (B, 4.0))
    shots = plan_shots(act, BALANCED, has_wide=False)
    assert [s.target for s in shots] == [A, B]


@pytest.mark.parametrize("preset", list(Preset))
def test_min_shot_length_is_never_violated(preset: Preset) -> None:
    params = params_for(preset)
    rng = np.random.default_rng(0)
    parts = [(int(i % 2), float(rng.uniform(0.3, 3.0))) for i in range(80)]
    act = activity(*parts)
    shots = plan_shots(act, params, has_wide=False)
    assert len(shots) > 3
    assert min(lengths_s(shots, act.n_frames)) >= params.min_shot_s - 1e-9


def test_calm_cuts_less_than_dynamic() -> None:
    rng = np.random.default_rng(1)
    parts = [(int(i % 2), float(rng.uniform(1.0, 6.0))) for i in range(60)]
    act = activity(*parts)
    counts = {p: len(plan_shots(act, params_for(p), has_wide=False)) for p in Preset}
    assert counts[Preset.CALM] < counts[Preset.BALANCED] <= counts[Preset.DYNAMIC]


def test_sustained_crosstalk_goes_wide_only_if_there_is_a_wide_camera() -> None:
    act = activity((A, 5.0), (CROSSTALK, 4.0), (B, 5.0))
    with_wide = plan_shots(act, BALANCED, has_wide=True)
    assert [s.target for s in with_wide] == [A, WIDE, B]
    without = plan_shots(act, BALANCED, has_wide=False)
    assert WIDE not in [s.target for s in without]


def test_brief_crosstalk_stays_on_speaker() -> None:
    act = activity((A, 5.0), (CROSSTALK, 0.5), (A, 5.0))
    assert [s.target for s in plan_shots(act, BALANCED, has_wide=True)] == [A]


def test_long_silence_goes_wide() -> None:
    act = activity((A, 5.0), (SILENCE, 10.0), (A, 5.0))
    targets = [s.target for s in plan_shots(act, BALANCED, has_wide=True)]
    assert targets == [A, WIDE, A]
    assert [s.target for s in plan_shots(act, BALANCED, has_wide=False)] == [A]


def test_camera_that_is_not_recording_is_avoided() -> None:
    act = activity((A, 6.0), (B, 6.0), (A, 6.0))
    act.available[B, :] = False
    assert B not in [s.target for s in plan_shots(act, BALANCED, has_wide=False)]


def test_no_speech_at_all() -> None:
    act = activity((SILENCE, 5.0))
    assert [s.target for s in plan_shots(act, BALANCED, has_wide=True)] == [WIDE]
    empty = activity((SILENCE, 0.0))
    assert plan_shots(empty, BALANCED, has_wide=False) == [Shot(0, 0)]


def test_first_speaker_is_the_opening_shot() -> None:
    act = activity((SILENCE, 2.0), (B, 6.0), (A, 6.0))
    shots = plan_shots(act, BALANCED, has_wide=False)
    assert shots[0] == Shot(0, B)


def test_fill_short_gaps() -> None:
    labels = np.array([0, 0, SILENCE, SILENCE, 0, SILENCE, SILENCE, SILENCE, 1], dtype=np.int64)
    out = fill_short_gaps(labels, max_gap=2)
    assert out.tolist() == [0, 0, 0, 0, 0, SILENCE, SILENCE, SILENCE, 1]
    edges = np.array([SILENCE, 0, SILENCE], dtype=np.int64)  # leading/trailing kept
    assert fill_short_gaps(edges, 5).tolist() == edges.tolist()


def test_best_path_without_min_shot() -> None:
    rewards = np.array([[1, 1, 0, 0, 1, 1], [0, 0, 1, 1, 0, 0]], dtype=np.float64)
    assert _best_path(rewards, min_steps=1, switch_cost=0.5).tolist() == [0, 0, 1, 1, 0, 0]
    assert _best_path(rewards, min_steps=1, switch_cost=5.0).tolist() == [0] * 6
    assert _best_path(rewards[:1], min_steps=3, switch_cost=1.0).tolist() == [0] * 6


def test_realistic_conversation_accuracy() -> None:
    """Synthetic 10-minute interview, bleed -8 dB, very different mic gains."""
    turns, mics = conversation_mics(600, 8000, gains=(1.0, 0.3), seed=3)
    feats = [analyze_track(m, 8000, EnergyVad()) for m in mics]
    n = len(feats[0].energy_db)
    ref = [to_reference(f, n, 0.0, 0.0) for f in feats]
    act = detect_speakers(["A", "B"], [r[0] for r in ref], [r[1] for r in ref], [r[2] for r in ref])
    on_screen = shown(plan_shots(act, BALANCED, has_wide=False), n)
    total = correct = 0
    speaking: list[set[int]] = [set() for _ in range(n)]
    for t in turns:
        for k in range(int(t.start_s * RATE), min(n, int(t.end_s * RATE))):
            speaking[k].add(t.speaker)
    for k in range(n):
        if speaking[k]:
            total += 1
            correct += on_screen[k] in speaking[k]
    assert correct / total >= 0.95


# ------------------------------------------------------------- to segments
def test_shots_to_segments_contiguous_and_valid() -> None:
    a, b, wide = uuid4(), uuid4(), uuid4()
    shots = [Shot(0, 0), Shot(512, 1), Shot(1003, WIDE), Shot(1500, 0)]
    segs = shots_to_segments(
        shots, analysis_rate=RATE, fps=FPS_29_97, duration_frames=600,
        speaker_clips=[a, b], wide_clip=wide,
    )  # fmt: skip
    assert [s.clip_id for s in segs] == [a, b, wide, a]
    assert segs[0].start_frame == 0 and segs[-1].end_frame == 600
    assert segs[1].start_frame == 153  # 5.12 s * 29.97 fps, nearest
    CutList(project_id=uuid4(), fps=FPS_29_97, segments=segs)  # validates contiguity


def test_shots_collapsed_by_snapping_or_duplicates() -> None:
    a, b = uuid4(), uuid4()
    shots = [Shot(0, 0), Shot(1, 1), Shot(300, 1), Shot(301, 0)]
    segs = shots_to_segments(
        shots, analysis_rate=RATE, fps=FPS_25, duration_frames=100,
        speaker_clips=[a, b], wide_clip=None,
    )  # fmt: skip
    assert [s.clip_id for s in segs] == [a, b]
    assert segs[1].start_frame == 75


def test_shots_to_segments_errors() -> None:
    with pytest.raises(ValueError, match="wide"):
        shots_to_segments([Shot(0, WIDE)], analysis_rate=RATE, fps=FPS_25,
                          duration_frames=10, speaker_clips=[uuid4()], wide_clip=None)  # fmt: skip
    with pytest.raises(ValueError, match="positive"):
        shots_to_segments([Shot(0, 0)], analysis_rate=RATE, fps=FPS_25,
                          duration_frames=0, speaker_clips=[uuid4()], wide_clip=None)  # fmt: skip


def test_presets_are_complete() -> None:
    for preset in Preset:
        p = params_for(preset)
        assert isinstance(p, SwitchParams) and p.min_shot_s > p.switch_delay_s > 0
    assert params_for("calm").min_shot_s > params_for("dynamic").min_shot_s
