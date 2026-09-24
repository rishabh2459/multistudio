"""`multicam` command-line interface.

Commands:
    multicam --version
    multicam validate {project,cutlist,groundtruth,sync} FILE
    multicam probe FILE...                          (Phase 1)
    multicam sync FILE FILE... [--reference F] [--out sync.json]   (Phase 1)
    multicam gt extract-audio RECORDING_DIR
    multicam gt build RECORDING_DIR
    multicam gt check [SAMPLES_DIR]
    multicam gt eval-sync RECORDING_DIR...          (Phase 1)
    multicam cutlist --sync sync.json [--wide F] [--label F=NAME] [--preset P]  (Phase 2)
    multicam gt eval-switch RECORDING_DIR... [--preset P]                     (Phase 2)
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel, ValidationError

from multicam_engine import __version__
from multicam_engine.benchmark.audacity import (
    GROUND_TRUTH_FILE,
    GroundTruthBuildError,
    build_from_folder,
)
from multicam_engine.benchmark.audio import extract_wavs
from multicam_engine.benchmark.ground_truth import GroundTruth
from multicam_engine.benchmark.switch_accuracy import TARGET_ACCURACY, evaluate_switching
from multicam_engine.benchmark.sync_accuracy import evaluate_recording
from multicam_engine.media.audio import SYNC_SAMPLE_RATE, default_cache_dir
from multicam_engine.media.ffmpeg import FFmpegNotFoundError
from multicam_engine.media.probe import ProbeError, probe
from multicam_engine.models import CutList, Project
from multicam_engine.models.project import ClipRole, Preset
from multicam_engine.pipeline import auto_edit, build_project
from multicam_engine.sync.engine import SyncReport, sync_files

_VALIDATE_KINDS: dict[str, type[BaseModel]] = {
    "project": Project,
    "cutlist": CutList,
    "groundtruth": GroundTruth,
    "sync": SyncReport,
}


def _err(msg: str) -> int:
    print(f"error: {msg}", file=sys.stderr)
    return 1


def _cmd_validate(args: argparse.Namespace) -> int:
    model = _VALIDATE_KINDS[args.kind]
    path = Path(args.file)
    try:
        model.model_validate_json(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return _err(f"file not found: {path}")
    except ValidationError as exc:
        return _err(f"{path} is not a valid {args.kind}:\n{exc}")
    print(f"ok: {path} is a valid {args.kind}")
    return 0


def _cmd_gt_extract_audio(args: argparse.Namespace) -> int:
    try:
        wavs = extract_wavs(Path(args.recording_dir))
    except (RuntimeError, FileNotFoundError) as exc:
        return _err(str(exc))
    for w in wavs:
        print(f"wrote {w}")
    print("Next: open these WAVs in Audacity and add labels (docs/TEST_FOOTAGE.md).")
    return 0


def _cmd_gt_build(args: argparse.Namespace) -> int:
    rec = Path(args.recording_dir)
    try:
        gt = build_from_folder(rec)
    except GroundTruthBuildError as exc:
        return _err(str(exc))
    out = rec / GROUND_TRUTH_FILE
    out.write_text(gt.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out}")
    _print_summary(gt)
    return 0


def _print_summary(gt: GroundTruth) -> None:
    print(f"  {gt.recording_id}: {gt.description or '(no description)'}")
    for clip in gt.clips:
        ref = " (reference)" if clip.file == gt.reference_file else ""
        drift = gt.true_drift_ppm(clip.file)
        drift_s = "n/a" if drift is None else f"{drift:+.1f} ppm"
        print(
            f"    {clip.file:<24} offset {gt.true_offset_ms(clip.file):+8d} ms"
            f"   drift {drift_s}{ref}"
        )
    print(f"    speech turns: {len(gt.speech)}")


def _cmd_gt_check(args: argparse.Namespace) -> int:
    root = Path(args.samples_dir)
    files = sorted(root.glob(f"*/{GROUND_TRUTH_FILE}"))
    if not files:
        return _err(f"no */{GROUND_TRUTH_FILE} found under {root}")
    failures = 0
    for path in files:
        try:
            gt = GroundTruth.model_validate_json(path.read_text(encoding="utf-8"))
        except ValidationError as exc:
            failures += 1
            print(f"FAIL {path}\n{exc}", file=sys.stderr)
            continue
        missing = [c.file for c in gt.clips if not (path.parent / c.file).is_file()]
        if missing:
            failures += 1
            print(f"FAIL {path}: missing media files {missing}", file=sys.stderr)
            continue
        print(f"ok   {path}")
        _print_summary(gt)
    print(f"\n{len(files) - failures}/{len(files)} recordings valid")
    return 1 if failures else 0


def _cmd_probe(args: argparse.Namespace) -> int:
    status = 0
    for file in args.files:
        try:
            result = probe(file)
        except (ProbeError, FFmpegNotFoundError) as exc:
            status = _err(str(exc))
            continue
        m = result.media
        if args.json:
            print(m.model_dump_json(indent=2))
            continue
        vfr = "VFR" if m.is_vfr else "CFR"
        audio = (
            f"{m.audio_codec} {m.audio_sample_rate} Hz x{m.audio_channels}"
            if m.audio_codec
            else "no audio"
        )
        print(
            f"{file}: {m.width}x{m.height} {m.video_codec} {m.fps} fps ({vfr}), "
            f"{m.duration_frames} frames ({float(result.duration):.2f} s), {audio}"
        )
    return status


def _cmd_sync(args: argparse.Namespace) -> int:
    cache = None if args.no_cache else (Path(args.cache_dir) if args.cache_dir else None)
    if cache is None and not args.no_cache:
        cache = default_cache_dir()
    try:
        report = sync_files(
            args.files,
            reference=args.reference,
            sample_rate=args.sample_rate,
            cache_dir=cache,
            on_progress=(lambda msg: print(f"  {msg}", file=sys.stderr)),
        )
    except (FileNotFoundError, FFmpegNotFoundError, ValueError) as exc:
        return _err(str(exc))

    print(f"reference: {report.reference_file}")
    for c in report.clips:
        if c.is_reference:
            continue
        print(
            f"  {c.file:<32} offset {c.offset_seconds * 1000:+10.2f} ms  "
            f"drift {c.drift_ppm:+8.2f} ppm  confidence {c.confidence:.2f}  "
            f"windows {c.windows_used}/{c.windows_total}"
        )
    for c in report.clips:
        for w in c.warnings:
            print(f"warning: {Path(c.file).name}: {w}", file=sys.stderr)
    if args.out:
        out = Path(args.out)
        out.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
        print(f"wrote {out}")
    return 0


def _cmd_gt_eval_sync(args: argparse.Namespace) -> int:
    failures = 0
    for rec in args.recording_dirs:
        try:
            acc = evaluate_recording(Path(rec), cache_dir=default_cache_dir())
        except (FileNotFoundError, ValidationError, FFmpegNotFoundError, ProbeError) as exc:
            failures += 1
            print(f"FAIL {rec}: {exc}", file=sys.stderr)
            continue
        print(f"{acc.recording_id}:")
        for c in acc.clips:
            end = "n/a" if c.end_error_ms is None else f"{c.end_error_ms:+.2f} ms"
            truth = "n/a" if c.true_drift_ppm is None else f"{c.true_drift_ppm:+.1f}"
            verdict = "ok  " if c.within_one_frame else "FAIL"
            print(
                f"  {verdict} {c.file:<24} start {c.start_error_ms:+.2f} ms  end {end}  "
                f"drift {c.measured_drift_ppm:+.1f} ppm (true {truth})  conf {c.confidence:.2f}"
            )
        failures += 0 if acc.passed else 1
    return 1 if failures else 0


def _parse_labels(items: list[str]) -> dict[str, str]:
    labels: dict[str, str] = {}
    for item in items:
        file, sep, name = item.partition("=")
        if not sep or not file or not name:
            raise ValueError(f"--label must look like FILE=NAME, got {item!r}")
        labels[Path(file).name] = name
    return labels


def _cmd_cutlist(args: argparse.Namespace) -> int:
    try:
        report = SyncReport.model_validate_json(Path(args.sync).read_text(encoding="utf-8"))
        roles = {Path(f).name: ClipRole.WIDE for f in args.wide}
        roles.update({Path(f).name: ClipRole.BROLL for f in args.broll})
        project = build_project(
            report,
            name=args.name,
            roles=roles,
            labels=_parse_labels(args.label),
            preset=Preset(args.preset),
        )
        result = auto_edit(project, vad=args.vad, cache_dir=default_cache_dir())
    except FileNotFoundError as exc:
        return _err(f"file not found: {exc}")
    except (ValidationError, ValueError, ProbeError, FFmpegNotFoundError) as exc:
        return _err(str(exc))

    cutlist = result.cutlist
    fps = cutlist.fps.to_fraction()
    names = {c.id: (c.speaker_label or c.role.value) for c in project.clips}
    total = cutlist.duration_frames
    print(
        f"preset {project.preset.value}, VAD {result.vad_backend}: "
        f"{len(cutlist.segments)} shots, average {float(total / fps) / len(cutlist.segments):.1f} s"
    )
    share: dict[str, int] = {}
    for seg in cutlist.segments:
        share[names[seg.clip_id]] = share.get(names[seg.clip_id], 0) + seg.duration_frames
    for name, frames in sorted(share.items(), key=lambda kv: -kv[1]):
        print(f"  {name:<20} {frames / total:6.1%}  ({float(frames / fps):.1f} s)")
    for w in result.warnings:
        print(f"warning: {w}", file=sys.stderr)

    out = Path(args.out)
    out.write_text(cutlist.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out}")
    project_out = Path(args.project_out) if args.project_out else out.with_name("project.json")
    project_out.write_text(project.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(f"wrote {project_out}")
    return 0


def _cmd_gt_eval_switch(args: argparse.Namespace) -> int:
    failures = 0
    for rec in args.recording_dirs:
        try:
            acc = evaluate_switching(
                Path(rec), preset=Preset(args.preset), vad=args.vad, cache_dir=default_cache_dir()
            )
        except (FileNotFoundError, ValidationError, ValueError, ProbeError) as exc:
            failures += 1
            print(f"FAIL {rec}: {exc}", file=sys.stderr)
            continue
        verdict = "ok  " if acc.passed else "FAIL"
        print(
            f"{verdict} {acc.recording_id}: speaker accuracy {acc.accuracy:.1%} "
            f"(target {TARGET_ACCURACY:.0%}) over {acc.speech_s:.0f} s of speech, "
            f"{acc.segments} shots (avg {acc.mean_shot_s:.1f} s), "
            f"short shots {acc.short_shots}, wide {acc.wide_share:.0%}"
        )
        failures += 0 if acc.passed else 1
    return 1 if failures else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="multicam", description="Multicam Studio engine CLI")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_val = sub.add_parser("validate", help="validate a JSON file against the data model")
    p_val.add_argument("kind", choices=sorted(_VALIDATE_KINDS))
    p_val.add_argument("file")
    p_val.set_defaults(func=_cmd_validate)

    p_probe = sub.add_parser("probe", help="show frame rate, VFR, duration and audio of files")
    p_probe.add_argument("files", nargs="+")
    p_probe.add_argument("--json", action="store_true", help="print MediaInfo JSON")
    p_probe.set_defaults(func=_cmd_probe)

    p_sync = sub.add_parser("sync", help="sync clips by their audio")
    p_sync.add_argument("files", nargs="+", help="two or more media files")
    p_sync.add_argument("--reference", help="clip to align the others to (default: first)")
    p_sync.add_argument("--out", help="write the sync report (JSON) here")
    p_sync.add_argument("--sample-rate", type=int, default=SYNC_SAMPLE_RATE)
    p_sync.add_argument("--cache-dir", help="decoded-audio cache (default: user cache folder)")
    p_sync.add_argument("--no-cache", action="store_true", help="do not cache decoded audio")
    p_sync.set_defaults(func=_cmd_sync)

    presets = [p.value for p in Preset]
    vads = ["auto", "silero", "energy"]
    p_cut = sub.add_parser("cutlist", help="auto-edit: who speaks when -> camera cuts")
    p_cut.add_argument("--sync", required=True, help="sync report from `multicam sync --out`")
    p_cut.add_argument("--wide", action="append", default=[], help="a wide camera (repeatable)")
    p_cut.add_argument("--broll", action="append", default=[], help="never auto-selected")
    p_cut.add_argument("--label", action="append", default=[], help="FILE=NAME (repeatable)")
    p_cut.add_argument("--preset", choices=presets, default=Preset.BALANCED.value)
    p_cut.add_argument("--vad", choices=vads, default="auto")
    p_cut.add_argument("--name", default="Untitled", help="project name")
    p_cut.add_argument("--out", default="cutlist.json")
    p_cut.add_argument("--project-out", help="default: project.json next to --out")
    p_cut.set_defaults(func=_cmd_cutlist)

    p_gt = sub.add_parser("gt", help="ground-truth tools for test footage")
    gt_sub = p_gt.add_subparsers(dest="gt_command", required=True)

    p_audio = gt_sub.add_parser("extract-audio", help="write WAVs for labeling in Audacity")
    p_audio.add_argument("recording_dir")
    p_audio.set_defaults(func=_cmd_gt_extract_audio)

    p_build = gt_sub.add_parser("build", help="meta.json + labels.txt -> ground_truth.json")
    p_build.add_argument("recording_dir")
    p_build.set_defaults(func=_cmd_gt_build)

    p_check = gt_sub.add_parser("check", help="validate all ground_truth.json files")
    p_check.add_argument("samples_dir", nargs="?", default="samples")
    p_check.set_defaults(func=_cmd_gt_check)

    p_eval = gt_sub.add_parser("eval-sync", help="run sync and score it against ground truth")
    p_eval.add_argument("recording_dirs", nargs="+")
    p_eval.set_defaults(func=_cmd_gt_eval_sync)

    p_esw = gt_sub.add_parser("eval-switch", help="auto-edit and score speaker accuracy")
    p_esw.add_argument("recording_dirs", nargs="+")
    p_esw.add_argument("--preset", choices=presets, default=Preset.BALANCED.value)
    p_esw.add_argument("--vad", choices=vads, default="auto")
    p_esw.set_defaults(func=_cmd_gt_eval_switch)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    sys.exit(main())
