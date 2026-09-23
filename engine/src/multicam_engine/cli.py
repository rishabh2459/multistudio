"""`multicam` command-line interface.

Phase 0 commands:
    multicam --version
    multicam validate {project,cutlist,groundtruth} FILE
    multicam gt extract-audio RECORDING_DIR
    multicam gt build RECORDING_DIR
    multicam gt check [SAMPLES_DIR]
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
from multicam_engine.models import CutList, Project

_VALIDATE_KINDS: dict[str, type[BaseModel]] = {
    "project": Project,
    "cutlist": CutList,
    "groundtruth": GroundTruth,
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="multicam", description="Multicam Studio engine CLI")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_val = sub.add_parser("validate", help="validate a JSON file against the data model")
    p_val.add_argument("kind", choices=sorted(_VALIDATE_KINDS))
    p_val.add_argument("file")
    p_val.set_defaults(func=_cmd_validate)

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

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    sys.exit(main())
