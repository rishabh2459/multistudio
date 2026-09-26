"""SMPTE timecode <-> frame numbers, including drop-frame (29.97 / 59.94).

Drop-frame timecode skips the labels :00 and :01 (:00-:03 at 59.94) at the start
of every minute except every tenth minute, so the label keeps up with the wall
clock. No frames are dropped; only their names.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from fractions import Fraction

_TC = re.compile(r"^(\d{2}):(\d{2}):(\d{2})([:;.])(\d{2})$")
_NTSC = (Fraction(30000, 1001), Fraction(60000, 1001))


@dataclass(frozen=True)
class TimecodeRate:
    fps: Fraction  # real frame rate (30000/1001)
    nominal: int  # frames per timecode second (30)
    drop: bool

    @property
    def dropped_per_minute(self) -> int:
        return (2 * self.nominal // 30) if self.drop else 0


def timecode_rate(fps: Fraction, drop: bool | None = None) -> TimecodeRate:
    """Timecode rate for a frame rate. Drop-frame by default at 29.97 and 59.94."""
    nominal = round(fps)
    use_drop = (fps in _NTSC) if drop is None else (drop and fps in _NTSC)
    return TimecodeRate(fps=fps, nominal=nominal, drop=use_drop)


def frames_to_timecode(frames: int, rate: TimecodeRate) -> str:
    if frames < 0:
        raise ValueError("timecode cannot be negative")
    n = rate.nominal
    if rate.drop:
        d = rate.dropped_per_minute
        per_10min = n * 600 - d * 9
        per_min = n * 60 - d
        tens, rem = divmod(frames, per_10min)
        if rem > d:
            frames += d * 9 * tens + d * ((rem - d) // per_min)
        else:
            frames += d * 9 * tens
    ff = frames % n
    total_seconds = frames // n
    hh, mm, ss = total_seconds // 3600 % 24, total_seconds // 60 % 60, total_seconds % 60
    sep = ";" if rate.drop else ":"
    return f"{hh:02d}:{mm:02d}:{ss:02d}{sep}{ff:02d}"


def timecode_to_frames(text: str, rate: TimecodeRate) -> int:
    match = _TC.match(text.strip())
    if not match:
        raise ValueError(f"not a timecode: {text!r}")
    hh, mm, ss, _, ff = match.groups()
    h, m, s, f = int(hh), int(mm), int(ss), int(ff)
    n = rate.nominal
    if f >= n or m >= 60 or s >= 60:
        raise ValueError(f"invalid timecode for {n} fps: {text!r}")
    frames = ((h * 60 + m) * 60 + s) * n + f
    if rate.drop:
        total_minutes = h * 60 + m
        frames -= rate.dropped_per_minute * (total_minutes - total_minutes // 10)
    return frames
