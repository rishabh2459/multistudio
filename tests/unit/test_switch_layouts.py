"""Cover-set switching (PL1): any camera layout, variety, wide frequency, onsets,
confidence - and the old one-solo-per-speaker layout still cuts the same."""

from __future__ import annotations

from itertools import pairwise

import numpy as np
import pytest

from multicam_engine.analysis import CROSSTALK, SILENCE, SpeakerActivity
from multicam_engine.decide import params_for
from multicam_engine.decide.presets import SwitchParams
from multicam_engine.decide.switch import (
    Camera,
    Shot,
    _best_path,
    camera_rewards,
    frame_rewards,
    plan_camera_shots,
    plan_shots,
)
from multicam_engine.models.project import Preset

from .legacy import switch_v1

RATE = 100
BALANCED = params_for(Preset.BALANCED)
A, B, C = 0, 1, 2


def activity(*parts: tuple[int, float], speakers: int = 2, margin: float = 10.0) -> SpeakerActivity:
    labels = np.concatenate([np.full(round(s * RATE), lab, dtype=np.int64) for lab, s in parts])
    n = len(labels)
    return SpeakerActivity(
        labels=labels,
        speakers=tuple(f"S{i}" for i in range(speakers)),
        margin_db=np.where(labels >= 0, margin, 0.0),
        available=np.ones((speakers, n), dtype=bool),
    )


def random_activity(seed: int, speakers: int = 2, turns: int = 60) -> SpeakerActivity:
    rng = np.random.default_rng(seed)
    choices = [*range(speakers), SILENCE, CROSSTALK]
    weights = np.array([4.0] * speakers + [1.0, 0.6])
    weights /= weights.sum()
    parts = [
        (int(rng.choice(choices, p=weights)), float(rng.uniform(0.2, 7.0))) for _ in range(turns)
    ]
    return activity(*parts, speakers=speakers)


def lengths_s(shots: list[Shot], n: int) -> list[float]:
    starts = [s.start for s in shots] + [n]
    return [(b - a) / RATE for a, b in pairwise(starts)]


# ------------------------------------------------------------ old layout unchanged
@pytest.mark.parametrize("seed", range(6))
@pytest.mark.parametrize("preset", [Preset.CALM, Preset.BALANCED, Preset.DYNAMIC])
@pytest.mark.parametrize("has_wide", [False, True])
def test_old_layout_rewards_are_identical(seed: int, preset: Preset, has_wide: bool) -> None:
    act = random_activity(seed, speakers=2 + seed % 2)
    params = params_for(preset)
    new = frame_rewards(act, params, has_wide)
    old = switch_v1.frame_rewards(act, params, has_wide)
    np.testing.assert_array_equal(new, old)


@pytest.mark.parametrize("seed", range(20))
def test_viterbi_without_variety_matches_the_old_one(seed: int) -> None:
    rng = np.random.default_rng(seed)
    rewards = rng.uniform(-0.2, 1.0, size=(int(rng.integers(1, 5)), int(rng.integers(1, 120))))
    min_steps, cost = int(rng.integers(1, 30)), float(rng.uniform(0, 10))
    np.testing.assert_array_equal(
        _best_path(rewards, min_steps, cost), switch_v1._best_path(rewards, min_steps, cost)
    )


@pytest.mark.parametrize("seed", range(6))
@pytest.mark.parametrize("has_wide", [False, True])
def test_old_layout_same_cameras_cut_times_refined(seed: int, has_wide: bool) -> None:
    act = random_activity(seed + 100)
    new = plan_shots(act, BALANCED, has_wide)
    old = switch_v1.plan_shots(act, BALANCED, has_wide)
    assert [s.target for s in new] == [s.target for s in old]
    step = round(0.1 * RATE)
    assert all(abs(a.start - b.start) <= step for a, b in zip(new, old, strict=True))


# ------------------------------------------------------------ layouts
def test_two_shot_is_used_for_the_person_without_a_solo() -> None:
    # Cameras: solo of A, two-shot of B+C. C has no solo.
    cams = [Camera(frozenset({A})), Camera(frozenset({B, C}))]
    act = activity((A, 6.0), (C, 6.0), (A, 6.0), speakers=3)
    shots = plan_camera_shots(act, cams, BALANCED)
    assert [s.target for s in shots] == [0, 1, 0]


def test_solo_beats_a_group_shot_of_the_same_speaker() -> None:
    cams = [Camera(frozenset({A})), Camera(frozenset({B})), Camera(frozenset({A, B}))]
    act = activity((A, 8.0), (B, 8.0))
    assert [s.target for s in plan_camera_shots(act, cams, BALANCED)] == [0, 1]


