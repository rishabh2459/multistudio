"""Videos whose every frame shows its own index as a barcode, for frame-exact checks.

Frame ``i`` = 14 vertical bars (bit b of ``i`` white/black) plus a grey marker bar.
Black padding frames have no marker and decode as ``-1``. The code survives lossy
compression and scaling because the bars are wide and flat.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np
import numpy.typing as npt

from .media_factory import write_wav

W, H, BITS = 64, 32, 14
BLACK = -1


def _frame(i: int) -> npt.NDArray[np.uint8]:
    f = np.zeros((H, W), dtype=np.uint8)
    for b in range(BITS):
        if (i >> b) & 1:
            f[:, b * 4 : (b + 1) * 4] = 255
    f[:, 60:64] = 128
    return f


def write_indexed_video(
    ffmpeg: str,
    path: Path,
    n_frames: int,
    *,
    rate: str = "30000/1001",
    vfr: bool = False,
    audio: npt.NDArray[np.floating] | None = None,
    sr: int = 48_000,
) -> Path:
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
           "-f", "rawvideo", "-pix_fmt", "gray", "-s", f"{W}x{H}", "-framerate", rate,
           "-i", "pipe:0"]  # fmt: skip
    if audio is not None:
        wav = write_wav(path.with_suffix(".src.wav"), audio, sr)
        cmd += ["-i", str(wav), "-map", "0:v", "-map", "1:a", "-c:a", "aac", "-b:a", "192k"]
    if vfr:  # drop every 5th frame, keep real timestamps
        cmd += ["-vf", r"select='not(eq(mod(n\,5)\,0))'", "-fps_mode", "vfr"]
    cmd += ["-c:v", "mpeg4", "-q:v", "2", "-pix_fmt", "yuv420p", str(path)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    assert proc.stdin is not None
    for i in range(n_frames):
        proc.stdin.write(_frame(i).tobytes())
    proc.stdin.close()
    assert proc.wait() == 0
    return path


def read_indices(ffmpeg: str, path: Path) -> list[int]:
    raw = subprocess.run(
        [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-i", str(path),
         "-fps_mode", "passthrough", "-f", "rawvideo", "-pix_fmt", "gray",
         "-s", f"{W}x{H}", "pipe:1"],
        capture_output=True, check=True,
    ).stdout  # fmt: skip
    frames = np.frombuffer(raw, dtype=np.uint8).reshape(-1, H, W)
    out: list[int] = []
    for f in frames:
        if f[:, 61:63].mean() < 64:
            out.append(BLACK)
            continue
        value = 0
        for b in range(BITS):
            if f[:, b * 4 + 1 : b * 4 + 3].mean() > 128:
                value |= 1 << b
        out.append(value)
    return out


def read_audio(ffmpeg: str, path: Path, sr: int = 48_000) -> npt.NDArray[np.float64]:
    raw = subprocess.run(
        [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-i", str(path),
         "-map", "0:a:0", "-ac", "1", "-ar", str(sr), "-f", "f32le", "pipe:1"],
        capture_output=True, check=True,
    ).stdout  # fmt: skip
    return np.frombuffer(raw, dtype="<f4").astype(np.float64)


def clicks(times_s: list[float], duration_s: float, sr: int = 48_000) -> npt.NDArray[np.float64]:
    """Short 2 kHz tone bursts (5 ms) starting at ``times_s`` over quiet noise."""
    n = int(duration_s * sr)
    x = np.random.default_rng(0).standard_normal(n) * 0.001
    burst = np.sin(2 * np.pi * 2000 * np.arange(int(0.005 * sr)) / sr) * 0.8
    for t in times_s:
        a = round(t * sr)
        x[a : a + len(burst)] += burst[: max(0, n - a)]
    return x


def click_onsets(
    audio: npt.NDArray[np.float64], sr: int = 48_000, threshold: float = 0.2
) -> list[float]:
    """Onset times (s) of loud bursts, at least 100 ms apart."""
    loud = np.flatnonzero(np.abs(audio) > threshold)
    onsets: list[float] = []
    last = -1e9
    for i in loud:
        if i - last > 0.1 * sr:
            onsets.append(i / sr)
        last = float(i)
    return onsets
