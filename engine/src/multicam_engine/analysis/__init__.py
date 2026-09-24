"""analysis — loudness, voice activity and who-is-speaking detection."""

from multicam_engine.analysis.energy import FEATURE_RATE, frame_energy_db, noise_floor_db
from multicam_engine.analysis.speakers import (
    CROSSTALK,
    SILENCE,
    DetectParams,
    SpeakerActivity,
    TrackFeatures,
    analyze_track,
    detect_speakers,
    to_reference,
)
from multicam_engine.analysis.vad import EnergyVad, SileroVad, Vad, VadUnavailableError, load_vad

__all__ = [
    "CROSSTALK",
    "FEATURE_RATE",
    "SILENCE",
    "DetectParams",
    "EnergyVad",
    "SileroVad",
    "SpeakerActivity",
    "TrackFeatures",
    "Vad",
    "VadUnavailableError",
    "analyze_track",
    "detect_speakers",
    "frame_energy_db",
    "load_vad",
    "noise_floor_db",
    "to_reference",
]
