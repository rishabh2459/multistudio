"""Plugin API v1: what the Premiere / Resolve / Final Cut plugins talk to (D76).

Flow: ``handshake`` -> ``POST /sessions`` (clips the user selected in the NLE)
-> ``PATCH /sessions/{id}/setup`` (who is who, preset) -> ``POST .../run`` ->
``GET .../events`` (SSE progress, ``plan_ready``) -> ``GET .../editplan``
(apply in the host) or ``GET .../export`` (XML fallback, Rule C).

Errors are ``{"code", "message", "hint"}`` with stable codes (``ErrorCode``).
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from sse_starlette import EventSourceResponse
from starlette.concurrency import run_in_threadpool

from multicam_api import __version__ as api_version
from multicam_api.db.models import (
    ClipRow,
    CutListRow,
    ExportRow,
    JobRow,
    PluginSessionRow,
    ProjectRow,
)
from multicam_api.plugin_schemas import (
    PLUGIN_API_VERSION,
    ErrorCode,
    ExportFileOut,
    FeedbackIn,
    FeedbackOut,
    Handshake,
    HostInfo,
    LicenceInfo,
    ModelsAvailable,
    PlanSummary,
    RunIn,
    RunOut,
    SessionClipOut,
    SessionCreate,
    SessionOut,
    SessionSetup,
    SessionState,
    SocialIn,
)
from multicam_api.routers import presets as presets_router
from multicam_api.routers._common import SessionDep, StateDep
from multicam_api.routers.jobs import enqueue, validate_params
from multicam_api.schemas import (
    JobKind,
    JobOut,
    JobStatus,
    PresetOut,
    ProjectLayout,
    UserPresetIn,
)
from multicam_api.services import media as media_service
from multicam_api.services.projects import (
    file_stat,
    file_status,
    follow_reference,
    latest_cutlist,
    project_to_engine,
    switch_settings,
)
from multicam_api.state import AppState
from multicam_api.views import effective_layout, job_out
from multicam_engine import __version__ as engine_version
from multicam_engine.analysis.vad import SILERO_MODEL_FILE, models_dir
from multicam_engine.editplan import (
    LOW_CONFIDENCE,
    EditPlan,
    HostApp,
    PlanMethod,
    build_edit_plan,
    plan_to_timeline,
)
from multicam_engine.export import EXTENSIONS, NleFormat, write_nle
from multicam_engine.layout import LayoutError, resolve_layout
from multicam_engine.media.probe import ProbeError, probe
from multicam_engine.models import CutList
from multicam_engine.models.project import ClipRole, OutputSettings, Preset, SyncResult
from multicam_engine.reframe.detect import YUNET_MODEL_FILE

router = APIRouter(prefix="/api/plugin/v1", tags=["plugin"])

CAPABILITIES = [
    "sync",
    "already_synced",
    "layouts",
    "presets",
    "user_presets",
    "editplan",
    "method:cuts",
    "method:stacked_enable",
    "method:multicam",
    "export:fcpxml",
    "export:xmeml",
    "export:edl",
    "markers",
    "reframe",
    "sound_only_mics",
    "multichannel_mics",
    "feedback",
]
SYNC_SAMPLE_RATE = 48_000


class PluginError(Exception):
    """Raised by plugin endpoints; rendered as ``{code, message, hint}``."""

    def __init__(
        self, code: ErrorCode, message: str, hint: str = "", status_code: int = 422
    ) -> None:
        super().__init__(message)
        self.code, self.message, self.hint, self.status_code = code, message, hint, status_code


# ------------------------------------------------------------------ helpers
def _session_or_404(db: Session, session_id: UUID) -> PluginSessionRow:
    row = db.get(PluginSessionRow, str(session_id))
    if row is None:
        raise PluginError(ErrorCode.NOT_FOUND, f"session {session_id} not found", status_code=404)
    return row


def _project(db: Session, row: PluginSessionRow) -> ProjectRow:
    project = db.get(ProjectRow, row.project_id)
    if project is None:  # pragma: no cover - cascade deletes the session too
        raise PluginError(ErrorCode.NOT_FOUND, "the session's project was deleted", status_code=404)
    return project


def _latest_job(db: Session, project_id: str) -> JobRow | None:
    return db.scalars(
        select(JobRow).where(JobRow.project_id == project_id).order_by(JobRow.created_at.desc())
    ).first()


def _plan_summary(cut: CutListRow | None) -> PlanSummary | None:
    if cut is None:
        return None
    cutlist = CutList.model_validate(cut.data)
    low = sum(
        1
        for s in cutlist.segments[1:]
        if s.confidence is not None and s.confidence < LOW_CONFIDENCE
    )
    return PlanSummary(
        cutlist_version=cut.version,
        source=cut.source,
        cuts=len(cutlist.segments) - 1,
        duration_frames=cutlist.duration_frames,
        low_confidence_cuts=low,
    )


def _clip_kind(clip: ClipRow) -> str:
    if clip.role == ClipRole.MIC.value:
        return "audio"
    if clip.media and not clip.media.get("has_video", True):
        return "audio"
    return "video"


def session_out(db: Session, row: PluginSessionRow, *, reused: bool = False) -> SessionOut:
    project = _project(db, row)
    refs: dict[str, Any] = row.clip_refs or {}
    job = _latest_job(db, project.id)
    cut = latest_cutlist(db, project.id)
    if job is not None and JobStatus(job.status) in (JobStatus.QUEUED, JobStatus.RUNNING):
        state = SessionState.RUNNING
    elif job is not None and JobStatus(job.status) is JobStatus.FAILED:
        state = SessionState.FAILED
    elif cut is not None:
        state = SessionState.READY
    else:
        state = SessionState.SETUP
    speakers, cameras = effective_layout(project)
    warnings: list[str] = []
    missing = [c for c in project.clips if file_status(c).value == "missing"]
    if missing:
        warnings.append("offline: " + ", ".join(Path(c.path).name for c in missing))
    if job is not None and job.result:
        warnings.extend(str(w) for w in job.result.get("warnings", []))
    return SessionOut(
        id=UUID(row.id),
        project_id=UUID(project.id),
        reused=reused,
        host=HostInfo.model_validate(
            {"app": row.host_app, "version": row.host_version, "os": row.host_os}
        ),
        host_sequence_id=row.host_sequence_id,
        already_synced=row.already_synced,
        method=PlanMethod(row.method),
        state=state,
        name=project.name,
        clips=[
            SessionClipOut(
                clip_id=UUID(c.id),
                path=c.path,
                name=Path(c.path).name,
                kind="audio" if _clip_kind(c) == "audio" else "video",
                role=ClipRole(c.role),
                label=c.speaker_label,
                host_ref=(refs.get(c.id) or {}).get("host_ref"),
                track=(refs.get(c.id) or {}).get("track"),
                file_status=file_status(c),
                synced=c.sync is not None,
                sync_confidence=(c.sync or {}).get("confidence"),
            )
            for c in project.clips
        ],
        speakers=speakers,
        cameras=cameras,
        layout_custom=bool(project.layout),
        preset=Preset(project.preset),
        switch=switch_settings(project),
        switch_custom=project.switch is not None,
        job=job_out(job) if job is not None else None,
        plan=_plan_summary(cut),
        warnings=warnings,
    )


def _probe_media(path: str) -> dict[str, Any] | None:
    try:
        return probe(path).media.model_dump(mode="json")
    except (ProbeError, FileNotFoundError):
        return None


# ------------------------------------------------------------------ handshake
@router.get("/handshake", response_model=Handshake)
def handshake(state: StateDep) -> Handshake:
    """Engine + API version and what this engine can do. Plugins check
    ``api_version`` (same major) and ``capabilities`` before anything else."""
    return Handshake(
        engine_version=f"{engine_version} (api {api_version})",
        api_version=PLUGIN_API_VERSION,
        capabilities=CAPABILITIES,
        models=ModelsAvailable(
            vad=(models_dir() / SILERO_MODEL_FILE).is_file(),
            face=(models_dir() / YUNET_MODEL_FILE).is_file(),
        ),
        licence=LicenceInfo(),
        data_dir=str(state.settings.data_dir),
        pid=os.getpid(),
    )


# ------------------------------------------------------------------ sessions
@router.post("/sessions", response_model=SessionOut, status_code=status.HTTP_201_CREATED)
def create_session(body: SessionCreate, db: SessionDep) -> SessionOut:
    """Create a session (and project) from the clips selected in the host.
    Idempotent on ``(host.app, host_sequence_id)``: the same clips reuse the
    existing project, so its analysis cache makes a re-run fast."""
    paths = [str(Path(c.path).expanduser()) for c in body.clips]
    if len(set(paths)) != len(paths):
        raise PluginError(ErrorCode.INVALID_REQUEST, "the same file is selected twice")
    videos = [i for i, c in enumerate(body.clips) if c.kind == "video"]
    if not videos:
        raise PluginError(
            ErrorCode.SETUP_REQUIRED,
            "no video clips selected",
            "select the camera clips (and the mic tracks) in the sequence",
        )
    existing = None
    if body.host_sequence_id:
        existing = db.scalars(
            select(PluginSessionRow).where(
                PluginSessionRow.host_app == body.host.app.value,
                PluginSessionRow.host_sequence_id == body.host_sequence_id,
            )
        ).first()
    if existing is not None:
        project = _project(db, existing)
        if [c.path for c in project.clips] == paths:
            _update_refs(existing, project, body)
            db.commit()
            return session_out(db, existing, reused=True)

    project = ProjectRow(
        id=str(uuid4()),
        name=body.sequence.name or Path(paths[videos[0]]).stem,
        preset=Preset.BALANCED.value,
        output=OutputSettings(
            fps=body.sequence.fps,
            width=body.sequence.width - body.sequence.width % 2,
            height=body.sequence.height - body.sequence.height % 2,
        ).model_dump(mode="json"),
        output_custom=True,  # the host sequence decides the output
    )
    db.add(project)
    for pos, (clip, path) in enumerate(zip(body.clips, paths, strict=True)):
        stat = file_stat(path)
        audio = clip.kind == "audio"
        project.clips.append(
            ClipRow(
                id=str(uuid4()),
                project_id=project.id,
                position=pos,
                path=path,
                role=(ClipRole.MIC if audio else ClipRole.SPEAKER).value,
                speaker_label=None if audio else (clip.label or Path(path).stem),
                media=_probe_media(path) if stat else None,
                file_size=stat[0] if stat else None,
                file_mtime_ns=stat[1] if stat else None,
            )
        )
    project.reference_clip_id = project.clips[videos[0]].id
    follow_reference(project)
    db.flush()  # the project row must exist before the session points at it
    if existing is None:
        existing = PluginSessionRow(id=str(uuid4()), clip_refs={}, host_sequence_id=None)
        db.add(existing)
    existing.project_id = project.id
    existing.host_sequence_id = body.host_sequence_id
    _update_refs(existing, project, body)
    db.commit()
    return session_out(db, existing)


def _update_refs(row: PluginSessionRow, project: ProjectRow, body: SessionCreate) -> None:
    row.host_app = body.host.app.value
    row.host_version = body.host.version
    row.host_os = body.host.os
    row.already_synced = body.already_synced
    row.method = row.method or PlanMethod.STACKED_ENABLE.value
    row.clip_refs = {
        c.id: {"host_ref": inp.host_ref, "track": inp.track}
        for c, inp in zip(project.clips, body.clips, strict=True)
    }
    ref = next(i for i, c in enumerate(project.clips) if c.id == project.reference_clip_id)
    row.host_start_frame = body.clips[ref].record_start_frame - body.clips[ref].in_frame
    if body.already_synced and project.reference_clip_id:
        # The event at sequence frame T is at media frame T - start + in in each clip,
        # so offset (this clip minus reference) = (in - start) - (in_ref - start_ref).
        fps = body.sequence.fps
        base = body.clips[ref].in_frame - body.clips[ref].record_start_frame
        for c, inp in zip(project.clips, body.clips, strict=True):
            frames = (inp.in_frame - inp.record_start_frame) - base
            c.sync = SyncResult(
                reference_clip_id=UUID(project.reference_clip_id),
                offset_samples=round(frames * SYNC_SAMPLE_RATE * fps.den / fps.num),
                sample_rate=SYNC_SAMPLE_RATE,
                confidence=1.0,
            ).model_dump(mode="json")


@router.get("/sessions/{session_id}", response_model=SessionOut)
def get_session(session_id: UUID, db: SessionDep) -> SessionOut:
    return session_out(db, _session_or_404(db, session_id))


@router.patch("/sessions/{session_id}/setup", response_model=SessionOut)
def setup_session(session_id: UUID, body: SessionSetup, db: SessionDep) -> SessionOut:
    """Who is who (roles or a full layout), editing style, apply method."""
    row = _session_or_404(db, session_id)
    project = _project(db, row)
    by_id = {c.id: c for c in project.clips}
    if body.name is not None:
        project.name = body.name
    for role in body.roles or []:
        clip = by_id.get(str(role.clip_id))
        if clip is None:
            raise PluginError(ErrorCode.INVALID_REQUEST, f"clip {role.clip_id} is not in session")
        clip.role = role.role.value
        clip.speaker_label = (
            (role.speaker_label or clip.speaker_label or Path(clip.path).stem)
            if role.role is ClipRole.SPEAKER
            else None
        )
    if body.preset is not None:
        project.preset = body.preset.value
        project.switch = None
    if body.switch is not None:
        project.switch = body.switch.model_dump(mode="json")
    if body.reset_layout:
        project.layout = None
    if body.layout is not None:
        _set_layout(project, body.layout)
    if body.method is not None:
        row.method = body.method.value
    db.commit()
    return session_out(db, row)


def _set_layout(project: ProjectRow, layout: ProjectLayout) -> None:
    previous = project.layout
    project.layout = layout.model_dump(mode="json")
    try:
        resolve_layout(project_to_engine(project))
    except (ValueError, LayoutError) as exc:
        project.layout = previous
        raise PluginError(
            ErrorCode.SETUP_REQUIRED, f"invalid layout: {exc}", "check who is in each camera"
        ) from exc


@router.post("/sessions/{session_id}/run", response_model=RunOut, status_code=202)
def run_session(session_id: UUID, body: RunIn, db: SessionDep, state: StateDep) -> RunOut:
    row = _session_or_404(db, session_id)
    project = _project(db, row)
    busy = _latest_job(db, project.id)
    if busy is not None and JobStatus(busy.status) in (JobStatus.QUEUED, JobStatus.RUNNING):
        raise PluginError(
            ErrorCode.ENGINE_BUSY,
            "this session is already running",
            "wait for it to finish or cancel it",
            status_code=409,
        )
    missing = [Path(c.path).name for c in project.clips if file_status(c).value == "missing"]
    if missing:
        raise PluginError(
            ErrorCode.MEDIA_OFFLINE,
            f"offline media: {', '.join(missing)}",
            "relink the media in the host, then start again",
        )
    params: dict[str, Any]
    if body.steps == "auto":
        kind = JobKind.AUTO
        params = {"vad": body.vad, "framing": body.framing, "sync": not row.already_synced}
    else:
        if len(body.steps) != 1:
            raise PluginError(ErrorCode.INVALID_REQUEST, 'give "auto" or exactly one step')
        kind = JobKind(body.steps[0])
        params = {"vad": body.vad} if kind is JobKind.ANALYZE else {}
    job = JobRow(
        id=str(uuid4()),
        project_id=project.id,
        kind=kind.value,
        status=JobStatus.QUEUED.value,
        params=validate_params(kind, params),
    )
    enqueue(state, db, job)
    return RunOut(
        job_id=UUID(job.id),
        kind=kind.value,
        events_url=f"/api/plugin/v1/sessions/{session_id}/events?job_id={job.id}",
    )


# ------------------------------------------------------------------ events
_ERROR_PATTERNS: list[tuple[str, ErrorCode, str]] = [
    ("not found", ErrorCode.MEDIA_OFFLINE, "relink the media in the host, then start again"),
    ("cannot read", ErrorCode.UNSUPPORTED_CODEC, "transcode the clip (e.g. ProRes / H.264)"),
    ("no microphone", ErrorCode.SETUP_REQUIRED, "pick the mic of each speaker in Setup"),
    ("no speakers", ErrorCode.SETUP_REQUIRED, "mark who is talking on which clip"),
    ("no cameras", ErrorCode.SETUP_REQUIRED, "mark at least one clip as a camera"),
    ("not synced", ErrorCode.SYNC_LOW_CONFIDENCE, "sync the clips (turn off 'already synced')"),
]


def job_error(job: JobOut) -> dict[str, str]:
    text = job.error or "the job failed"
    for needle, code, hint in _ERROR_PATTERNS:
        if needle in text.lower():
            return {"code": code.value, "message": text, "hint": hint}
    return {"code": ErrorCode.JOB_FAILED.value, "message": text, "hint": ""}


def _events_snapshot(
    state: AppState, project_id: str, job_id: str | None
) -> tuple[JobOut | None, PlanSummary | None]:
    with state.db.session() as db:
        job = db.get(JobRow, job_id) if job_id else _latest_job(db, project_id)
        return (job_out(job) if job else None), _plan_summary(latest_cutlist(db, project_id))


@router.get("/sessions/{session_id}/events")
async def session_events(
    session_id: UUID,
    request: Request,
    state: StateDep,
    job_id: UUID | None = None,
) -> EventSourceResponse:
    """SSE: ``progress`` while the job runs, then ``plan_ready`` (with the plan
    summary) or ``error`` (``{code, message, hint}``); the stream then ends."""
    with state.db.session() as db:
        project_id = _session_or_404(db, session_id).project_id

    async def stream() -> AsyncIterator[dict[str, str]]:
        last: tuple[object, ...] | None = None
        while not await request.is_disconnected():
            job, plan = await run_in_threadpool(
                _events_snapshot, state, project_id, str(job_id) if job_id else None
            )
            if job is None:
                if plan is not None:
                    yield {"event": "plan_ready", "data": plan.model_dump_json()}
                else:
                    yield {"event": "idle", "data": "{}"}
                return
            key = (job.status, round(job.progress, 3), job.stage, job.message)
            if key != last:
                last = key
                yield {
                    "event": "progress",
                    "data": json.dumps(
                        {
                            "job_id": str(job.id),
                            "status": job.status.value,
                            "stage": job.stage,
                            "progress": job.progress,
                            "message": job.message,
                        }
                    ),
                }
            if job.status is JobStatus.SUCCEEDED:
                if plan is not None:
                    yield {"event": "plan_ready", "data": plan.model_dump_json()}
                else:
                    yield {"event": "step_done", "data": json.dumps({"job_id": str(job.id)})}
                return
            if job.status.finished:
                yield {"event": "error", "data": json.dumps(job_error(job))}
                return
            await asyncio.sleep(state.settings.sse_interval)

    return EventSourceResponse(stream(), ping=15)


# ------------------------------------------------------------------ plans
def _cutlist_row(db: Session, project_id: str, version: int | None) -> CutListRow:
    if version is None:
        row = latest_cutlist(db, project_id)
    else:
        row = db.scalars(
            select(CutListRow).where(
                CutListRow.project_id == project_id, CutListRow.version == version
            )
        ).first()
    if row is None:
        raise PluginError(
            ErrorCode.NO_PLAN,
            "no edit yet",
            "run auto edit first",
            status_code=status.HTTP_409_CONFLICT,
        )
    return row


def _plan(
    db: Session,
    row: PluginSessionRow,
    *,
    host: HostApp,
    version: int | None,
    method: PlanMethod | None,
) -> EditPlan:
    project_row = _project(db, row)
    cut_row = _cutlist_row(db, project_row.id, version)
    project = project_to_engine(project_row)
    cutlist = CutList.model_validate(cut_row.data)
    probes = {}
    offline: list[str] = []
    for clip in project_row.clips:
        try:
            probes[UUID(clip.id)] = media_service.probe_cached(clip.path)
        except (FileNotFoundError, ProbeError):
            offline.append(Path(clip.path).name)
    refs = {
        UUID(cid): ref["host_ref"]
        for cid, ref in (row.clip_refs or {}).items()
        if ref and ref.get("host_ref")
    }
    try:
        return build_edit_plan(
            project,
            cutlist,
            probes,
            cutlist_version=cut_row.version,
            method=method or PlanMethod(row.method),
            host=host,
            host_refs=refs,
            name=f"{project_row.name} - Auto Edit v{cut_row.version}",
            host_start_frame=row.host_start_frame,
        )
    except ValueError as exc:
        if offline:
            raise PluginError(
                ErrorCode.MEDIA_OFFLINE,
                f"offline media: {', '.join(offline)}",
                "relink the media in the host",
            ) from exc
        raise PluginError(ErrorCode.JOB_FAILED, str(exc)) from exc


@router.get("/sessions/{session_id}/editplan", response_model=EditPlan)
def get_editplan(
    session_id: UUID,
    db: SessionDep,
    host: HostApp = HostApp.GENERIC,
    version: int | None = Query(default=None, ge=1),
    method: PlanMethod | None = None,
) -> EditPlan:
    """The edit as host operations (default: latest version, the session's method)."""
    return _plan(db, _session_or_404(db, session_id), host=host, version=version, method=method)


_EXPORT_FORMATS = {"fcpxml": NleFormat.FCPXML, "xmeml": NleFormat.XMEML, "edl": NleFormat.EDL}


@router.get("/sessions/{session_id}/export", response_model=ExportFileOut)
def export_session(
    session_id: UUID,
    db: SessionDep,
    state: StateDep,
    format: str = "fcpxml",
    version: int | None = Query(default=None, ge=1),
) -> ExportFileOut:
    """Write the plan as a file the host can import (Rule C fallback)."""
    if format not in _EXPORT_FORMATS:
        raise PluginError(
            ErrorCode.NOT_AVAILABLE,
            f"export format {format!r} is not available",
            f"use one of {sorted(_EXPORT_FORMATS)}",
        )
    row = _session_or_404(db, session_id)
    plan = _plan(db, row, host=HostApp.GENERIC, version=version, method=None)
    fmt = _EXPORT_FORMATS[format]
    project_id = UUID(row.project_id)
    stem = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in plan.sequence.name)
    out = state.storage.exports_dir(project_id) / f"{stem}{EXTENSIONS[fmt]}"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(write_nle(plan_to_timeline(plan), fmt), encoding="utf-8")
    db.add(
        ExportRow(
            id=str(uuid4()),
            project_id=row.project_id,
            job_id=None,
            kind=fmt.value,
            path=str(out),
            preset=None,
            input_hash=None,
            frames=plan.sequence.duration_frames,
        )
    )
    db.commit()
    return ExportFileOut(
        format=fmt.value,
        path=str(out),
        cutlist_version=plan.cutlist_version,
        warnings=plan.warnings,
    )


