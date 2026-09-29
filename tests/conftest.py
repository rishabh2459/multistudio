"""Shared pytest fixtures."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from multicam_engine.analysis.vad import SILERO_MODEL_FILE, models_dir
from multicam_engine.media.ffmpeg import FFmpegNotFoundError, find_tool
from multicam_engine.reframe.detect import YUNET_MODEL_FILE


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


@pytest.fixture(scope="session")
def face_model() -> Path:
    """Path to the YuNet face model. Skips if not fetched, unless
    ``MULTICAM_REQUIRE_FACE=1`` - then it fails instead."""
    path = models_dir() / YUNET_MODEL_FILE
    if not path.is_file():
        if os.environ.get("MULTICAM_REQUIRE_FACE") == "1":
            pytest.fail(f"face model required but missing: {path}")
        pytest.skip(f"face model not fetched ({path}); run: make fetch-models")
    return path
