"""High-level pipeline: sync report -> project -> analysis -> CutList.

report  = sync_files([...])                          # Phase 1
project = build_project(report, roles=..., labels=...)
result  = auto_edit(project)                         # Phase 2
result.cutlist                                       # -> render (Phase 3)
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID

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


@dataclass(frozen=True)
class Analysis:
    """Who speaks when, for a project (the expensive half of auto-editing)."""

    activity: SpeakerActivity
    speaker_clip_ids: list[UUID]
    vad_backend: str
    warnings: list[str] = field(default_factory=list)

    def save(self, path: Path) -> None:
        """Store as ``.npz`` so a new preset can re-cut without re-analysing."""
        a = self.activity
        with path.open("wb") as fh:
            np.savez_compressed(
                fh,
                labels=a.labels,
                margin_db=a.margin_db,
                available=a.available,
                speakers=np.array(a.speakers, dtype=str),
                speaker_clip_ids=np.array([str(c) for c in self.speaker_clip_ids], dtype=str),
                frame_rate=np.array(a.frame_rate),
                vad_backend=np.array(self.vad_backend),
                warnings=np.array(self.warnings, dtype=str),
            )

    @classmethod
    def load(cls, path: Path) -> Analysis:
        with np.load(path, allow_pickle=False) as data:
            activity = SpeakerActivity(
                labels=data["labels"].astype(np.int64),
                speakers=tuple(str(s) for s in data["speakers"]),
                margin_db=data["margin_db"].astype(np.float64),
                available=data["available"].astype(bool),
                frame_rate=int(data["frame_rate"]),
            )
            return cls(
                activity=activity,
                speaker_clip_ids=[UUID(str(c)) for c in data["speaker_clip_ids"]],
                vad_backend=str(data["vad_backend"]),
                warnings=[str(w) for w in data["warnings"]],
            )


def _timeline_frames(project: Project) -> tuple[int, int]:
    """(output frames, analysis frames) of the reference clip."""
    if project.reference_clip_id is None:
        raise ValueError("project has no reference clip (run sync first)")
    ref = project.clip(project.reference_clip_id)
    if ref.media is None:
        raise ValueError("reference clip has no media info (probe it first)")
    duration_frames = ref.media.duration_frames
    fps = project.output.fps
    return duration_frames, int(np.ceil(duration_frames * FEATURE_RATE * fps.den / fps.num))


def analyze_project(
    project: Project,
    *,
    vad: Vad | VadKind = "auto",
    detect: DetectParams | None = None,
    cache_dir: Path | None = None,
    sample_rate: int = SYNC_SAMPLE_RATE,
    on_progress: Callable[[float], None] | None = None,
) -> Analysis:
    """Measure loudness + speech on every speaker mic and label who speaks when."""
    warnings: list[str] = []
    if isinstance(vad, str):
        vad, note = load_vad(vad)
        if note:
            warnings.append(note)
    _, n = _timeline_frames(project)
    speakers = [c for c in project.clips if c.role is ClipRole.SPEAKER]
    if not speakers:
        raise ValueError("project has no speaker clips")

    names, energies, vads, available = [], [], [], []
    for k, clip in enumerate(speakers):
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
        if on_progress:
            on_progress((k + 1) / len(speakers))

    activity = detect_speakers(names, energies, vads, available, detect)
    for i, label in enumerate(names):
        if activity.seconds(i) == 0 and available[i].any():
            warnings.append(f"{label}: never detected as speaking; check the camera roles")
    return Analysis(activity, [c.id for c in speakers], vad.name, warnings)


def cutlist_from_analysis(
    project: Project, analysis: Analysis, switch: SwitchParams | None = None
) -> CutList:
    """Camera cuts from an analysis, using the project's preset (or ``switch``)."""
    params = switch or params_for(project.preset)
    duration_frames, _ = _timeline_frames(project)
    speakers = [c for c in project.clips if c.role is ClipRole.SPEAKER]
    if [c.id for c in speakers] != analysis.speaker_clip_ids:
        raise ValueError("speaker cameras changed since the analysis; analyse again")
    wide = next((c for c in project.clips if c.role is ClipRole.WIDE), None)
    shots = plan_shots(analysis.activity, params, has_wide=wide is not None)
    segments = shots_to_segments(
        shots,
        analysis_rate=analysis.activity.frame_rate,
        fps=project.output.fps,
        duration_frames=duration_frames,
        speaker_clips=[c.id for c in speakers],
        wide_clip=wide.id if wide else None,
    )
    cutlist = CutList(
        project_id=project.id,
        fps=project.output.fps,
        segments=segments,
        audio=AudioConfig(
            gains_db={c.id: 0.0 for c in project.clips if c.role is not ClipRole.BROLL}
        ),
    )
    cutlist.check_against(project)
    return cutlist


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
    analysis = analyze_project(
        project, vad=vad, detect=detect, cache_dir=cache_dir, sample_rate=sample_rate
    )
    cutlist = cutlist_from_analysis(project, analysis, switch)
    return AutoEditResult(cutlist, analysis.activity, analysis.vad_backend, analysis.warnings)
