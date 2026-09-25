"""Database rows -> API response models."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from sqlalchemy.orm import Session

from multicam_api.db.models import ClipRow, CutListRow, ExportRow, JobRow, ProjectRow
from multicam_api.schemas import (
    ClipOut,
    CutListOut,
    ExportOut,
    JobKind,
    JobOut,
    JobStatus,
    ProjectOut,
    ProjectSummary,
)
from multicam_api.services.projects import file_status, latest_cutlist
from multicam_engine.models import CutList, OutputSettings
from multicam_engine.models.project import ClipRole, MediaInfo, Preset, SyncResult


def clip_out(row: ClipRow, reference_clip_id: str | None) -> ClipOut:
    return ClipOut(
        id=UUID(row.id),
        project_id=UUID(row.project_id),
        path=row.path,
        name=Path(row.path).name,
        role=ClipRole(row.role),
        speaker_label=row.speaker_label,
        media=MediaInfo.model_validate(row.media) if row.media else None,
        sync=SyncResult.model_validate(row.sync) if row.sync else None,
        file_status=file_status(row),
        is_reference=row.id == reference_clip_id,
    )


def project_out(row: ProjectRow, session: Session) -> ProjectOut:
    latest = latest_cutlist(session, row.id)
    return ProjectOut(
        id=UUID(row.id),
        name=row.name,
        preset=Preset(row.preset),
        output=OutputSettings.model_validate(row.output),
        output_custom=row.output_custom,
        reference_clip_id=UUID(row.reference_clip_id) if row.reference_clip_id else None,
        clips=[clip_out(c, row.reference_clip_id) for c in row.clips],
        cutlist_version=latest.version if latest else None,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def project_summary(row: ProjectRow, session: Session) -> ProjectSummary:
    latest = latest_cutlist(session, row.id)
    return ProjectSummary(
        id=UUID(row.id),
        name=row.name,
        preset=Preset(row.preset),
        clip_count=len(row.clips),
        cutlist_version=latest.version if latest else None,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def cutlist_out(row: CutListRow) -> CutListOut:
    return CutListOut(
        version=row.version,
        source=row.source,
        created_at=row.created_at,
        cutlist=CutList.model_validate(row.data),
    )


def job_out(row: JobRow) -> JobOut:
    return JobOut(
        id=UUID(row.id),
        project_id=UUID(row.project_id),
        kind=JobKind(row.kind),
        status=JobStatus(row.status),
        stage=row.stage,
        progress=min(1.0, max(0.0, row.progress)),
        message=row.message,
        params=row.params,
        result=row.result,
        error=row.error,
        retry_of=UUID(row.retry_of) if row.retry_of else None,
        created_at=row.created_at,
        started_at=row.started_at,
        finished_at=row.finished_at,
    )


def export_out(row: ExportRow) -> ExportOut:
    path = Path(row.path)
    exists = path.is_file()
    return ExportOut(
        id=UUID(row.id),
        project_id=UUID(row.project_id),
        job_id=UUID(row.job_id) if row.job_id else None,
        kind=row.kind,
        path=row.path,
        preset=row.preset,
        frames=row.frames,
        exists=exists,
        size_bytes=path.stat().st_size if exists else None,
        created_at=row.created_at,
    )
