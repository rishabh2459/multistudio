"""Extract WAV files from test footage so they can be labeled in Audacity.

Temporary helper for Phase 0. Phase 1 replaces the ffmpeg handling with the
full ``media`` module; this keeps the labeling workflow usable today.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".m4v", ".avi", ".mts"}
AUDIO_DIR = "_audio"


def extract_wavs(recording_dir: Path, sample_rate: int = 48_000) -> list[Path]:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("ffmpeg not found on PATH (install with: brew install ffmpeg)")
    videos = sorted(p for p in recording_dir.iterdir() if p.suffix.lower() in VIDEO_EXTENSIONS)
    if not videos:
        raise FileNotFoundError(f"no video files in {recording_dir}")
    out_dir = recording_dir / AUDIO_DIR
    out_dir.mkdir(exist_ok=True)
    outputs: list[Path] = []
    for video in videos:
        out = out_dir / f"{video.name}.wav"  # keep full name so labels map 1:1
        subprocess.run(
            [
                ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                "-i", str(video),
                "-map", "0:a:0", "-vn",
                "-ac", "1", "-ar", str(sample_rate), "-c:a", "pcm_s16le",
                str(out),
            ],
            check=True,
        )  # fmt: skip
        outputs.append(out)
    return outputs
