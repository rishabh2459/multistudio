"""Punch-ins: variety on long shots of one camera without another angle.

A long shot is split at a pause of the person on screen (so the cut does not
land mid-word) and the parts alternate between the normal framing and a
tighter one, like an editor punching in on a 4K source.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt


@dataclass(frozen=True)
class PunchParams:
    min_shot_s: float  # only shots at least this long get punch-ins
    min_part_s: float  # no part shorter than this
    tight_scale: float  # zoom of the tight framing


PUNCH_PRESETS: dict[str, PunchParams | None] = {
    "off": None,
    "calm": PunchParams(min_shot_s=16.0, min_part_s=6.0, tight_scale=1.25),
    "balanced": PunchParams(min_shot_s=10.0, min_part_s=4.0, tight_scale=1.3),
    "dynamic": PunchParams(min_shot_s=6.0, min_part_s=3.0, tight_scale=1.4),
}


def split_points(
    start: int,
    end: int,
    speaking: npt.NDArray[np.bool_] | None,
    fps: float,
    params: PunchParams,
) -> list[int]:
    """Frames at which to split the shot [start, end).

    ``speaking[i]`` says whether the person on screen talks during timeline
    frame i (None: unknown, split in the middle). Splits recursively so no
    part is longer than ``min_shot_s``.
    """
    length = (end - start) / fps
    if length <= params.min_shot_s:
        return []
    lo = start + round(params.min_part_s * fps)
    hi = end - round(params.min_part_s * fps)
    if hi <= lo:
        return []
    middle = (start + end) // 2
    cut = middle
    if speaking is not None:
        window = speaking[lo:hi]
        quiet = np.flatnonzero(~window) + lo if len(window) else np.array([], dtype=np.int64)
        if not len(quiet):
            return []  # talking the whole time: better no punch-in than mid-word
        cut = int(quiet[np.argmin(np.abs(quiet - middle))])
    return [
        *split_points(start, cut, speaking, fps, params),
        cut,
        *split_points(cut, end, speaking, fps, params),
    ]
