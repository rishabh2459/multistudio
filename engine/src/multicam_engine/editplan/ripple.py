"""Cut an EditPlan down to some ranges of its timeline, closing the gaps.

* ``slice_plan``  keep [start, end) only (a social clip from an in/out range);
* ``apply_removals``  take the approved removals out on EVERY track at the same
  frames (jump cuts / fillers) — a ripple delete that keeps picture and all mics
  in sync.

Both keep a list of ranges and lay them end to end. A piece cut at its head gets
its source moved forward by the frames cut (exact, through Premiere ticks);
markers inside removed parts disappear; reframe paths and Motion keys move with
the picture.
"""

from __future__ import annotations

import math
from fractions import Fraction
from typing import TypeVar
from uuid import UUID

from multicam_engine.editplan.model import (
    TICKS_PER_SECOND,
    AudioTrack,
    EditPlan,
    PlanMarker,
    PlanMedia,
    PlanOverlay,
    PlanPiece,
    PlanRemoval,
    PlanTransformKey,
    TrackPiece,
    VideoEvent,
    VideoTrack,
)
from multicam_engine.editplan.transform import transform_at
from multicam_engine.models.cutlist import Reframe, ReframeKey

P = TypeVar("P", bound=PlanPiece)
Range = tuple[int, int]


def _half_up(x: Fraction) -> int:
    return math.floor(x + Fraction(1, 2))


class _Keeper:
    """Old timeline frames -> new frames for a set of kept ranges."""

    def __init__(self, plan: EditPlan, keep: list[Range]) -> None:
        self.fps = plan.sequence.fps.to_fraction()
        self.media: dict[UUID, PlanMedia] = plan.media_by_id()
        self.keep: list[tuple[int, int, int]] = []  # (old start, old end, new start)
        at = 0
        for a, b in keep:
            if b > a:
                self.keep.append((a, b, at))
                at += b - a
        self.duration = at

    def frame(self, old: int) -> int | None:
        """New position of an old frame (None if it was removed)."""
        for a, b, o in self.keep:
            if a <= old < b:
                return o + old - a
        return None

    def _source(self, piece: PlanPiece, cut_frames: int) -> dict[str, int]:
        if cut_frames == 0:
            return {
                "source_in_frame": piece.source_in_frame,
                "source_in_sample": piece.source_in_sample,
                "source_in_ticks": piece.source_in_ticks,
            }
        m = self.media[piece.clip_id]
        ticks = piece.source_in_ticks + _half_up(Fraction(cut_frames) / self.fps * TICKS_PER_SECOND)
        seconds = Fraction(ticks, TICKS_PER_SECOND)
        return {
            "source_in_frame": _half_up(seconds * m.fps.to_fraction()),
            "source_in_sample": _half_up(seconds * m.sample_rate),
            "source_in_ticks": ticks,
        }

    @staticmethod
    def _keys(
        keys: list[PlanTransformKey] | None, lo: int, hi: int, shift: int
    ) -> list[PlanTransformKey] | None:
        if not keys:
            return keys
        out = [transform_at(keys, lo).model_copy(update={"frame": lo - shift})]
        out += [k.model_copy(update={"frame": k.frame - shift}) for k in keys if lo < k.frame < hi]
        return out

    @staticmethod
    def _reframe(r: Reframe | None, lo: int, shift: int) -> Reframe | None:
        if r is None or not r.path:
            return r
        cx, cy = r.center_at(lo)
        keys = [ReframeKey(frame=lo - shift, cx=cx, cy=cy)]
        keys += [
            ReframeKey(frame=k.frame - shift, cx=k.cx, cy=k.cy) for k in r.path if k.frame > lo
        ]
        return Reframe(cx=cx, cy=cy, scale=r.scale, path=keys, manual=r.manual)

    def pieces(self, items: list[P]) -> list[P]:
        out: list[P] = []
        for p in items:
            for a, b, o in self.keep:
                lo, hi = max(p.start, a), min(p.end, b)
                if hi <= lo:
                    continue
                shift = a - o  # old frame - shift = new frame
                update: dict[str, object] = {
                    "start": lo - shift,
                    "end": hi - shift,
                    **self._source(p, lo - p.start),
                }
                if isinstance(p, (VideoEvent, TrackPiece, PlanOverlay)):
                    update["transform"] = self._keys(p.transform, lo, hi, shift)
                if isinstance(p, VideoEvent):
                    update["reframe"] = self._reframe(p.reframe, lo, shift)
                    update["reframe_vertical"] = self._reframe(p.reframe_vertical, lo, shift)
                out.append(type(p).model_validate({**p.model_dump(), **_dump(update)}))
        return out

    def markers(self, markers: list[PlanMarker]) -> list[PlanMarker]:
        out = []
        for m in markers:
            frame = self.frame(m.frame)
            if frame is not None:
                out.append(m.model_copy(update={"frame": frame}))
        return out

    def removals(self, removals: list[PlanRemoval]) -> list[PlanRemoval]:
        out = []
        for r in removals:
            for a, b, o in self.keep:
                lo, hi = max(r.start, a), min(r.end, b)
                if hi > lo:
                    out.append(PlanRemoval(start=lo - a + o, end=hi - a + o, kind=r.kind))
        return out


