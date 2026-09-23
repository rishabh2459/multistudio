"""Locate and run the ffmpeg / ffprobe executables.

Lookup order for each tool:
    1. ``MULTICAM_FFMPEG`` / ``MULTICAM_FFPROBE`` environment variable (the desktop
       app points these at its bundled LGPL binaries, Phase 6).
    2. ``PATH`` (development: Homebrew's ffmpeg).
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Literal

Tool = Literal["ffmpeg", "ffprobe"]


class FFmpegNotFoundError(RuntimeError):
    """ffmpeg/ffprobe could not be found."""


class FFmpegError(RuntimeError):
    """ffmpeg/ffprobe ran but failed."""

    def __init__(self, message: str, stderr: str = "") -> None:
        detail = stderr.strip().splitlines()[-5:] if stderr else []
        super().__init__(message + ("\n" + "\n".join(detail) if detail else ""))
        self.stderr = stderr


def find_tool(name: Tool) -> str:
    env_var = f"MULTICAM_{name.upper()}"
    override = os.environ.get(env_var)
    if override:
        if Path(override).is_file():
            return override
        raise FFmpegNotFoundError(f"{env_var} points to {override!r}, which does not exist")
    found = shutil.which(name)
    if found is None:
        raise FFmpegNotFoundError(
            f"{name} not found on PATH (macOS: brew install ffmpeg; "
            f"or set {env_var} to the executable)"
        )
    return found


def run_tool(name: Tool, args: Sequence[str], *, timeout: float | None = None) -> bytes:
    """Run ffmpeg/ffprobe and return stdout. Raises ``FFmpegError`` on failure."""
    cmd = [find_tool(name), "-hide_banner", "-nostdin", *args]
    if name == "ffprobe":
        cmd.remove("-nostdin")  # ffprobe does not accept it
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        raise FFmpegError(f"{name} timed out after {timeout} s") from exc
    if proc.returncode != 0:
        raise FFmpegError(
            f"{name} failed (exit {proc.returncode})", proc.stderr.decode(errors="replace")
        )
    return proc.stdout