@router.post("/sessions/{session_id}/social")
def social_clips(session_id: UUID, body: SocialIn, db: SessionDep) -> dict[str, Any]:
    """Social clips (in/out -> one plan per aspect ratio) arrive in PL5."""
    _session_or_404(db, session_id)
    raise PluginError(
        ErrorCode.NOT_AVAILABLE,
        "social clips are not available in this engine yet",
        "update Multicam Studio",
        status_code=501,
    )


@router.post("/sessions/{session_id}/feedback", response_model=FeedbackOut)
def feedback(session_id: UUID, body: FeedbackIn, db: SessionDep, state: StateDep) -> FeedbackOut:
    """Store the editor's final timeline next to the auto edit ("learn my style", PL8)."""
    row = _session_or_404(db, session_id)
    cut_row = _cutlist_row(db, row.project_id, body.plan.cutlist_version)
    auto = [s.start_frame for s in CutList.model_validate(cut_row.data).segments[1:]]
    final = [e.start for e in body.plan.video_events[1:]]
    kept = sum(1 for c in auto if any(abs(c - f) <= 2 for f in final))
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    path = state.storage.artifact_path(UUID(row.project_id), f"feedback-{stamp}.json")
    path.write_text(
        json.dumps({"note": body.note, "plan": body.plan.model_dump(mode="json")}),
        encoding="utf-8",
    )
    return FeedbackOut(
        stored=True, path=str(path), cuts_auto=len(auto), cuts_final=len(final), cuts_kept=kept
    )


# ------------------------------------------------------------------ presets
@router.get("/presets", response_model=list[PresetOut])
def list_presets(db: SessionDep) -> list[PresetOut]:
    return presets_router.list_presets(db)


@router.post("/presets", response_model=PresetOut, status_code=status.HTTP_201_CREATED)
def create_preset(body: UserPresetIn, db: SessionDep) -> PresetOut:
    return presets_router.create_preset(body, db)
