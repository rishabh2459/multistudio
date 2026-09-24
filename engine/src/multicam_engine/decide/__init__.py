"""decide — switching rules (who to show when) and editing presets."""

from multicam_engine.decide.presets import PRESETS, SwitchParams, params_for
from multicam_engine.decide.switch import WIDE, Shot, plan_shots, shots_to_segments

__all__ = [
    "PRESETS",
    "WIDE",
    "Shot",
    "SwitchParams",
    "params_for",
    "plan_shots",
    "shots_to_segments",
]
