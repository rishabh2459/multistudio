"""render — frame-accurate output from a CutList (video filter graphs + master audio)."""

from multicam_engine.render.audio import RenderCancelledError
from multicam_engine.render.encoders import (
    PRESETS,
    OutputPreset,
    available_encoders,
    choose_encoder,
)
from multicam_engine.render.plan import RenderPlan, RenderPlanError, VideoPiece, build_plan
from multicam_engine.render.proxy import make_proxy
from multicam_engine.render.run import RenderProgress, RenderResult, render

__all__ = [
    "PRESETS",
    "OutputPreset",
    "RenderCancelledError",
    "RenderPlan",
    "RenderPlanError",
    "RenderProgress",
    "RenderResult",
    "VideoPiece",
    "available_encoders",
    "build_plan",
    "choose_encoder",
    "make_proxy",
    "render",
]
