import numpy as np
import pytest

from multicam_engine.analysis import (
    CROSSTALK,
    SILENCE,
    EnergyVad,
    SpeakerActivity,
    TrackFeatures,
    analyze_track,
    detect_speakers,
    to_reference,
)
from multicam_engine.decide import WIDE, params_for, plan_shots
from multicam_engine.models.project import Preset

from ..synth import Turn, conversation_mics, mic_mix, voices

SR = 8000


def _detect(mics: list[np.ndarray], names: list[str] | None = None) -> SpeakerActivity:
    feats = [analyze_track(m, SR, EnergyVad()) for m in mics]
    n = min(len(f.energy_db) for f in feats)
    ref = [to_reference(f, n, 0.0, 0.0) for f in feats]
    return detect_speakers(
        names or [f"S{i}" for i in range(len(mics))],
        [r[0] for r in ref],
        [r[1] for r in ref],
        [r[2] for r in ref],
    )


def _truth(turns: list[Turn], n: int) -> np.ndarray:
    truth = np.full(n, SILENCE)
    for t in turns:
        seg = truth[int(t.start_s * 100) : int(t.end_s * 100)]
        seg[(seg != SILENCE) & (seg != t.speaker)] = CROSSTALK
        seg[seg == SILENCE] = t.speaker
    return truth


@pytest.mark.parametrize("bleed_db", [-12.0, -8.0, -5.0])
def test_never_picks_the_wrong_speaker(bleed_db: float) -> None:
    # cam2's mic is 10 dB quieter overall: calibration must handle it.
    turns, mics = conversation_mics(240, SR, bleed_db=bleed_db, gains=(1.0, 0.3), seed=4)
    act = _detect(mics, ["Host", "Guest"])
    truth = _truth(turns, act.n_frames)
    single = truth >= 0
    picked = act.labels[single]
    wrong = (picked >= 0) & (picked != truth[single])
    assert wrong.mean() < 0.02
    assert (act.labels[single] == truth[single]).mean() > 0.55  # rest: gaps between syllables
    assert (act.labels[truth == SILENCE] == SILENCE).mean() > 0.95
    assert act.speakers == ("Host", "Guest")


def test_three_speakers() -> None:
    turns, mics = conversation_mics(240, SR, n_speakers=3, seed=6)
    act = _detect(mics)
    truth = _truth(turns, act.n_frames)
    single = truth >= 0
    wrong = (act.labels[single] >= 0) & (act.labels[single] != truth[single])
    assert wrong.mean() < 0.03


@pytest.mark.parametrize("seed", [2, 3, 4])
def test_talking_over_each_other_goes_wide(seed: int) -> None:
    turns = [Turn(0, 1.0, 9.0), Turn(1, 1.0, 9.0)]  # both talk for 8 s
    vs = voices(turns, 2, 10.0, SR, seed=seed)
    act = _detect([mic_mix(vs, i, bleed_db=-9, seed=i) for i in range(2)])
    voiced = act.labels[150:850][act.labels[150:850] != SILENCE]
    assert (voiced == CROSSTALK).mean() > 0.2
    shots = plan_shots(act, params_for(Preset.BALANCED), has_wide=True)
    ends = [s.start for s in shots[1:]] + [act.n_frames]
    wide_frames = sum(
        max(0, min(e, 900) - max(s.start, 100))
        for s, e in zip(shots, ends, strict=True)
        if s.target == WIDE
    )
    assert wide_frames >= 300  # a good part of the 8 s talk-over is on the wide shot


def test_single_speaker_track() -> None:
    _, mics = conversation_mics(60, SR, seed=8)
    act = _detect(mics[:1])
    assert set(np.unique(act.labels)) <= {0, SILENCE}
    assert act.seconds(0) > 5


def test_to_reference_applies_offset_drift_and_availability() -> None:
    energy = np.arange(1000, dtype=np.float64)  # value = clip frame index
    feats = TrackFeatures(energy_db=energy, vad=np.ones(1000))
    # Clip started 2 s before the reference: reference frame 0 == clip frame 200.
    e, v, avail = to_reference(feats, 900, offset_s=2.0, drift_ppm=0.0)
    assert e[0] == 200 and e[500] == 700
    assert avail[:799].all() and not avail[800:].any()
    assert v[850] == 0.0 and e[850] == -120.0
    # Clip started 1 s later: first second of the reference is not covered.
    e, _, avail = to_reference(feats, 300, offset_s=-1.0, drift_ppm=0.0)
    assert not avail[:100].any() and avail[100] and e[150] == 50
    # Drift: +1000 ppm -> clip runs 0.1 % fast.
    e, _, _ = to_reference(feats, 1000, offset_s=0.0, drift_ppm=1000.0)
    assert e[500] == pytest.approx(500.5)


def test_unavailable_speaker_is_never_chosen() -> None:
    _, mics = conversation_mics(60, SR, seed=9)
    feats = [analyze_track(m, SR, EnergyVad()) for m in mics]
    n = len(feats[0].energy_db)
    ref = [to_reference(f, n, 0.0, 0.0) for f in feats]
    avail = [ref[0][2], np.zeros(n, dtype=bool)]
    act = detect_speakers(["A", "B"], [r[0] for r in ref], [r[1] for r in ref], avail)
    assert not (act.labels == 1).any()


def test_input_validation() -> None:
    with pytest.raises(ValueError, match="at least one"):
        detect_speakers([], [], [], [])
    with pytest.raises(ValueError, match="one energy"):
        detect_speakers(["A", "B"], [np.zeros(3)], [np.zeros(3)], [np.ones(3, dtype=bool)])
