"""High-level pipeline: sync report -> project -> analysis -> CutList.

report  = sync_files([...])                          # Phase 1
project = build_project(report, roles=..., labels=...)
result  = auto_edit(project)                         # Phase 2
result.cutlist                                       # -> render (Phase 3)
"""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID

import numpy as np

from multicam_engine.analysis.energy import FEATURE_RATE
from multicam_engine.analysis.energy import FloatArray as FloatArrayT
from multicam_engine.analysis.speakers import BoolArray as BoolArrayT
from multicam_engine.analysis.speakers import (
    DetectParams,
    SpeakerActivity,
    analyze_track,
    detect_speakers,
    to_reference,
)
from multicam_engine.analysis.vad import Vad, VadKind, load_vad
from multicam_engine.decide.presets import SwitchParams, params_for
from multicam_engine.decide.switch import Camera, camera_shots_to_segments, plan_camera_shots
from multicam_engine.layout import LayoutError, ResolvedLayout, resolve_layout
from multicam_engine.media.audio import SYNC_SAMPLE_RATE, NoAudioError, load_audio
from multicam_engine.media.probe import probe
from multicam_engine.models.cutlist import AudioConfig, CutList
from multicam_engine.models.project import (
    Clip,
    ClipRole,
    OutputSettings,
    Preset,
    Project,
    ShotType,
)
from multicam_engine.sync.engine import SyncReport

LOW_SYNC_CONFIDENCE = 0.5
#: More than this share of speech labelled as two people at once usually means the
#: mics hear everyone about equally loud (camera mics in one room).
MUDDY_CROSSTALK_SHARE = 0.2
#: Mics decoded / analysed at the same time (ffmpeg and ONNX release the GIL).
MAX_PARALLEL_MICS = 4


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
    if not ref_media.has_video:  # sound-only reference: output follows the first camera
        ref_media = next((c.media for c in clips if c.media and c.media.has_video), ref_media)
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
    #: Mic clip of each speaker (activity row order).
    speaker_clip_ids: list[UUID]
    vad_backend: str
    warnings: list[str] = field(default_factory=list)
    #: Channel of each mic (-1 = all channels mixed); empty for old analyses.
    mic_channels: list[int] = field(default_factory=list)

    @property
    def mic_keys(self) -> list[tuple[UUID, int | None]]:
        channels = self.mic_channels or [-1] * len(self.speaker_clip_ids)
        return [
            (c, None if ch < 0 else ch)
            for c, ch in zip(self.speaker_clip_ids, channels, strict=True)
        ]

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
                mic_channels=np.array(
                    self.mic_channels or [-1] * len(self.speaker_clip_ids), dtype=np.int64
                ),
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
            channels = (
                [int(c) for c in data["mic_channels"]] if "mic_channels" in data.files else []
            )
            return cls(
                activity=activity,
                speaker_clip_ids=[UUID(str(c)) for c in data["speaker_clip_ids"]],
                vad_backend=str(data["vad_backend"]),
                warnings=[str(w) for w in data["warnings"]],
                mic_channels=channels,
            )


