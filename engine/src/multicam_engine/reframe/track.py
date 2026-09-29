"""From per-frame detections to one framing subject per clip.

* primary: the person the camera is on (speaker cameras): the biggest face,
  followed from sample to sample by position so another face passing by does
  not steal the frame;
* group: the box around every face (wide shots).
Gaps (face turned away, low light) are filled by holding the last position,
then easing to the frame centre if nothing is seen for a while.
"""

from __future__ import annotations

from dataclasses import dataclass

from multicam_engine.reframe.detect import Face


@dataclass(frozen=True)
class Detections:
    t: float  # media seconds
    faces: tuple[Face, ...]


@dataclass(frozen=True)
class SubjectPoint:
    t: float
    cx: float
    cy: float
    size: float  # face height (primary) or box height (group), fraction of the frame
    seen: bool  # detected at this sample (False = held / defaulted)


CENTER = (0.5, 0.45)


def _nearest(faces: tuple[Face, ...], cx: float, cy: float, max_jump: float) -> Face | None:
    best: Face | None = None
    best_d = max_jump
    for face in faces:
        d = ((face.cx - cx) ** 2 + (face.cy - cy) ** 2) ** 0.5
        if d < best_d:
            best, best_d = face, d
    return best


def primary_track(
    detections: list[Detections],
    *,
    max_jump: float = 0.25,
    hold_s: float = 3.0,
    default_size: float = 0.3,
) -> list[SubjectPoint]:
    points: list[SubjectPoint] = []
    last: SubjectPoint | None = None
    last_seen_t = float("-inf")
    for d in detections:
        face: Face | None = None
        if last is not None:
            face = _nearest(d.faces, last.cx, last.cy, max_jump)  # keep following
        if face is None and d.faces:
            face = d.faces[0]  # the biggest face (the subject moved or changed)
        if face is not None:
            last_seen_t = d.t
            point = SubjectPoint(d.t, face.cx, face.cy, face.h, True)
        elif last is not None and d.t - last_seen_t <= hold_s:
            point = SubjectPoint(d.t, last.cx, last.cy, last.size, False)  # hold
        else:
            point = SubjectPoint(d.t, CENTER[0], CENTER[1], default_size, False)
        points.append(point)
        last = point
    return points


def group_track(detections: list[Detections], *, default_size: float = 0.6) -> list[SubjectPoint]:
    points: list[SubjectPoint] = []
    for d in detections:
        if d.faces:
            x1 = min(f.x for f in d.faces)
            y1 = min(f.y for f in d.faces)
            x2 = max(f.x + f.w for f in d.faces)
            y2 = max(f.y + f.h for f in d.faces)
            points.append(SubjectPoint(d.t, (x1 + x2) / 2, (y1 + y2) / 2, y2 - y1, True))
        elif points:
            p = points[-1]
            points.append(SubjectPoint(d.t, p.cx, p.cy, p.size, False))
        else:
            points.append(SubjectPoint(d.t, CENTER[0], CENTER[1], default_size, False))
    return points
