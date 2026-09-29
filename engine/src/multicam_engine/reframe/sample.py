"""Read small frames from a clip at regular times, fast.

By default only keyframes are decoded (``-skip_frame nokey``): an hour of 4K
video is sampled in seconds because nothing else is decoded. If the file has
too few keyframes (long GOPs) every frame is decoded and thinned instead.
Timestamps come from ffmpeg's ``showinfo`` so they are the real media times.
"""

from __future__ import annotations

import re
import subprocess
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import numpy.typing as npt

from multicam_engine.media.ffmpeg import find_tool
from multicam_engine.media.probe import ProbeResult, probe

_PTS = re.compile(r"pts_time:\s*(-?[\d.]+)")


@dataclass(frozen=True)
class FrameSample:
    t: float  # seconds since the start of the file (media time)
    image: npt.NDArray[np.uint8]  # H x W x 3, BGR


def sample_size(width: int, height: int, max_side: int) -> tuple[int, int]:
    """Output size (even numbers) that fits in ``max_side`` keeping the aspect."""
    scale = min(1.0, max_side / max(width, height))
    return max(2, round(width * scale / 2) * 2), max(2, round(height * scale / 2) * 2)


def _run(
    path: Path, every_s: float, size: tuple[int, int], keyframes_only: bool
) -> Iterator[FrameSample]:
    w, h = size
    select = f"select='isnan(prev_selected_t)+gte(t-prev_selected_t\\,{every_s:.3f})'"
    cmd = [find_tool("ffmpeg"), "-hide_banner", "-nostdin", "-loglevel", "info"]
    if keyframes_only:
        cmd += ["-skip_frame", "nokey"]
    cmd += ["-i", str(path), "-map", "0:v:0", "-an", "-sn",
            "-vf", f"{select},scale={w}:{h}:flags=bilinear,showinfo",
            "-fps_mode", "vfr", "-f", "rawvideo", "-pix_fmt", "bgr24", "pipe:1"]  # fmt: skip
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert proc.stdout is not None and proc.stderr is not None
    times: list[float] = []
    lock = threading.Condition()

    def read_stderr() -> None:
        assert proc.stderr is not None
        for raw in proc.stderr:
            line = raw.decode(errors="replace")
            if "Parsed_showinfo" in line and "pts_time" in line:
                match = _PTS.search(line)
                if match:
                    with lock:
                        times.append(float(match.group(1)))
                        lock.notify_all()
        with lock:
            times.append(float("nan"))  # end marker
            lock.notify_all()

    reader = threading.Thread(target=read_stderr, daemon=True)
    reader.start()
    frame_bytes = w * h * 3
    index = 0
    try:
        while True:
            data = proc.stdout.read(frame_bytes)
            if len(data) < frame_bytes:
                break
            wanted = index + 1

            def ready(n: int = wanted) -> bool:
                return len(times) >= n

            with lock:
                lock.wait_for(ready, timeout=10)
                t = times[index] if len(times) > index else float("nan")
            index += 1
            if t != t:  # nan: timestamp missing
                continue
            image = np.frombuffer(data, dtype=np.uint8).reshape(h, w, 3).copy()
            yield FrameSample(t, image)
    finally:
        proc.stdout.close()
        proc.kill()
        proc.wait()


def sample_frames(
    path: str | Path,
    *,
    every_s: float = 0.5,
    max_side: int = 640,
    info: ProbeResult | None = None,
) -> Iterator[FrameSample]:
    """Frames about every ``every_s`` seconds (keyframes when that is dense enough)."""
    path = Path(path)
    info = info or probe(path)
    size = sample_size(info.media.width, info.media.height, max_side)
    duration = float(info.duration)
    wanted = max(1, int(duration / max(every_s, 0.1)))
    zero = float(min(info.video_start, info.audio_start or info.video_start))
    fast = list(_run(path, every_s, size, keyframes_only=True))
    # Keyframes too sparse (e.g. one per 10 s)? Decode everything instead.
    samples = fast if len(fast) >= wanted / 4 else list(_run(path, every_s, size, False))
    for s in samples:
        yield FrameSample(s.t - zero, s.image)