def _timeline_frames(project: Project) -> tuple[int, int]:
    """(output frames, analysis frames) covering the reference clip."""
    if project.reference_clip_id is None:
        raise ValueError("project has no reference clip (run sync first)")
    ref = project.clip(project.reference_clip_id)
    if ref.media is None:
        raise ValueError("reference clip has no media info (probe it first)")
    src, out = ref.media.fps, project.output.fps
    # The reference may run at another rate than the output (custom output
    # settings, or a sound-only reference): convert through exact seconds.
    duration_frames = max(
        1, -(-ref.media.duration_frames * src.den * out.num // (src.num * out.den))
    )
    return duration_frames, int(np.ceil(duration_frames * FEATURE_RATE * out.den / out.num))


def analyze_project(
    project: Project,
    *,
    vad: Vad | VadKind = "auto",
    detect: DetectParams | None = None,
    cache_dir: Path | None = None,
    sample_rate: int = SYNC_SAMPLE_RATE,
    on_progress: Callable[[float], None] | None = None,
) -> Analysis:
    """Measure loudness + speech on every speaker's mic and label who speaks when.

    Mics are decoded and analysed in parallel (audio only, no video decode)."""
    warnings: list[str] = []
    if isinstance(vad, str):
        vad, note = load_vad(vad)
        if note:
            warnings.append(note)
    _, n = _timeline_frames(project)
    try:
        layout = resolve_layout(project)
        mics = layout.mic_keys
    except LayoutError as exc:
        raise ValueError(str(exc)) from exc

    names = [s.name for s in layout.speakers]
    clips = [project.clip(clip_id) for clip_id, _ in mics]
    for name, clip in zip(names, clips, strict=True):
        if clip.sync is None:
            raise ValueError(f"clip {name} is not synced")
        if clip.sync.confidence < LOW_SYNC_CONFIDENCE:
            warnings.append(f"{name}: low sync confidence ({clip.sync.confidence:.2f})")

    done = 0

    def measure(k: int) -> tuple[FloatArrayT, FloatArrayT, BoolArrayT, str | None]:
        nonlocal done
        clip, (_, channel), name = clips[k], mics[k], names[k]
        assert clip.sync is not None
        note: str | None = None
        try:
            audio = load_audio(clip.path, sample_rate, cache_dir, channel=channel)
        except NoAudioError:
            note = f"{name}: no audio; this camera is only used if chosen manually"
            audio = np.zeros(0, dtype=np.float32)
        features = analyze_track(audio, sample_rate, vad) if len(audio) else None
        offset_s = clip.sync.offset_samples / clip.sync.sample_rate
        if features is None:
            result = (np.full(n, -120.0), np.zeros(n), np.zeros(n, dtype=bool), note)
        else:
            energy, prob, avail = to_reference(features, n, offset_s, clip.sync.drift_ppm)
            result = (energy, prob, avail, note)
        done += 1
        if on_progress:
            on_progress(done / len(mics))
        return result

    workers = max(1, min(MAX_PARALLEL_MICS, len(mics)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        measured = list(pool.map(measure, range(len(mics))))
    energies = [m[0] for m in measured]
    vads = [m[1] for m in measured]
    available = [m[2] for m in measured]
    warnings.extend(m[3] for m in measured if m[3])

    activity = detect_speakers(names, energies, vads, available, detect)
    for i, label in enumerate(names):
        if activity.seconds(i) == 0 and available[i].any():
            warnings.append(f"{label}: never detected as speaking; check the camera roles")
    voiced = int(np.count_nonzero(activity.labels != -1))
    if (
        len(names) > 1
        and voiced
        and activity.seconds(-2) * activity.frame_rate / voiced > (MUDDY_CROSSTALK_SHARE)
    ):
        warnings.append(
            "the microphones hear everyone about equally loud, so who is speaking is often "
            "unclear; a separate mic per person (lav / podcast mic) gives much better cuts"
        )
    return Analysis(
        activity,
        [clip_id for clip_id, _ in mics],
        vad.name,
        warnings,
        mic_channels=[-1 if ch is None else ch for _, ch in mics],
    )


def clip_coverage(clip: Clip, n: int, rate: int = FEATURE_RATE) -> BoolArrayT | None:
    """Analysis frames of the reference timeline this clip has picture for
    (None: unknown, treat as always recording)."""
    if clip.sync is None or clip.media is None:
        return None
    fps = clip.media.fps
    duration_s = clip.media.duration_frames * fps.den / fps.num
    t = np.arange(n, dtype=np.float64) / rate
    offset_s = clip.sync.offset_samples / clip.sync.sample_rate
    pos = t + offset_s + clip.sync.drift_ppm * 1e-6 * t
    covered: BoolArrayT = (pos >= 0) & (pos <= duration_s)
    return covered


def switch_cameras(
    project: Project, layout: ResolvedLayout, analysis: Analysis
) -> tuple[list[Camera], list[UUID]]:
    """The cameras as switching sees them, and their clip ids (same order)."""
    index = layout.speaker_index()
    n = analysis.activity.n_frames
    mic_row = {key: i for i, key in enumerate(analysis.mic_keys)}
    cams: list[Camera] = []
    for cam in layout.cameras:
        row = mic_row.get((cam.clip_id, None))
        available = (
            analysis.activity.available[row]
            if row is not None
            else clip_coverage(project.clip(cam.clip_id), n, analysis.activity.frame_rate)
        )
        cams.append(
            Camera(
                covers=frozenset(index[s] for s in cam.covers if s in index),
                wide=cam.shot is ShotType.WIDE,
                priority=cam.priority,
                available=available,
            )
        )
    return cams, [c.clip_id for c in layout.cameras]


def cutlist_from_analysis(
    project: Project, analysis: Analysis, switch: SwitchParams | None = None
) -> CutList:
    """Camera cuts from an analysis, using the project's preset (or ``switch``)."""
    params = switch or params_for(project.preset)
    duration_frames, _ = _timeline_frames(project)
    try:
        layout = resolve_layout(project)
        mics = layout.mic_keys
    except LayoutError as exc:
        raise ValueError(str(exc)) from exc
    if mics != analysis.mic_keys:
        raise ValueError("speakers or their mics changed since the analysis; analyse again")
    cameras, camera_clips = switch_cameras(project, layout, analysis)
    shots = plan_camera_shots(analysis.activity, cameras, params)
    segments = camera_shots_to_segments(
        shots,
        analysis_rate=analysis.activity.frame_rate,
        fps=project.output.fps,
        duration_frames=duration_frames,
        camera_clips=camera_clips,
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
