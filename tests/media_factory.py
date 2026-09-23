"""Write small synthetic video files (test pattern + given audio) with ffmpeg."""

from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np
import numpy.typing as npt
from scipy.io import wavfile


def write_wav(path: Path, audio: npt.NDArray[np.floating], sr: int) -> Path:
    pcm = np.clip(np.asarray(audio, dtype=np.float64), -1.0, 1.0)
    wavfile.write(path, sr, (pcm * 32767).astype(np.int16))
    return path


def write_clip(
    ffmpeg: str,
    path: Path,
    audio: npt.NDArray[np.floating] | None,
    sr: int,
    *,
    duration_s: float | None = None,
    fps: str = "30000/1001",
    vfr: bool = False,
    audio_codec: str = "aac",
) -> Path:
    """Tiny test-pattern video with ``audio`` as its soundtrack (or no audio)."""
    if duration_s is None:
        if audio is None:
            raise ValueError("duration_s is required without audio")
        duration_s = len(audio) / sr
    pattern = f"testsrc=size=160x90:rate={fps}:duration={duration_s}"
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
           "-f", "lavfi", "-i", pattern]  # fmt: skip
    if audio is not None:
        wav = write_wav(path.with_suffix(".src.wav"), audio, sr)
        cmd += ["-i", str(wav), "-map", "0:v", "-map", "1:a", "-c:a", audio_codec, "-ar", "48000"]
    if vfr:  # drop every 5th frame and keep real timestamps -> variable frame rate
        cmd += ["-vf", r"select='not(eq(mod(n\,5)\,0))'", "-fps_mode", "vfr"]
    cmd += ["-c:v", "mpeg4", "-q:v", "15", "-t", f"{duration_s}", str(path)]
    subprocess.run(cmd, check=True)
    return path
