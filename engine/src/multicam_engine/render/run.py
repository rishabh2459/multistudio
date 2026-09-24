"""Render a CutList to a finished video file.

Steps (with progress + ETA reported throughout, and cancellable at any time):

1. probe every clip used and build the exact ``RenderPlan``
2. master audio: one continuous mix, encoded to AAC            (~10 % of the work)
3. video: the edit in chunks (<= 5 min / 24 cuts each), every chunk one ffmpeg
   run with one filter graph, encoded with the chosen encoder  (~85 %)
4. join: chunks are concatenated *without re-encoding* (they share settings and
   each starts on a keyframe) and muxed with the audio; frame count verified (~5 %)

Chunking keeps filter graphs small for 3-hour recordings with hundreds of cuts,
and the join is lossless, so the result is identical to a single-pass render.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID

from multicam_engine.media.ffmpeg import FFmpegError, find_tool, run_tool
from multicam_engine.media.probe import ProbeResult, probe
from multicam_engine.models.cutlist import AudioMode, CutList
from multicam_engine.models.project import Project
from multicam_engine.render.audio import RenderCancelledError, mix_master_audio
from multicam_engine.render.encoders import PRESETS, OutputPreset, choose_encoder, encoder_args
from multicam_engine.render.graph import chunk_command
from multicam_engine.render.plan import RenderPlan, build_plan

_W_AUDIO, _W_VIDEO, _W_JOIN = 0.10, 0.85, 0.05


@dataclass(frozen=True)
class RenderProgress:
    stage: str  # "audio" | "video" | "join" | "done"
    fraction: float  # overall 0..1
    frames_done: int
    total_frames: int
    eta_s: float | None


@dataclass(frozen=True)
class RenderResult:
    output: Path
    encoder: str
    codec: str
    frames: int
    duration_s: float
    elapsed_s: float
    warnings: list[str] = field(default_factory=list)


class _Progress:
    def __init__(self, total_frames: int, callback: Callable[[RenderProgress], None] | None):
        self.total = total_frames
        self.callback = callback
        self.t0 = time.monotonic()
        self.frames = 0

    def report(self, stage: str, fraction: float) -> None:
        if self.callback is None:
            return
        fraction = min(1.0, max(0.0, fraction))
        elapsed = time.monotonic() - self.t0
        eta = elapsed * (1 - fraction) / fraction if fraction > 0.02 else None
        self.callback(RenderProgress(stage, fraction, self.frames, self.total, eta))


def _check_cancel(cancel: threading.Event | None) -> None:
    if cancel is not None and cancel.is_set():
        raise RenderCancelledError("render cancelled")


def _run_with_progress(
    args: list[str],
    on_frame: Callable[[int], None],
    cancel: threading.Event | None,
) -> None:
    """Run ffmpeg with ``-progress pipe:1``; report frames; kill it on cancel."""
    with tempfile.TemporaryFile() as err:
        proc = subprocess.Popen(
            [find_tool("ffmpeg"), "-hide_banner", "-nostdin", *args],
            stdout=subprocess.PIPE, stderr=err, text=True,
        )  # fmt: skip
        assert proc.stdout is not None
        try:
            for line in proc.stdout:
                if cancel is not None and cancel.is_set():
                    proc.kill()
                    raise RenderCancelledError("render cancelled")
                key, _, value = line.strip().partition("=")
                if key == "frame" and value.isdigit():
                    on_frame(int(value))
            code = proc.wait()
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
        if code != 0:
            err.seek(0)
            raise FFmpegError(f"ffmpeg failed (exit {code})", err.read().decode(errors="replace"))


def count_video_frames(path: Path) -> int:
    out = run_tool(
        "ffprobe",
        ["-v", "error", "-select_streams", "v:0", "-count_packets",
         "-show_entries", "stream=nb_read_packets", "-of", "csv=p=0", str(path)],
    )  # fmt: skip
    return int(out.decode().strip().rstrip(",") or 0)


def probe_clips(project: Project, cutlist: CutList) -> dict[UUID, ProbeResult]:
    used = {s.clip_id for s in cutlist.segments} | set(cutlist.audio.gains_db)
    if cutlist.audio.mode is AudioMode.SINGLE and cutlist.audio.single_clip_id:
        used.add(cutlist.audio.single_clip_id)
    return {clip_id: probe(project.clip(clip_id).path) for clip_id in used}


def render(
    project: Project,
    cutlist: CutList,
    output: str | Path,
    *,
    preset: str | OutputPreset = "youtube-1080p",
    encoder: str = "auto",
    on_progress: Callable[[RenderProgress], None] | None = None,
    cancel: threading.Event | None = None,
    chunk_seconds: float = 300.0,
    max_pieces_per_chunk: int = 24,
    probes: dict[UUID, ProbeResult] | None = None,
    keep_temp: bool = False,
) -> RenderResult:
    output = Path(output)
    out_preset = PRESETS[preset] if isinstance(preset, str) else preset
    started = time.monotonic()

    plan: RenderPlan = build_plan(
        project,
        cutlist,
        probes if probes is not None else probe_clips(project, cutlist),
        width=out_preset.width,
        height=out_preset.height,
        chunk_seconds=chunk_seconds,
        max_pieces_per_chunk=max_pieces_per_chunk,
    )
    warnings = list(plan.warnings)
    enc, codec = choose_encoder(out_preset.codec, encoder)
    if codec != out_preset.codec:
        warnings.append(f"no working {out_preset.codec} encoder; using {codec} ({enc})")
    video_args = [
        "-c:v",
        enc,
        *encoder_args(enc, out_preset.video_kbps, float(plan.fps), fast=out_preset.fast),
    ]

    progress = _Progress(plan.total_frames, on_progress)
    output.parent.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=f".{output.stem}.render-", dir=output.parent))
    try:
        # 2) audio
        audio_file = work / "audio.m4a" if plan.audio else None
        if audio_file is not None:
            clipped = mix_master_audio(
                plan.audio,
                plan.duration,
                audio_file,
                audio_kbps=out_preset.audio_kbps,
                on_progress=lambda f: progress.report("audio", _W_AUDIO * f),
                cancel=cancel,
            )
            if clipped:
                warnings.append(
                    f"audio mix clipped {clipped} samples; lower the clip gains or use one mic"
                )
        progress.report("audio", _W_AUDIO)

        # 3) video chunks
        chunk_files: list[Path] = []
        done_before = 0
        for n, chunk in enumerate(plan.chunks):
            _check_cancel(cancel)
            part = work / f"part{n:04d}.mkv"
            chunk_frames = sum(plan.pieces[i].frames for i in chunk)

            def on_frame(frame: int, base: int = done_before) -> None:
                progress.frames = base + frame
                progress.report("video", _W_AUDIO + _W_VIDEO * progress.frames / plan.total_frames)

            _run_with_progress(chunk_command(plan, chunk, part, video_args), on_frame, cancel)
            done_before += chunk_frames
            chunk_files.append(part)

        # 4) join without re-encoding + mux audio
        _check_cancel(cancel)
        progress.report("join", _W_AUDIO + _W_VIDEO)
        listing = work / "parts.txt"
        listing.write_text("".join(f"file '{p.name}'\n" for p in chunk_files), encoding="utf-8")
        tmp_out = work / f"final{output.suffix or '.mp4'}"
        args = ["-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(listing)]
        if audio_file is not None:
            args += ["-i", str(audio_file), "-map", "0:v:0", "-map", "1:a:0"]
        else:
            args += ["-map", "0:v:0"]
        args += ["-c", "copy"]
        if (output.suffix or ".mp4").lower() in (".mp4", ".mov", ".m4v"):
            args += ["-movflags", "+faststart"]
            if codec == "hevc":
                args += ["-tag:v", "hvc1"]  # plays in QuickTime / Apple devices
        args += ["-progress", "pipe:1", "-nostats", str(tmp_out)]
        _run_with_progress(args, lambda _f: None, cancel)

        frames = count_video_frames(tmp_out)
        if frames != plan.total_frames:
            warnings.append(f"expected {plan.total_frames} frames, output has {frames}")
        tmp_out.replace(output)
        progress.frames = plan.total_frames
        progress.report("done", 1.0)
    finally:
        if not keep_temp:
            shutil.rmtree(work, ignore_errors=True)

    return RenderResult(
        output=output,
        encoder=enc,
        codec=codec,
        frames=plan.total_frames,
        duration_s=float(plan.duration),
        elapsed_s=round(time.monotonic() - started, 2),
        warnings=warnings,
    )
