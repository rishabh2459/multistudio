"""Reframe (crop centre + zoom, fractions of the source) -> host Motion keyframes.

A host places a clip at 100 % of its native size, centred. To show the crop a
``Reframe`` describes, the clip is scaled so the crop fills the sequence and moved
so the crop centre lands in the middle of the sequence::

    k     = out_w / (crop_w * src_w)          (crop_w as a fraction of the source)
    scale = 100 * k                            percent
    x     = out_w / 2 - k * (cx - 0.5) * src_w
    y     = out_h / 2 - k * (cy - 0.5) * src_h

Keys sit at the event start and at every path key inside the event, so the host's
linear interpolation draws exactly the path the render uses.
"""

from __future__ import annotations

from itertools import pairwise

from multicam_engine.editplan.model import PlanTransformKey
from multicam_engine.models.cutlist import Reframe, ReframeKey
from multicam_engine.reframe.framing import clamp_center, crop_size


def _key(
    frame: int, cx: float, cy: float, scale: float, src: tuple[int, int], out: tuple[int, int]
) -> PlanTransformKey:
    (sw, sh), (ow, oh) = src, out
    cw, ch = crop_size(sw, sh, ow, oh, scale)
    cx, cy = clamp_center(cx, cy, cw, ch)
    k = ow / (cw * sw)
    return PlanTransformKey(
        frame=frame,
        scale=round(100.0 * k, 4),
        x=round(ow / 2 - k * (cx - 0.5) * sw, 3),
        y=round(oh / 2 - k * (cy - 0.5) * sh, 3),
    )


def crop_transform(
    reframe: Reframe | None,
    src: tuple[int, int],
    out: tuple[int, int],
    start: int,
    end: int,
    *,
    always: bool = False,
) -> list[PlanTransformKey] | None:
    """Motion keys for sequence frames [start, end) of an event.

    ``None`` when no reframe is set and ``always`` is False (the host shows the clip
    as placed, the behaviour before reframing existed). With ``always`` a missing
    reframe means "fill the sequence, centred" (social clips: every size differs).
    """
    if src[0] <= 0 or src[1] <= 0:
        return None
    if reframe is None:
        if not always:
            return None
        reframe = Reframe(cx=0.5, cy=0.5, scale=1.0)
    keys = [_key(start, *reframe.center_at(start), reframe.scale, src, out)]
    for key in reframe.path or []:
        if start < key.frame < end:
            keys.append(_key(key.frame, key.cx, key.cy, reframe.scale, src, out))
    return keys


def fit_transform(
    media: tuple[int, int], out: tuple[int, int], frame: int, *, cover: bool = False
) -> list[PlanTransformKey]:
    """Scale a picture to fit inside (``cover``: fill) the sequence, centred."""
    (mw, mh), (ow, oh) = media, out
    k = max(ow / mw, oh / mh) if cover else min(ow / mw, oh / mh)
    return [PlanTransformKey(frame=frame, scale=round(100.0 * k, 4), x=ow / 2, y=oh / 2)]


def shift_reframe(reframe: Reframe | None, offset: int) -> Reframe | None:
    """The same framing on a timeline that starts ``offset`` frames later (a slice).
    Path keys before the new frame 0 collapse into one key at 0."""
    if reframe is None or not reframe.path:
        return reframe
    cx, cy = reframe.center_at(offset)
    keys = [ReframeKey(frame=0, cx=cx, cy=cy)]
    keys += [
        ReframeKey(frame=k.frame - offset, cx=k.cx, cy=k.cy)
        for k in reframe.path
        if k.frame > offset
    ]
    return Reframe(cx=cx, cy=cy, scale=reframe.scale, path=keys, manual=reframe.manual)


def transform_at(keys: list[PlanTransformKey], frame: int) -> PlanTransformKey:
    """The (linearly interpolated) transform at a frame; held outside the keys."""
    if frame <= keys[0].frame:
        return keys[0].model_copy(update={"frame": frame})
    for a, b in pairwise(keys):
        if frame <= b.frame:
            f = (frame - a.frame) / (b.frame - a.frame)
            return PlanTransformKey(
                frame=frame,
                scale=a.scale + (b.scale - a.scale) * f,
                x=a.x + (b.x - a.x) * f,
                y=a.y + (b.y - a.y) * f,
            )
    return keys[-1].model_copy(update={"frame": frame})
