"""What each job kind does. Every step:

* checks the clip files first (missing -> a clear error telling the user to relink;
  changed -> re-probed and re-synced automatically),
* computes a hash of its inputs and skips the work if the last successful run of
  that step had the same inputs and its output still exists ("cached": true),
* reports progress and honours cancellation.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from multicam_api.db.models import ClipRow, CutListRow, ExportRow, ProjectRow, StepCacheRow
from multicam_api.jobs.context import JobContext, JobFailedError
from multicam_api.schemas import AnalyzeParams, AutoParams, DecideParams, JobKind, RenderParams
from multicam_api.services.projects import (
    FileStatus,
    add_cutlist_version,
    clip_fingerprint,
    file_stat,
    file_status,
    follow_reference,
    latest_cutlist,
    project_to_engine,
    stable_hash,
)
from multicam_engine.decide.presets import params_for
from multicam_engine.media.probe import ProbeError, probe
from multicam_engine.models.cutlist import AudioConfig, AudioMode, CutList
from multicam_engine.models.project import ClipRole, Project
from multicam_engine.pipeline import Analysis, analyze_project, cutlist_from_analysis
from multicam_engine.render import PRESETS, RenderProgress, render
from multicam_engine.sync import sync_files

Result = dict[str, Any]


# ------------------------------------------------------------------ helpers
def _project(session: Session, ctx: JobContext) -> ProjectRow:
    row = session.get(ProjectRow, str(ctx.project_id))
    if row is None:
        raise JobFailedError("project was deleted")
    return row


def _cache_get(session: Session, project_id: UUID, step: str) -> StepCacheRow | None:
    return session.scalars(
        select(StepCacheRow).where(
            StepCacheRow.project_id == str(project_id), StepCacheRow.step == step
        )
    ).first()


def _cache_put(
    session: Session, project_id: UUID, step: str, input_hash: str, result: Result
) -> None:
    row = _cache_get(session, project_id, step)
    if row is None:
        session.add(
            StepCacheRow(
                project_id=str(project_id), step=step, input_hash=input_hash, result=result
            )
        )
    else:
        row.input_hash, row.result = input_hash, result


def _probe_row(clip: ClipRow) -> None:
    try:
        clip.media = probe(clip.path).media.model_dump(mode="json")
    except ProbeError as exc:
        raise JobFailedError(f"cannot read {Path(clip.path).name}: {exc}") from exc
    stat = file_stat(clip.path)
    clip.file_size, clip.file_mtime_ns = (stat[0], stat[1]) if stat else (None, None)


def check_files(ctx: JobContext) -> None:
    """Fail on missing files; re-probe (and drop the sync of) changed ones."""
    with ctx.db.transaction() as s:
        project = _project(s, ctx)
        missing = [c for c in project.clips if file_status(c) is FileStatus.MISSING]
        if missing:
            names = ", ".join(f"{Path(c.path).name} ({c.path})" for c in missing)
            raise JobFailedError(
                f"file(s) not found: {names}. If you moved them, relink the clip "
                "(PATCH /api/clips/{id} with the new path)."
            )
        for clip in project.clips:
            status = file_status(clip)
            if status is FileStatus.OK:
                continue
            _probe_row(clip)
            if status is FileStatus.CHANGED:
                ctx.warnings.append(f"{Path(clip.path).name} changed on disk; re-synced")
                if clip.id == project.reference_clip_id:
                    for other in project.clips:
                        other.sync = None
                clip.sync = None
        follow_reference(project)


# ------------------------------------------------------------------ probe
def run_probe(ctx: JobContext) -> Result:
    check_files(ctx)
    with ctx.db.transaction() as s:
        project = _project(s, ctx)
        for i, clip in enumerate(project.clips):
            ctx.report("probe", i / max(1, len(project.clips)), Path(clip.path).name)
            _probe_row(clip)
        follow_reference(project)
        return {"clips": len(project.clips)}


# ------------------------------------------------------------------ sync
def _sync_hash(project: ProjectRow) -> str:
    return stable_hash(
        {"clips": [clip_fingerprint(c) for c in project.clips], "ref": project.reference_clip_id}
    )


def run_sync(ctx: JobContext) -> Result:
    check_files(ctx)
    with ctx.db.session() as s:
        project = _project(s, ctx)
        if len(project.clips) < 2:
            raise JobFailedError("add at least two clips before syncing")
        input_hash = _sync_hash(project)
        cached = _cache_get(s, ctx.project_id, "sync")
        if cached and cached.input_hash == input_hash and all(c.sync for c in project.clips):
            return {**cached.result, "cached": True}
        paths = {c.path: c.id for c in project.clips}
        ref = next(c for c in project.clips if c.id == project.reference_clip_id)
        ref_path, ref_id = ref.path, ref.id

    done = 0
    steps = 2 * len(paths) - 1  # decode each clip, sync each non-reference clip

    def on_progress(message: str) -> None:
        nonlocal done
        done += 1
        ctx.report("sync", done / steps, message)

    report = sync_files(
        list(paths),
        reference=ref_path,
        cache_dir=ctx.settings.audio_cache_dir,
        on_progress=on_progress,
    )
    ctx.storage.artifact_path(ctx.project_id, "sync.json").write_text(
        report.model_dump_json(indent=2), encoding="utf-8"
    )
    clips_out: list[Result] = []
    with ctx.db.transaction() as s:
        project = _project(s, ctx)
        by_id = {c.id: c for c in project.clips}
        for entry in report.clips:
            clip = by_id.get(paths.get(entry.file, ""))
            if clip is None:
                continue
            clip.sync = entry.to_sync_result(UUID(ref_id)).model_dump(mode="json")
            ctx.warnings.extend(f"{Path(entry.file).name}: {w}" for w in entry.warnings)
            clips_out.append(
                {
                    "clip_id": clip.id,
                    "offset_ms": round(entry.offset_seconds * 1000, 2),
                    "drift_ppm": entry.drift_ppm,
                    "confidence": entry.confidence,
                }
            )
        result: Result = {"clips": clips_out}
        _cache_put(s, ctx.project_id, "sync", input_hash, result)
    return {**result, "cached": False}


# ------------------------------------------------------------------ analyze
def _analyze_hash(project: ProjectRow, vad: str) -> str:
    return stable_hash(
        {
            "clips": [
                {**clip_fingerprint(c), "role": c.role, "label": c.speaker_label, "sync": c.sync}
                for c in project.clips
            ],
            "ref": project.reference_clip_id,
            "output": project.output,
            "vad": vad,
        }
    )


def _require_synced(project: Project) -> None:
    unsynced = [
        Path(c.path).name for c in project.clips if c.role is ClipRole.SPEAKER and c.sync is None
    ]
    if unsynced:
        raise JobFailedError(f"not synced yet: {', '.join(unsynced)} (run a sync job first)")


def run_analyze(ctx: JobContext) -> Result:
    return analyze(ctx, AnalyzeParams.model_validate(ctx.params))


def analyze(ctx: JobContext, params: AnalyzeParams) -> Result:
    check_files(ctx)
    with ctx.db.session() as s:
        row = _project(s, ctx)
        project = project_to_engine(row)
        input_hash = _analyze_hash(row, params.vad)
        cached = _cache_get(s, ctx.project_id, "analyze")
    artifact = ctx.storage.artifact_path(ctx.project_id, f"analysis-{input_hash[:20]}.npz")
    if cached and cached.input_hash == input_hash and artifact.is_file():
        return {**cached.result, "cached": True}
    _require_synced(project)
    analysis = analyze_project(
        project,
        vad=params.vad,
        cache_dir=ctx.settings.audio_cache_dir,
        on_progress=ctx.progress_callback("analyze"),
    )
    analysis.save(artifact)
    ctx.warnings.extend(analysis.warnings)
    act = analysis.activity
    result: Result = {
        "vad_backend": analysis.vad_backend,
        "artifact": artifact.name,
        "vad": params.vad,
        "speakers": [
            {"clip_id": str(cid), "label": act.speakers[i], "speaking_s": round(act.seconds(i), 1)}
            for i, cid in enumerate(analysis.speaker_clip_ids)
        ],
    }
    with ctx.db.transaction() as s:
        _cache_put(s, ctx.project_id, "analyze", input_hash, result)
    return {**result, "cached": False}


# ------------------------------------------------------------------ decide
def run_decide(ctx: JobContext) -> Result:
    return decide(ctx, DecideParams.model_validate(ctx.params))


def decide(ctx: JobContext, params: DecideParams) -> Result:
    with ctx.db.session() as s:
        row = _project(s, ctx)
        analyzed = _cache_get(s, ctx.project_id, "analyze")
        vad = str(analyzed.result.get("vad", "auto")) if analyzed else "auto"
        current = _analyze_hash(row, vad)
        valid = analyzed is not None and analyzed.input_hash == current
    if not valid:
        analyze(ctx, AnalyzeParams.model_validate({"vad": vad}))
    with ctx.db.session() as s:
        row = _project(s, ctx)
        analyzed = _cache_get(s, ctx.project_id, "analyze")
        assert analyzed is not None
        project = project_to_engine(row)
        use_preset = params.preset or project.preset
        input_hash = stable_hash(
            {
                "analysis": analyzed.input_hash,
                "preset": use_preset.value,
                "roles": [(c.id, c.role) for c in row.clips],
            }
        )
        latest = latest_cutlist(s, str(ctx.project_id))
        if latest is not None and latest.input_hash == input_hash:
            return {
                "version": latest.version,
                "segments": len(latest.data["segments"]),
                "preset": use_preset.value,
                "cached": True,
            }
        artifact = ctx.storage.artifact_path(ctx.project_id, str(analyzed.result["artifact"]))
    ctx.report("decide", 0.2, "choosing cameras")
    try:
        cutlist = cutlist_from_analysis(project, Analysis.load(artifact), params_for(use_preset))
    except ValueError as exc:
        raise JobFailedError(str(exc)) from exc
    with ctx.db.transaction() as s:
        saved: CutListRow = add_cutlist_version(
            s, str(ctx.project_id), cutlist, source="auto", input_hash=input_hash
        )
        return {
            "version": saved.version,
            "segments": len(cutlist.segments),
            "preset": use_preset.value,
            "cached": False,
        }


# ------------------------------------------------------------------ auto
def run_auto(ctx: JobContext) -> Result:
    params = AutoParams.model_validate(ctx.params)
    ctx.span(0.0, 0.45)
    synced = run_sync(ctx)
    ctx.span(0.45, 0.9)
    analyzed = analyze(ctx, AnalyzeParams(vad=params.vad))
    ctx.span(0.9, 1.0)
    decided = decide(ctx, DecideParams(preset=params.preset))
    return {"sync": synced, "analyze": analyzed, "decide": decided}


# ------------------------------------------------------------------ render
def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", text).strip("-") or "episode"


def run_render(ctx: JobContext) -> Result:
    params = RenderParams.model_validate(ctx.params)
    if params.preset not in PRESETS:
        raise JobFailedError(f"unknown render preset {params.preset!r} (known: {sorted(PRESETS)})")
    check_files(ctx)
    with ctx.db.session() as s:
        row = _project(s, ctx)
        project = project_to_engine(row)
        latest = latest_cutlist(s, str(ctx.project_id))
        if latest is None:
            raise JobFailedError("no cutlist yet: run an auto (or decide) job first")
        cutlist = CutList.model_validate(latest.data)
        version = latest.version
        if params.audio_clip_id is not None:
            if params.audio_clip_id not in {c.id for c in project.clips}:
                raise JobFailedError("audio_clip_id is not a clip of this project")
            cutlist.audio = AudioConfig(mode=AudioMode.SINGLE, single_clip_id=params.audio_clip_id)
        out = (
            Path(params.output_path)
            if params.output_path
            else (
                ctx.storage.exports_dir(ctx.project_id)
                / f"{_slug(row.name)}-v{version}-{params.preset}.mp4"
            )
        )
        input_hash = stable_hash(
            {
                "cutlist": latest.data,
                "audio": cutlist.audio.model_dump(mode="json"),
                "clips": [{**clip_fingerprint(c), "sync": c.sync} for c in row.clips],
                "preset": params.preset,
                "encoder": params.encoder,
                "out": str(out),
            }
        )
        cached = _cache_get(s, ctx.project_id, "render")
        if cached and cached.input_hash == input_hash and out.is_file():
            return {**cached.result, "cached": True}

    def on_progress(p: RenderProgress) -> None:
        eta = f", ETA {p.eta_s:.0f} s" if p.eta_s else ""
        ctx.report(f"render:{p.stage}", p.fraction, f"{p.frames_done}/{p.total_frames} frames{eta}")

    result = render(
        project,
        cutlist,
        out,
        preset=params.preset,
        encoder=params.encoder,
        on_progress=on_progress,
        cancel=ctx.cancel_event,
    )
    ctx.warnings.extend(result.warnings)
    with ctx.db.transaction() as s:
        export = ExportRow(
            id=str(uuid4()),
            project_id=str(ctx.project_id),
            job_id=str(ctx.job_id),
            kind="video",
            path=str(out),
            preset=params.preset,
            input_hash=input_hash,
            frames=result.frames,
        )
        s.add(export)
        out_result: Result = {
            "export_id": export.id,
            "path": str(out),
            "frames": result.frames,
            "encoder": result.encoder,
            "cutlist_version": version,
            "elapsed_s": result.elapsed_s,
        }
        _cache_put(s, ctx.project_id, "render", input_hash, out_result)
    return {**out_result, "cached": False}


STEPS: dict[JobKind, Callable[[JobContext], Result]] = {
    JobKind.PROBE: run_probe,
    JobKind.SYNC: run_sync,
    JobKind.ANALYZE: run_analyze,
    JobKind.DECIDE: run_decide,
    JobKind.AUTO: run_auto,
    JobKind.RENDER: run_render,
}
