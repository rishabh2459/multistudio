from pathlib import Path

import numpy as np
import pytest

from multicam_engine.analysis.energy import (
    SILENCE_DB,
    frame_energy_db,
    noise_floor_db,
    smooth_db,
    speech_level_db,
)
from multicam_engine.analysis.vad import EnergyVad, SileroVad, VadUnavailableError, load_vad

SR = 8000


def test_frame_energy_levels() -> None:
    x = np.concatenate([np.full(SR, 0.5), np.zeros(SR // 2), np.full(SR // 2 + 40, 0.05)])
    db = frame_energy_db(x, SR)
    assert len(db) == 200  # 2.005 s -> 200 full 10 ms frames
    assert db[:100] == pytest.approx(20 * np.log10(0.5), abs=1e-9)
    assert (db[100:150] == SILENCE_DB).all()
    assert db[150:] == pytest.approx(-26.02, abs=0.01)


def test_frame_energy_rejects_bad_rate() -> None:
    with pytest.raises(ValueError, match="multiple"):
        frame_energy_db(np.zeros(100), 44_101)
    assert len(frame_energy_db(np.zeros(10), SR)) == 0


def test_smooth_is_power_average() -> None:
    db = np.array([-120.0, 0.0, -120.0])
    out = smooth_db(db, 3)
    assert out[1] == pytest.approx(10 * np.log10(1 / 3), abs=1e-6)
    assert (smooth_db(db, 1) == db).all()


def test_floor_and_speech_level() -> None:
    rng = np.random.default_rng(0)
    db = np.concatenate([rng.normal(-60, 1, 900), rng.normal(-20, 1, 300)])
    speech = np.zeros(len(db), dtype=bool)
    speech[900:] = True
    assert noise_floor_db(db) == pytest.approx(-61.3, abs=1.0)
    assert speech_level_db(db, speech) == pytest.approx(-18.7, abs=1.0)
    # Too little speech to calibrate -> falls back to all frames.
    assert speech_level_db(db, np.zeros(len(db), dtype=bool)) > -25
    assert noise_floor_db(np.full(5, SILENCE_DB)) == SILENCE_DB


def test_energy_vad_finds_loud_parts() -> None:
    rng = np.random.default_rng(1)
    x = rng.standard_normal(3 * SR) * 0.001
    x[SR : 2 * SR] += np.sin(np.arange(SR) * 2 * np.pi * 300 / SR) * 0.3
    p = EnergyVad().speech_probability(x, SR)
    assert len(p) == 300
    assert p[110:190].min() > 0.9
    assert p[:90].max() < 0.1 and p[210:].max() < 0.1


def test_load_vad_fallback(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MULTICAM_MODELS_DIR", str(tmp_path))
    vad, warning = load_vad("auto")
    assert vad.name == "energy" and warning is not None and "fetch-models" in warning
    energy, note = load_vad("energy")
    assert energy.name == "energy" and note is None
    with pytest.raises(VadUnavailableError):
        load_vad("silero")
    with pytest.raises(VadUnavailableError):
        SileroVad()
