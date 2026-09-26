"""Helpers shared by the NLE writers."""

from __future__ import annotations

import math
import re
from fractions import Fraction
from pathlib import Path, PureWindowsPath
from urllib.parse import quote

_WINDOWS_PATH = re.compile(r"^[A-Za-z]:[\\/]")


def round_to(value: Fraction, step: Fraction) -> Fraction:
    """Nearest multiple of ``step`` (half up)."""
    return math.floor(value / step + Fraction(1, 2)) * step


def to_frames(seconds: Fraction, fps: Fraction) -> int:
    """Nearest frame number (half up)."""
    return math.floor(seconds * fps + Fraction(1, 2))


def file_url(path: Path | str, *, localhost: bool = False) -> str:
    """``file:///Users/me/a%20b.mp4`` (``file://localhost/...`` for FCP7 XML);
    Windows paths become ``file:///C:/...``."""
    text = str(path)
    if _WINDOWS_PATH.match(text):
        encoded = "/" + quote(PureWindowsPath(text).as_posix(), safe="/:")
    else:
        encoded = quote(text.replace("\\", "/"), safe="/")
    return f"file://{'localhost' if localhost else ''}{encoded}"


def reel_names(names: list[str], length: int = 8) -> list[str]:
    """Unique EDL reel names: uppercase letters/digits/_, at most ``length`` chars."""
    out: list[str] = []
    for name in names:
        base = re.sub(r"[^A-Z0-9_]", "", Path(name).stem.upper().replace(" ", "_")) or "REEL"
        candidate = base[:length]
        n = 2
        while candidate in out:
            suffix = str(n)
            candidate = base[: length - len(suffix)] + suffix
            n += 1
        out.append(candidate)
    return out
