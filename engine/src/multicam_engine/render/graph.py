"""Build the ffmpeg command for one chunk of the edit (video only).

Per segment (a ``VideoPiece``) the filter chain is:

    setpts   retime: t_out = (pts - source_pts) / speed     (drift correction)
    fps      constant frame rate at the project rate; each output frame takes the
             source frame nearest in time (VFR phone footage becomes CFR here)
    trim     exactly ``covered`` frames ...
    tpad     ... padded by cloning if the source ended early, trimmed again, so the
             count is exact no matter what the source does
    scale    fit into the output size (letterbox if the aspect differs)
    tpad     black frames where the camera was not recording (head / tail)

All segments of the chunk are joined with ``concat`` in one ``filter_complex``,
so every cut lands on its exact output frame and nothing is stream-copied.
Inputs are opened with ``-copyts`` so timestamps are the file's own, and seeked
to 3 s before they are needed (fast, still frame-accurate because we trim).
"""

from __future__ import annotations

from fractions import Fraction
from itertools import pairwise
from pathlib import Path

from multicam_engine.models.cutlist import Reframe
from multicam_engine.render.plan import RenderPlan, VideoPiece

SEEK_MARGIN_S = 3


def _dec(value: Fraction) -> str:
    """Fixed-point decimal for ffmpeg (1 ns resolution is far below a frame)."""
    return f"{float(value):.9f}"


def _rate(value: Fraction) -> str:
    return f"{value.numerator}/{value.denominator}"


def _lerp_expr(values: list[tuple[float, float]]) -> str:
    """ffmpeg expression of t: piecewise-linear through (time, value) points."""
    if len(values) == 1:
        return f"{values[0][1]:.6f}"
    expr = f"{values[-1][1]:.6f}"
    for (t0, v0), (t1, v1) in reversed(list(pairwise(values))):
        slope = (v1 - v0) / (t1 - t0) if t1 > t0 else 0.0
        expr = f"if(lt(t,{t1:.4f}),{v0:.6f}+({slope:.8f})*(t-{t0:.4f}),{expr})"
    return f"if(lt(t,{values[0][0]:.4f}),{values[0][1]:.6f},{expr})"


def _crop(width: int, height: int, reframe: Reframe, first_frame: int, fps: Fraction) -> str:
    """Crop with the output's aspect ratio (zoomed by ``scale``), centred on the
    reframe point or following its keyframes (t = seconds since the piece start)."""
    aspect = f"{width / height:.6f}"
    s = f"{reframe.scale:.6f}"
    w = f"min(iw,ih*{aspect})/{s}"
    h = f"min(ih,iw/{aspect})/{s}"
    if reframe.path:
        keys = [(float((k.frame - first_frame) / fps), k.cx, k.cy) for k in reframe.path]
        cx = _lerp_expr([(t, x) for t, x, _ in keys])
        cy = _lerp_expr([(t, y) for t, _, y in keys])
    else:
        cx, cy = f"{reframe.cx:.6f}", f"{reframe.cy:.6f}"
    return f"crop=w='{w}':h='{h}':x='clip(({cx})*iw-ow/2,0,iw-ow)':y='clip(({cy})*ih-oh/2,0,ih-oh)'"


def _fit(
    width: int,
    height: int,
    reframe: Reframe | None,
    first_frame: int = 0,
    fps: Fraction = Fraction(30),
) -> str:
    steps = [] if reframe is None else [_crop(width, height, reframe, first_frame, fps)]
    steps += [
        f"scale={width}:{height}:force_original_aspect_ratio=decrease:flags=lanczos",
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black",
        "setsar=1",
        "format=yuv420p",
    ]
    return ",".join(steps)


def piece_filter(
    piece: VideoPiece, input_label: str | None, plan: RenderPlan, out_label: str
) -> str:
    rate = _rate(plan.fps)
    size = f"{plan.width}x{plan.height}"
    if piece.is_black or input_label is None or piece.source_pts is None:
        return (
            f"color=c=black:s={size}:r={rate},trim=end_frame={piece.frames},"
            f"setsar=1,format=yuv420p,setpts=PTS-STARTPTS[{out_label}]"
        )
    c = piece.covered
    fit = _fit(
        plan.width, plan.height, piece.reframe, piece.start_frame + piece.head_black, plan.fps
    )
    return (
        f"[{input_label}]"
        f"setpts='(PTS*TB-{_dec(piece.source_pts)})/{_dec(piece.speed)}/TB',"
        f"fps={rate}:start_time=0:round=near,"
        f"trim=end_frame={c},tpad=stop=-1:stop_mode=clone,trim=end_frame={c},"
        f"{fit},"
        f"tpad=start={piece.head_black}:stop={piece.tail_black}:"
        f"start_mode=add:stop_mode=add:color=black,"
        f"setpts=PTS-STARTPTS[{out_label}]"
    )


def chunk_command(
    plan: RenderPlan,
    chunk: list[int],
    output: Path,
    video_args: list[str],
) -> list[str]:
    """ffmpeg arguments (without the executable) rendering ``chunk`` to ``output``."""
    args: list[str] = ["-loglevel", "error", "-y", "-copyts"]
    filters: list[str] = []
    labels: list[str] = []
    n_inputs = 0
    frames = 0
    for k, idx in enumerate(chunk):
        piece = plan.pieces[idx]
        label = None
        if not piece.is_black and piece.path is not None and piece.source_pts is not None:
            seek = max(Fraction(0), piece.source_pts - SEEK_MARGIN_S)
            args += ["-ss", _dec(seek), "-i", str(piece.path)]
            label = f"{n_inputs}:v:0"
            n_inputs += 1
        filters.append(piece_filter(piece, label, plan, f"p{k}"))
        labels.append(f"[p{k}]")
        frames += piece.frames
    filters.append(f"{''.join(labels)}concat=n={len(labels)}:v=1:a=0[vout]")
    args += [
        "-filter_complex", ";".join(filters),
        "-map", "[vout]",
        "-an", "-sn", "-dn",
        *video_args,
        "-pix_fmt", "yuv420p",
        "-fps_mode", "passthrough",
        "-frames:v", str(frames),
        "-progress", "pipe:1", "-nostats",
        str(output),
    ]  # fmt: skip
    return args
