"""Time the auto-edit pipeline on a real recording (PLUGIN_PLAN Section 7.1 / PL0).

Stages timed separately: decode (all mics), sync, analyze (VAD + energy), and
decide (once per preset; this is what a re-cut with a new preset costs).

Video files go through ``build_project`` (ffprobe). Audio-only files (``.wav``)
are accepted too, for timing on extracted tracks: then pass ``--fps`` and the
clips get a synthetic 1920x1080 picture.

Usage:
    uv run python scripts/bench_pipeline.py host.mov:speaker guest.mov:speaker wide.mov:wide
    uv run python scripts/bench_pipeline.py a.wav:speaker b.wav:speaker w.wav:wide --fps 30
    ... --json out.json   # also write the numbers
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
import wave
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from multicam_engine.analysis.vad import load_vad
from multicam_engine.decide.presets import params_for
from multicam_engine.media.audio import SYNC_SAMPLE_RATE, load_audio
from multicam_engine.models.project import (
    Clip,
    ClipRole,
    MediaInfo,
    OutputSettings,
    Preset,
    Project,
)
from multicam_engine.models.time import Rational
from multicam_engine.pipeline import analyze_project, build_project, cutlist_from_analysis
from multicam_engine.sync import sync_files


def _parse_clip(spec: str) -> tuple[Path, ClipRole]:
    path, _, role = spec.rpartition(":")
    if not path:
        return Path(spec), ClipRole.SPEAKER
    return Path(path), ClipRole(role)


def _wav_media(path: Path, fps: Rational) -> MediaInfo:
    with wave.open(str(path)) as w:
        seconds = w.getnframes() / w.getframerate()
        rate, channels = w.getframerate(), w.getnchannels()
    return MediaInfo(
        fps=fps,
        is_vfr=False,
        duration_frames=int(seconds * fps.num / fps.den),
        width=1920,
        height=1080,
        video_codec="none",
        audio_codec="pcm_s16le",
        audio_sample_rate=rate,
        audio_channels=channels,
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("clips", nargs="+", help="path[:speaker|wide|broll]")
    ap.add_argument("--fps", default="30", help="frame rate for audio-only inputs, e.g. 30000/1001")
    ap.add_argument("--vad", default="auto", choices=["auto", "silero", "energy"])
    ap.add_argument("--json", type=Path, help="write the timings here")
    args = ap.parse_args(argv)

    specs = [_parse_clip(s) for s in args.clips]
    num, _, den = args.fps.partition("/")
    fps = Rational(num=int(num), den=int(den or 1))
    timings: dict[str, Any] = {}

    with tempfile.TemporaryDirectory() as tmp:
        cache = Path(tmp)
        t0 = time.perf_counter()
        with ThreadPoolExecutor(max_workers=len(specs)) as pool:
            list(pool.map(lambda s: load_audio(s[0], SYNC_SAMPLE_RATE, cache), specs))
        timings["decode_s"] = time.perf_counter() - t0

        t0 = time.perf_counter()
        report = sync_files([p for p, _ in specs], cache_dir=cache)
        timings["sync_s"] = time.perf_counter() - t0
        timings["sync"] = [
            {"file": Path(c.file).name, "offset_s": c.offset_seconds, "confidence": c.confidence}
            for c in report.clips
        ]

        roles = {p.name: r for p, r in specs}
        if all(p.suffix.lower() == ".wav" for p, _ in specs):
            clips = [
                Clip(
                    path=str(p.resolve()),
                    role=r,
                    speaker_label=p.stem if r is ClipRole.SPEAKER else None,
                    media=_wav_media(p, fps),
                )
                for p, r in specs
            ]
            by_file = {c.path: c for c in clips}
            ref = next(c for c in report.clips if c.is_reference)
            ref_id = by_file[str(Path(ref.file).resolve())].id
            for entry in report.clips:
                by_file[str(Path(entry.file).resolve())].sync = entry.to_sync_result(ref_id)
            project = Project(
                name="bench",
                output=OutputSettings(fps=fps, width=1920, height=1080),
                clips=clips,
                reference_clip_id=ref_id,
            )
        else:
            project = build_project(report, roles=roles)

        vad, note = load_vad(args.vad)
        t0 = time.perf_counter()
        analysis = analyze_project(project, vad=vad, cache_dir=cache)
        timings["analyze_s"] = time.perf_counter() - t0
        timings["vad"] = vad.name + (f" ({note})" if note else "")
        timings["warnings"] = analysis.warnings

        timings["decide"] = {}
        for preset in Preset:
            t0 = time.perf_counter()
            cutlist = cutlist_from_analysis(project, analysis, params_for(preset))
            elapsed = time.perf_counter() - t0
            lengths = [s.duration_frames for s in cutlist.segments]
            timings["decide"][preset.value] = {
                "seconds": round(elapsed, 3),
                "cuts": len(cutlist.segments) - 1,
                "mean_shot_s": round(sum(lengths) / len(lengths) * fps.den / fps.num, 2),
            }

    duration_s = (project.clips[0].media.duration_frames if project.clips[0].media else 0) / (
        fps.num / fps.den
    )
    timings["duration_s"] = round(duration_s, 1)
    for key in ("decode_s", "sync_s", "analyze_s"):
        timings[key] = round(timings[key], 2)
    print(json.dumps(timings, indent=2))
    if args.json:
        args.json.write_text(json.dumps(timings, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