def _dump(update: dict[str, object]) -> dict[str, object]:
    """Model values -> plain data, so model_validate sees one consistent shape."""
    out: dict[str, object] = {}
    for k, v in update.items():
        if isinstance(v, list):
            out[k] = [x.model_dump() if hasattr(x, "model_dump") else x for x in v]
        elif hasattr(v, "model_dump"):
            out[k] = v.model_dump()
        else:
            out[k] = v
    return out


def _cut(
    plan: EditPlan, keep: list[Range], *, removals: list[PlanRemoval], **update: object
) -> EditPlan:
    k = _Keeper(plan, keep)
    if k.duration <= 0:
        raise ValueError("nothing left to keep")
    sequence = plan.sequence.model_copy(update={"duration_frames": k.duration})
    return EditPlan.model_validate(
        {
            **{name: getattr(plan, name) for name in type(plan).model_fields},
            "sequence": sequence,
            "video_events": k.pieces(plan.video_events),
            "video_tracks": [
                VideoTrack(index=t.index, clip_id=t.clip_id, pieces=k.pieces(t.pieces))
                for t in plan.video_tracks
            ],
            "audio_tracks": [
                AudioTrack(
                    index=t.index, clip_id=t.clip_id, gain_db=t.gain_db, pieces=k.pieces(t.pieces)
                )
                for t in plan.audio_tracks
            ],
            "overlays": k.pieces(plan.overlays),
            "markers": k.markers(plan.markers),
            "removals": removals,
            **update,
        }
    )


def slice_plan(plan: EditPlan, start: int, end: int, *, name: str | None = None) -> EditPlan:
    """Frames [start, end) of the plan as a plan of their own, starting at frame 0."""
    end = min(end, plan.sequence.duration_frames)
    if not 0 <= start < end:
        raise ValueError(f"empty range [{start}, {end})")
    k = _Keeper(plan, [(start, end)])
    seq = plan.sequence.model_copy(update={"name": name}) if name else plan.sequence
    return _cut(
        plan.model_copy(update={"sequence": seq}),
        [(start, end)],
        removals=k.removals(plan.removals),
    )


def merged_ranges(removals: list[PlanRemoval], duration: int) -> list[Range]:
    """Sorted, merged removal ranges clipped to [0, duration)."""
    spans = sorted((max(0, r.start), min(duration, r.end)) for r in removals if r.end > r.start)
    merged: list[list[int]] = []
    for a, b in spans:
        if b <= a:
            continue
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    return [(a, b) for a, b in merged]


def kept_ranges(removals: list[PlanRemoval], duration: int) -> list[Range]:
    """The complement of the removals in [0, duration)."""
    bounds = [0]
    for a, b in merged_ranges(removals, duration):
        bounds += [a, b]
    bounds.append(duration)
    # bounds = [0, a1, b1, a2, b2, ..., duration]: keep (0, a1), (b1, a2), ...
    pairs = zip(bounds[0::2], bounds[1::2], strict=True)
    return [(a, b) for a, b in pairs if b > a]


def apply_removals(
    plan: EditPlan, removals: list[PlanRemoval] | None = None, *, suffix: str = " - Jump Cuts"
) -> EditPlan:
    """Ripple-delete ``removals`` (default: the plan's approved removals) on every
    track at the same frames. Returns a plan without removals (``rippled``)."""
    todo = plan.removals if removals is None else removals
    duration = plan.sequence.duration_frames
    seq = plan.sequence.model_copy(update={"name": plan.sequence.name + suffix})
    return _cut(
        plan.model_copy(update={"sequence": seq}),
        kept_ranges(todo, duration),
        removals=[],
        rippled=True,
    )


def removed_frames(removals: list[PlanRemoval], duration: int) -> int:
    return sum(b - a for a, b in merged_ranges(removals, duration))
