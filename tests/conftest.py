"""Shared pytest fixtures."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from multicam_engine.analysis.vad import SILERO_MODEL_FILE, models_dir
from multicam_engine.media.ffmpeg import FFmpegNotFoundError, find_tool


@pytest.fixture(scope="session")
def ffmpeg() -> str:
    """Path to ffmpeg. Skips the test if ffmpeg is missing, unless
    ``MULTICAM_REQUIRE_FFMPEG=1`` (set in CI) - then it fails instead."""
    try:
        find_tool("ffprobe")
        return find_tool("ffmpeg")
    except FFmpegNotFoundError as exc:
        if os.environ.get("MULTICAM_REQUIRE_FFMPEG") == "1":
            pytest.fail(f"ffmpeg is required here: {exc}")
        pytest.skip(f"ffmpeg not available: {exc}")


@pytest.fixture(scope="session")
def silero_model() -> Path:
    """Path to the Silero VAD model. Skips if it has not been fetched (``make
    fetch-models``), unless ``MULTICAM_REQUIRE_VAD=1`` - then it fails instead."""
    path = models_dir() / SILERO_MODEL_FILE
    if not path.is_file():
        if os.environ.get("MULTICAM_REQUIRE_VAD") == "1":
            pytest.fail(f"Silero model required but missing: {path}")
        pytest.skip(f"Silero model not fetched ({path}); run: make fetch-models")
    return path
