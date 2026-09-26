"""Where the frozen (PyInstaller) backend finds ffmpeg and the model files."""

import sys
from pathlib import Path

import pytest

from multicam_engine.analysis.vad import models_dir
from multicam_engine.media.ffmpeg import bundled_tool, find_tool


def test_frozen_backend_uses_the_bundled_ffmpeg(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    exe = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
    (tmp_path / exe).write_bytes(b"")
    monkeypatch.delenv("MULTICAM_FFMPEG", raising=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "multicam-api"))
    assert bundled_tool("ffmpeg") == (tmp_path / exe).resolve()
    assert find_tool("ffmpeg") == str((tmp_path / exe).resolve())
    assert bundled_tool("ffprobe") is None  # not shipped -> falls back to PATH


def test_env_override_wins_and_source_tree_is_not_frozen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert bundled_tool("ffmpeg") is None
    custom = tmp_path / "my-ffmpeg"
    custom.write_bytes(b"")
    monkeypatch.setenv("MULTICAM_FFMPEG", str(custom))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert find_tool("ffmpeg") == str(custom)


def test_models_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MULTICAM_MODELS_DIR", raising=False)
    assert models_dir().parts[-2:] == ("packaging", "models")
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert models_dir() == tmp_path / "models"
    monkeypatch.setenv("MULTICAM_MODELS_DIR", "/elsewhere")
    assert models_dir() == Path("/elsewhere")
