"""Shared pytest fixtures."""

from __future__ import annotations

import os

import pytest

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