def test_wide_is_the_fallback_for_someone_no_other_camera_shows() -> None:
    cams = [Camera(frozenset({A})), Camera(frozenset({A, B}), wide=True)]
    act = activity((A, 6.0), (B, 6.0), (A, 6.0))
    assert [s.target for s in plan_camera_shots(act, cams, BALANCED)] == [0, 1, 0]


def test_group_shot_takes_talk_over_when_there_is_no_wide() -> None:
    cams = [Camera(frozenset({A})), Camera(frozenset({B})), Camera(frozenset({A, B}))]
    act = activity((A, 5.0), (CROSSTALK, 4.0), (B, 5.0))
    assert [s.target for s in plan_camera_shots(act, cams, BALANCED)] == [0, 2, 1]


def test_priority_prefers_the_favourite_of_two_angles() -> None:
    cams = [Camera(frozenset({A}), priority=0.8), Camera(frozenset({A}), priority=1.2)]
    act = activity((A, 10.0), speakers=1)
    assert [s.target for s in plan_camera_shots(act, cams, BALANCED)] == [1]


def test_unavailable_group_camera_is_avoided() -> None:
    act = activity((A, 5.0), (C, 6.0), (A, 5.0), speakers=3)
    gone = np.zeros(act.n_frames, dtype=bool)
    cams = [Camera(frozenset({A})), Camera(frozenset({B, C}), available=gone)]
    assert 1 not in [s.target for s in plan_camera_shots(act, cams, BALANCED)]


def test_ten_cameras_ten_speakers() -> None:
    parts = [(i % 10, 3.0) for i in range(40)]
    act = activity(*parts, speakers=10)
    cams = [Camera(frozenset({i})) for i in range(10)]
    shots = plan_camera_shots(act, cams, params_for(Preset.DYNAMIC))
    assert [s.target for s in shots] == [i % 10 for i in range(40)]


# ------------------------------------------------------------ variety / wide frequency
def test_max_shot_forces_variety_in_a_long_monologue() -> None:
    act = activity((A, 60.0), (B, 2.0))
    cams = [Camera(frozenset({A})), Camera(frozenset({B})), Camera(frozenset({A, B}), wide=True)]
    calm = plan_camera_shots(act, cams, BALANCED)
    assert len(calm) <= 3
    varied = SwitchParams(**{**BALANCED.__dict__, "max_shot_s": 8.0})
    shots = plan_camera_shots(act, cams, varied)
    assert len(shots) >= 5
    assert 2 in [s.target for s in shots]  # the wide also shows A
    # Never a long stretch on one camera while A talks.
    long_ = [x for x in lengths_s(shots, act.n_frames)[:-1] if x > 8.0 + 4.0 + 0.1]
    assert not long_


def test_punchy_keeps_min_shot_and_cuts_more() -> None:
    act = random_activity(7, turns=80)
    cams = [Camera(frozenset({A})), Camera(frozenset({B})), Camera(frozenset({A, B}), wide=True)]
    punchy = params_for(Preset.PUNCHY)
    shots = plan_camera_shots(act, cams, punchy)
    assert min(lengths_s(shots, act.n_frames)) >= punchy.min_shot_s - 1e-9
    assert len(shots) > len(plan_camera_shots(act, cams, BALANCED))


def test_wide_frequency_raises_group_rewards() -> None:
    act = activity((A, 5.0), (B, 5.0))
    cams = [Camera(frozenset({A})), Camera(frozenset({A, B}))]
    few = SwitchParams(**{**BALANCED.__dict__, "wide_frequency": 0.0})
    many = SwitchParams(**{**BALANCED.__dict__, "wide_frequency": 1.0})
    assert camera_rewards(act, cams, few)[1, 100] < camera_rewards(act, cams, many)[1, 100]
    assert camera_rewards(act, cams, many)[1, 100] < 1.0  # never beats the solo


# ------------------------------------------------------------ onsets / confidence
def test_cut_snaps_to_the_true_onset() -> None:
    # B starts at 6.53 s: not on the 100 ms grid.
    act = activity((A, 6.0), (SILENCE, 0.53), (B, 6.0))
    shots = plan_shots(act, BALANCED, has_wide=False)
    assert [s.target for s in shots] == [A, B]
    assert shots[1].start == 653 - round(BALANCED.lead_s * RATE)


def test_confidence_reflects_the_speaker_margin() -> None:
    clear = activity((A, 6.0), (B, 6.0), margin=12.0)
    murky = activity((A, 6.0), (B, 6.0), margin=0.5)
    c1 = plan_shots(clear, BALANCED, has_wide=False)[1].confidence
    c2 = plan_shots(murky, BALANCED, has_wide=False)[1].confidence
    assert c1 >= 0.9 > 0.6 > c2
