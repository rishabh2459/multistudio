"""Score an automatic edit against hand-labelled "who spoke when".

Speaker accuracy = share of speech time (inside the ground truth's
``annotated_range``) during which the edit shows the right camera:

* one person speaking  -> that person's camera,
* several at once      -> any of their cameras, or the wide shot.

Phase 2 target (docs/TEST_FOOTAGE.md §6): >= 95 %, and no shot shorter than the
preset's minimum.
"""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path

import numpy as np
from pydantic import Field

from multicam_engine.analysis.vad import VadKind
from multicam_engine.benchmark.audacity import GROUND_TRUTH_FILE
from multicam_engine.benchmark.ground_truth import GroundTruth
from multicam_engine.decide.presets import params_for
from multicam_engine.models._base import StrictModel
from multicam_engine.models.cutlist import CutList
from multicam_engine.models.project import ClipRole, Preset, Project
from multicam_engine.pipeline import auto_edit, build_project
from multicam_engine.sync.engine import sync_files

TARGET_ACCURACY = 0.95
_SLOTS_PER_S = 100  # scoring resolution: 10 ms
_WIDE = "__wide__"


class SwitchAccuracy(StrictModel):
    recording_id: str
    accuracy: float = Field(ge=0.0, le=1.0)
    speech_s: float
    wide_share: float = Field(ge=0.0, le=1.0, description="Share of speech time on wide")
    segments: int
    mean_shot_s: float
    short_shots: int = Field(ge=0, description="Shots shorter than the preset minimum")

    @property
    def passed(self) -> bool:
        return self.accuracy >= TARGET_ACCURACY and self.short_shots == 0


def score_switching(
    gt: GroundTruth, cutlist: CutList, project: Project, min_shot_s: float
) -> SwitchAccuracy:
    fps = cutlist.fps.to_fraction()
    n_slots = int(cutlist.duration_frames * _SLOTS_PER_S / fps)

    who: dict[object, str] = {}
    for clip in project.clips:
        if clip.role is ClipRole.WIDE:
            who[clip.id] = _WIDE
        elif clip.speaker_label:
            who[clip.id] = clip.speaker_label

    shown = np.empty(n_slots, dtype=object)
    for seg in cutlist.segments:
        a = int(Fraction(seg.start_frame) / fps * _SLOTS_PER_S)
        b = min(n_slots, int(Fraction(seg.end_frame) / fps * _SLOTS_PER_S))
        shown[a:b] = who.get(seg.clip_id, "")

    speaking: list[set[str]] = [set() for _ in range(n_slots)]
    for turn in gt.speech:
        a = turn.start_ms * _SLOTS_PER_S // 1000
        b = min(n_slots, turn.end_ms * _SLOTS_PER_S // 1000)
        for k in range(a, b):
            speaking[k].add(turn.speaker_label)

    lo, hi = 0, n_slots
    if gt.annotated_range is not None:
        lo = gt.annotated_range.start_ms * _SLOTS_PER_S // 1000
        hi = min(n_slots, gt.annotated_range.end_ms * _SLOTS_PER_S // 1000)

    total = correct = wide = 0
    for k in range(lo, hi):
        active = speaking[k]
        if not active:
            continue
        total += 1
        on_screen = shown[k]
        wide += on_screen == _WIDE
        if on_screen in active or (len(active) > 1 and on_screen == _WIDE):
            correct += 1

    min_frames = float(min_shot_s * fps)
    segs = cutlist.segments
    short = sum(s.duration_frames < min_frames for s in segs[:-1])
    mean_shot = float(Fraction(cutlist.duration_frames) / fps) / len(segs)
    return SwitchAccuracy(
        recording_id=gt.recording_id,
        accuracy=round(correct / total, 4) if total else 0.0,
        speech_s=total / _SLOTS_PER_S,
        wide_share=round(wide / total, 4) if total else 0.0,
        segments=len(segs),
        mean_shot_s=round(mean_shot, 2),
        short_shots=short,
    )


def evaluate_switching(
    recording_dir: Path,
    *,
    preset: Preset = Preset.BALANCED,
    vad: VadKind = "auto",
    cache_dir: Path | None = None,
) -> SwitchAccuracy:
    """Sync + auto-edit a test recording folder and score it (needs ffmpeg)."""
    gt = GroundTruth.model_validate_json(
        (recording_dir / GROUND_TRUTH_FILE).read_text(encoding="utf-8")
    )
    report = sync_files(
        [recording_dir / c.file for c in gt.clips],
        reference=recording_dir / gt.reference_file,
        cache_dir=cache_dir,
    )
    project = build_project(
        report,
        name=gt.recording_id,
        roles={c.file: c.role for c in gt.clips},
        labels={c.file: c.speaker_label for c in gt.clips if c.speaker_label},
        preset=preset,
    )
    result = auto_edit(project, vad=vad, cache_dir=cache_dir)
    return score_switching(gt, result.cutlist, project, params_for(preset).min_shot_s)
