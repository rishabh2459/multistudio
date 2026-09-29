"""Crop geometry, smoothing and keyframes.

All coordinates are fractions of the source frame (0..1). A crop always has
the output's aspect ratio; ``scale`` 1 is the largest crop of that shape.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import pairwise


@dataclass(frozen=True)
class PathPoint:
    t: float  # timeline seconds
    cx: float
    cy: float


def crop_size(src_w: int, src_h: int, out_w: int, out_h: int, scale: float) -> tuple[float, float]:
    """(width, height) of the crop as fractions of the source."""
    src_aspect = src_w / src_h
    out_aspect = out_w / out_h
    if out_aspect <= src_aspect:  # output narrower: full height
        w, h = out_aspect / src_aspect, 1.0
    else:
        w, h = 1.0, src_aspect / out_aspect
    return w / scale, h / scale


def clamp_center(cx: float, cy: float, cw: float, ch: float) -> tuple[float, float]:
    """Move a crop centre so the crop stays inside the frame."""
    return (
        min(max(cx, cw / 2), 1 - cw / 2),
        min(max(cy, ch / 2), 1 - ch / 2),
    )


def frame_subject(
    cx: float, cy: float, size: float, cw: float, ch: float, *, headroom: float = 0.1
) -> tuple[float, float]:
    """Crop centre for a subject at (cx, cy): centred horizontally; vertically the
    face sits a little above the middle (``headroom`` of the crop height), the
    usual framing for talking heads. Wide group boxes are centred."""
    shift = headroom * ch if size < ch * 0.6 else 0.0
    return clamp_center(cx, cy + shift, cw, ch)


def _ease(points: list[PathPoint], tau_s: float, dead_zone: float) -> list[PathPoint]:
    aim_x, aim_y = points[0].cx, points[0].cy
    x, y = aim_x, aim_y
    out = [PathPoint(points[0].t, x, y)]
    for prev, p in pairwise(points):
        if abs(p.cx - aim_x) > dead_zone:
            aim_x = p.cx
        if abs(p.cy - aim_y) > dead_zone:
            aim_y = p.cy
        k = 1 - math.exp(-abs(p.t - prev.t) / tau_s) if tau_s > 0 else 1.0
        x += (aim_x - x) * k
        y += (aim_y - y) * k
        out.append(PathPoint(p.t, x, y))
    return out


def smooth(points: list[PathPoint], *, dead_zone: float, tau_s: float) -> list[PathPoint]:
    """Camera-operator smoothing: ignore movement inside a dead zone around the
    current aim, then ease towards the new aim. Run forwards and then backwards
    over the whole shot (we know the future), so the crop does not lag behind a
    moving subject: it starts moving a little before and arrives on time."""
    if not points:
        return []
    forward = _ease(points, tau_s, dead_zone)
    backward = _ease(forward[::-1], tau_s, 0.0)[::-1]
    return [PathPoint(p.t, b.cx, b.cy) for p, b in zip(points, backward, strict=True)]


def simplify(points: list[PathPoint], tolerance: float) -> list[PathPoint]:
    """Ramer-Douglas-Peucker on (t, cx, cy): keep the keys needed to stay within
    ``tolerance`` (fraction of the frame) of the smoothed path."""
    if len(points) <= 2:
        return list(points)
    a, b = points[0], points[-1]
    span = b.t - a.t
    worst, index = 0.0, 0
    for i in range(1, len(points) - 1):
        p = points[i]
        f = (p.t - a.t) / span if span > 0 else 0.0
        d = max(abs(p.cx - (a.cx + (b.cx - a.cx) * f)), abs(p.cy - (a.cy + (b.cy - a.cy) * f)))
        if d > worst:
            worst, index = d, i
    if worst <= tolerance:
        return [a, b]
    left = simplify(points[: index + 1], tolerance)
    return left[:-1] + simplify(points[index:], tolerance)
