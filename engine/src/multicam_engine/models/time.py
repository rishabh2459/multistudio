"""Exact time arithmetic.

Golden rule of this project: **timeline positions are never floats.**
Float seconds accumulate rounding error and produce off-by-one-frame cuts
(e.g. 29.97 fps is really 30000/1001). Everything here uses integers and
``fractions.Fraction``, and every conversion states its rounding mode.
"""

from __future__ import annotations

import math
from enum import StrEnum
from fractions import Fraction
from typing import Any, Self

from pydantic import ConfigDict, Field, model_validator

from multicam_engine.models._base import StrictModel


class Rounding(StrEnum):
    """How to turn an exact rational position into an integer index."""

    FLOOR = "floor"
    CEIL = "ceil"
    NEAREST = "nearest"  # round half up — deterministic, unlike banker's rounding


class Rational(StrictModel):
    """An exact positive rational number, e.g. a frame rate of 30000/1001."""

    model_config = ConfigDict(frozen=True)

    num: int = Field(gt=0)
    den: int = Field(gt=0)

    @model_validator(mode="before")
    @classmethod
    def _reduce(cls, data: Any) -> Any:
        """Store in lowest terms so that 60000/2002 == 30000/1001."""
        if isinstance(data, dict):
            num, den = data.get("num"), data.get("den")
            if isinstance(num, int) and isinstance(den, int) and num > 0 and den > 0:
                g = math.gcd(num, den)
                return {**data, "num": num // g, "den": den // g}
        return data

    @classmethod
    def from_fraction(cls, value: Fraction) -> Self:
        return cls(num=value.numerator, den=value.denominator)

    @classmethod
    def parse(cls, text: str) -> Self:
        """Parse ffprobe-style rates: ``"30000/1001"``, ``"25/1"`` or ``"25"``.

        Raises ``ValueError`` for unknown/invalid rates such as ffprobe's ``"0/0"``.
        """
        text = text.strip()
        try:
            if "/" in text:
                num_s, den_s = text.split("/", 1)
                num, den = int(num_s), int(den_s)
            else:
                num, den = int(text), 1
        except ValueError as exc:
            raise ValueError(f"not a rational number: {text!r}") from exc
        if num <= 0 or den <= 0:
            raise ValueError(f"rate must be positive, got {text!r}")
        return cls(num=num, den=den)

    def to_fraction(self) -> Fraction:
        return Fraction(self.num, self.den)

    def __str__(self) -> str:
        return f"{self.num}/{self.den}"


# Common frame rates
FPS_23_976 = Rational(num=24000, den=1001)
FPS_24 = Rational(num=24, den=1)
FPS_25 = Rational(num=25, den=1)
FPS_29_97 = Rational(num=30000, den=1001)
FPS_30 = Rational(num=30, den=1)
FPS_50 = Rational(num=50, den=1)
FPS_59_94 = Rational(num=60000, den=1001)
FPS_60 = Rational(num=60, den=1)


def _exact(value: Fraction | int) -> Fraction:
    # bool is an int subclass; float is rejected on purpose (see module docstring).
    if isinstance(value, bool) or not isinstance(value, Fraction | int):
        raise TypeError(
            f"expected Fraction or int, got {type(value).__name__}; "
            "floats are not allowed for time values"
        )
    return Fraction(value)


def round_fraction(value: Fraction, rounding: Rounding) -> int:
    """Convert an exact fraction to an int using an explicit rounding mode."""
    if rounding is Rounding.FLOOR:
        return math.floor(value)
    if rounding is Rounding.CEIL:
        return math.ceil(value)
    return math.floor(value + Fraction(1, 2))


def frames_to_seconds(frames: int, fps: Rational) -> Fraction:
    """Exact time (in seconds) of the start of frame ``frames``."""
    return _exact(frames) / fps.to_fraction()


def seconds_to_frames(
    seconds: Fraction | int, fps: Rational, rounding: Rounding = Rounding.NEAREST
) -> int:
    return round_fraction(_exact(seconds) * fps.to_fraction(), rounding)


def samples_to_seconds(samples: int, sample_rate: int) -> Fraction:
    if sample_rate <= 0:
        raise ValueError("sample_rate must be positive")
    return Fraction(_exact(samples), sample_rate)


def seconds_to_samples(
    seconds: Fraction | int, sample_rate: int, rounding: Rounding = Rounding.NEAREST
) -> int:
    if sample_rate <= 0:
        raise ValueError("sample_rate must be positive")
    return round_fraction(_exact(seconds) * sample_rate, rounding)


def samples_to_frames(
    samples: int, sample_rate: int, fps: Rational, rounding: Rounding = Rounding.NEAREST
) -> int:
    return seconds_to_frames(samples_to_seconds(samples, sample_rate), fps, rounding)


def frames_to_samples(
    frames: int, fps: Rational, sample_rate: int, rounding: Rounding = Rounding.NEAREST
) -> int:
    return seconds_to_samples(frames_to_seconds(frames, fps), sample_rate, rounding)


def ms_to_seconds(ms: int) -> Fraction:
    return Fraction(_exact(ms), 1000)
