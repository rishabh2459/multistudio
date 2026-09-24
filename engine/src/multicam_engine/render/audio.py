"""Continuous master audio: one track for the whole timeline, never cut.

Only the picture switches between cameras; the sound is one uninterrupted mix
(or one chosen mic), so there are no clicks or gaps at cut points (plan X5).

Each source is streamed through ffmpeg (decoded to 48 kHz stereo float) and read
strictly forward. For every output sample at reference time ``t`` we take the
clip's audio at position ``t * (1 + drift) + offset`` - the same line the video
uses. Without drift and with a whole-sample offset this is an exact copy; with
drift, 4-point cubic (Catmull-Rom) interpolation resamples it transparently.
The mix is piped straight into an AAC encoder, so no huge WAV hits the disk.
"""

from __future__ import annotations

import subprocess
import threading
from collections.abc import Callable
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

import numpy as np
import numpy.typing as npt

from multicam_engine.media.ffmpeg import FFmpegError, find_tool
from multicam_engine.render.plan import AudioTrack

SAMPLE_RATE = 48_000
CHANNELS = 2
BLOCK = SAMPLE_RATE * 2  # samples per processing block (2 s)

Block = npt.NDArray[np.float32]


class RenderCancelledError(RuntimeError):
    """The render was cancelled by the user."""


class _SourceStream:
    """Sequential reader of one clip's decoded audio with a sliding buffer."""

    def __init__(self, path: Path) -> None:
        self._proc = subprocess.Popen(
            [find_tool("ffmpeg"), "-hide_banner", "-nostdin", "-loglevel", "error",
             "-i", str(path), "-map", "0:a:0", "-vn", "-ac", str(CHANNELS),
             "-ar", str(SAMPLE_RATE), "-f", "f32le", "pipe:1"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )  # fmt: skip
        self._buf = np.zeros((0, CHANNELS), dtype=np.float32)
        self._start = 0  # sample index of self._buf[0]
        self._eof = False

    def _fill(self, until: int) -> None:
        stdout = self._proc.stdout
        assert stdout is not None
        while not self._eof and self._start + len(self._buf) < until:
            want = max(until - (self._start + len(self._buf)), SAMPLE_RATE) * CHANNELS * 4
            data = stdout.read(want)
            if not data:
                self._eof = True
                break
            usable = len(data) - len(data) % (CHANNELS * 4)
            new = np.frombuffer(data[:usable], dtype="<f4").reshape(-1, CHANNELS)
            self._buf = np.concatenate([self._buf, new])

    def samples(self, first: int, last: int) -> Block:
        """Samples ``first .. last-1`` (zeros outside the recording). Must move forward."""
        out = np.zeros((last - first, CHANNELS), dtype=np.float32)
        if last <= 0:
            return out
        self._fill(last)
        lo = max(first, self._start)
        hi = min(last, self._start + len(self._buf))
        if hi > lo:
            out[lo - first : hi - first] = self._buf[lo - self._start : hi - self._start]
        drop = max(0, first - self._start - 16)  # keep a little history
        if drop:
            self._buf = self._buf[drop:]
            self._start += drop
        return out

    def close(self) -> None:
        if self._proc.poll() is None:
            self._proc.kill()
        self._proc.wait()


def _catmull_rom(p0: Block, p1: Block, p2: Block, p3: Block, t: npt.NDArray[np.float64]) -> Block:
    t = t[:, None]
    out = 0.5 * (
        2 * p1
        + (p2 - p0) * t
        + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t**2
        + (3 * p1 - p0 - 3 * p2 + p3) * t**3
    )
    return out.astype(np.float32)


@dataclass
class _Source:
    track: AudioTrack
    stream: _SourceStream
    offset_samples: float
    speed: float
    exact: bool  # no drift and whole-sample offset: straight copy

    def render(self, n0: int, count: int) -> Block:
        if self.exact:
            first = n0 + round(self.offset_samples)
            return self.stream.samples(first, first + count)
        n = np.arange(n0, n0 + count, dtype=np.float64)
        pos = n * self.speed + self.offset_samples
        base = np.floor(pos)
        frac = pos - base
        first = int(base[0]) - 1
        raw = self.stream.samples(first, int(base[-1]) + 3)
        i = (base - first).astype(np.int64)
        return _catmull_rom(raw[i - 1], raw[i], raw[i + 1], raw[i + 2], frac)


def mix_master_audio(
    tracks: list[AudioTrack],
    duration: Fraction,
    output: Path,
    *,
    audio_kbps: int = 320,
    on_progress: Callable[[float], None] | None = None,
    cancel: threading.Event | None = None,
) -> int:
    """Write the master mix of ``tracks`` (AAC) to ``output``. Returns clipped-sample count."""
    total = round(duration * SAMPLE_RATE)
    encoder = subprocess.Popen(
        [find_tool("ffmpeg"), "-hide_banner", "-nostdin", "-loglevel", "error", "-y",
         "-f", "f32le", "-ar", str(SAMPLE_RATE), "-ac", str(CHANNELS), "-i", "pipe:0",
         "-c:a", "aac", "-b:a", f"{audio_kbps}k", str(output)],
        stdin=subprocess.PIPE, stderr=subprocess.PIPE,
    )  # fmt: skip
    sources: list[_Source] = []
    clipped = 0
    try:
        for track in tracks:
            offset = track.timing.offset * SAMPLE_RATE
            speed = track.timing.speed
            sources.append(
                _Source(
                    track=track,
                    stream=_SourceStream(track.timing.path),
                    offset_samples=float(offset),
                    speed=float(speed),
                    exact=speed == 1 and offset.denominator == 1,
                )
            )
        stdin = encoder.stdin
        assert stdin is not None
        for n0 in range(0, total, BLOCK):
            if cancel is not None and cancel.is_set():
                raise RenderCancelledError("render cancelled")
            count = min(BLOCK, total - n0)
            mix = np.zeros((count, CHANNELS), dtype=np.float32)
            for src in sources:
                mix += src.render(n0, count) * np.float32(src.track.gain)
            over = np.abs(mix) > 1.0
            clipped += int(np.count_nonzero(over))
            np.clip(mix, -1.0, 1.0, out=mix)
            stdin.write(mix.astype("<f4").tobytes())
            if on_progress:
                on_progress((n0 + count) / total)
        stdin.close()
        if encoder.wait() != 0:
            err = encoder.stderr.read().decode(errors="replace") if encoder.stderr else ""
            raise FFmpegError("audio encoder failed", err)
    finally:
        for src in sources:
            src.stream.close()
        if encoder.poll() is None:
            encoder.kill()
            encoder.wait()
    return clipped
