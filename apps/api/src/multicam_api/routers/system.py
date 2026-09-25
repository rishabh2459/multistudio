"""Health and environment information."""

from __future__ import annotations

from fastapi import APIRouter

from multicam_api import __version__
from multicam_api.routers._common import StateDep
from multicam_api.schemas import Health, SystemInfo
from multicam_engine import __version__ as engine_version
from multicam_engine.analysis.vad import SILERO_MODEL_FILE, models_dir
from multicam_engine.media.ffmpeg import FFmpegError, FFmpegNotFoundError, find_tool, run_tool
from multicam_engine.render.encoders import PRESETS, available_encoders

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/health", response_model=Health)
def health() -> Health:
    """Liveness check (no token needed). The desktop app polls this after launch."""
    return Health(version=__version__)


@router.get("/info", response_model=SystemInfo)
def info(state: StateDep, encoders: bool = False) -> SystemInfo:
    """ffmpeg, AI model and encoder availability. ``encoders=true`` test-encodes
    with each candidate encoder once (a few seconds, then cached)."""
    try:
        ffmpeg: str | None = find_tool("ffmpeg")
        version = run_tool("ffmpeg", ["-version"]).decode(errors="replace").splitlines()[0]
    except (FFmpegNotFoundError, FFmpegError):
        ffmpeg, version = None, None
    h264 = hevc = None
    if encoders and ffmpeg:
        h264, hevc = list(available_encoders("h264")), list(available_encoders("hevc"))
    return SystemInfo(
        api_version=__version__,
        engine_version=engine_version,
        data_dir=str(state.settings.data_dir),
        ffmpeg=ffmpeg,
        ffmpeg_version=version,
        vad_model_available=(models_dir() / SILERO_MODEL_FILE).is_file(),
        encoders_h264=h264,
        encoders_hevc=hevc,
        render_presets=sorted(PRESETS),
    )
