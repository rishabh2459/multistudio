"""High-level pipeline: sync report -> project -> analysis -> CutList.

report  = sync_files([...])                          # Phase 1
project = build_project(report, roles=..., labels=...)
result  = auto_edit(project)                         # Phase 2
result.cutlist                                       # -> render (Phase 3)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from multicam_engine.analysis.energy import FEATURE_RATE
from multicam_engine.analysis.speakers import (
    DetectParams,
    SpeakerActivity,
    analyze_track,
    detect_speakers,
    to_reference,
)
from multicam_engine.analysis.vad import Vad, VadKind, load_vad
from multicam_engine.decide.presets import SwitchParams, params_for
from multicam_engine.decide.switch import plan_shots, shots_to_segments
from multicam_engine.media.audio import SYNC_SAMPLE_RATE, NoAudioError, load_audio
from multicam_engine.media.probe import probe
from multicam_engine.models.cutlist import AudioConfig, CutList
from multicam_engine.models.project import (
    Clip,
    ClipRole,
    OutputSettings,
    Preset,
    Project,
)
from multicam_engine.sync.engine import SyncReport

LOW_SYNC_CONFIDENCE = 0.5


def _even(value: int) -> int:
    return max(2, value - value % 2)


def build_project(
    report: SyncReport,
    *,
    name: str = "Untitled",
    roles: dict[str, ClipRole] | None = None,
    labels: dict[str, str] | None = None,
    preset: Preset = Preset.BALANCED,
) -> Project:
    """Create a project from a sync report. ``roles`` / ``labels`` are keyed by file
    name (or full path). Clips default to speakers labelled with their file stem.
    Output settings follow the reference clip (frame rate and size)."""
    roles = roles or {}
    labels = labels or {}
    clips: list[Clip] = []
    reference_id = None
    ref_media = None
    for entry in report.clips:
        path = Path(entry.file)
        key = path.name if path.name in roles or path.name in labels else entry.file
        role = roles.get(key, ClipRole.SPEAKER)
        media = probe(path).media
        clip = Clip(
            path=str(path.resolve()),
            role=role,
            speaker_label=labels.get(key, path.stem) if role is ClipRole.SPEAKER else None,
            media=media,
        )
        if entry.is_reference:
            reference_id, ref_media = clip.id, media
        clips.append(clip)
    if reference_id is None or ref_media is None:
        raise ValueError("sync report has no reference clip")
    for clip, entry in zip(clips, report.clips, strict=True):
        clip.sync = entry.to_sync_result(reference_id)
    return Project(
        name=name,
        output=OutputSettings(
            fps=ref_media.fps, width=_even(ref_media.width), height=_even(ref_media.height)
        ),
        preset=preset,
        clips=clips,
        reference_clip_id=reference_id,
    )


@dataclass(frozen=True)
class AutoEditResult:
    cutlist: CutList
    activity: SpeakerActivity
    vad_backend: str
    warnings: list[str] = field(default_factory=list)


def auto_edit(
    project: Project,
    *,
    vad: Vad | VadKind = "auto",
    switch: SwitchParams | None = None,
    detect: DetectParams | None = None,
    cache_dir: Path | None = None,
    sample_rate: int = SYNC_SAMPLE_RATE,
) -> AutoEditResult:
    """Detect who speaks when and build the CutList for ``project``."""
    warnings: list[str] = []
    if isinstance(vad, str):
        vad, note = load_vad(vad)
        if note:
            warnings.append(note)
    params = switch or params_for(project.preset)

    if project.reference_clip_id is None:
        raise ValueError("project has no reference clip (run sync first)")
    ref = project.clip(project.reference_clip_id)
    if ref.media is None:
        raise ValueError("reference clip has no media info (probe it first)")
    duration_frames = ref.media.duration_frames
    fps = project.output.fps
    n = int(np.ceil(duration_frames * FEATURE_RATE * fps.den / fps.num))

    speakers = [c for c in project.clips if c.role is ClipRole.SPEAKER]
    wide = next((c for c in project.clips if c.role is ClipRole.WIDE), None)
    if not speakers:
        raise ValueError("project has no speaker clips")

    names, energies, vads, available = [], [], [], []
    for clip in speakers:
        label = clip.speaker_label or Path(clip.path).stem
        if clip.sync is None:
            raise ValueError(f"clip {label} is not synced")
        if clip.sync.confidence < LOW_SYNC_CONFIDENCE:
            warnings.append(f"{label}: low sync confidence ({clip.sync.confidence:.2f})")
        try:
            audio = load_audio(clip.path, sample_rate, cache_dir)
        except NoAudioError:
            warnings.append(f"{label}: no audio; this camera is only used if chosen manually")
            audio = np.zeros(0, dtype=np.float32)
        features = analyze_track(audio, sample_rate, vad) if len(audio) else None
        offset_s = clip.sync.offset_samples / clip.sync.sample_rate
        if features is None:
            energy = np.full(n, -120.0)
            prob = np.zeros(n)
            avail = np.zeros(n, dtype=bool)
        else:
            energy, prob, avail = to_reference(features, n, offset_s, clip.sync.drift_ppm)
        names.append(label)
        energies.append(energy)
        vads.append(prob)
        available.append(avail)

    activity = detect_speakers(names, energies, vads, available, detect)
    for i, label in enumerate(names):
        if activity.seconds(i) == 0 and available[i].any():
            warnings.append(f"{label}: never detected as speaking; check the camera roles")

    shots = plan_shots(activity, params, has_wide=wide is not None)
    segments = shots_to_segments(
        shots,
        analysis_rate=activity.frame_rate,
        fps=fps,
        duration_frames=duration_frames,
        speaker_clips=[c.id for c in speakers],
        wide_clip=wide.id if wide else None,
    )
    cutlist = CutList(
        project_id=project.id,
        fps=fps,
        segments=segments,
        audio=AudioConfig(
            gains_db={c.id: 0.0 for c in project.clips if c.role is not ClipRole.BROLL}
        ),
    )
    cutlist.check_against(project)
    return AutoEditResult(cutlist, activity, vad.name, warnings)
