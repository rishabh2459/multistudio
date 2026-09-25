"""Lookups shared by the routers (404 when missing)."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from multicam_api.db.models import ClipRow, ExportRow, JobRow, ProjectRow
from multicam_api.state import AppState, get_session, get_state

UNPROCESSABLE = 422  # (Starlette renamed the constant between versions)

SessionDep = Annotated[Session, Depends(get_session)]
StateDep = Annotated[AppState, Depends(get_state)]


def not_found(what: str, ident: UUID) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, f"{what} {ident} not found")


def project_or_404(session: Session, project_id: UUID) -> ProjectRow:
    row = session.get(ProjectRow, str(project_id))
    if row is None:
        raise not_found("project", project_id)
    return row


def clip_or_404(session: Session, clip_id: UUID) -> ClipRow:
    row = session.get(ClipRow, str(clip_id))
    if row is None:
        raise not_found("clip", clip_id)
    return row


def job_or_404(session: Session, job_id: UUID) -> JobRow:
    row = session.get(JobRow, str(job_id))
    if row is None:
        raise not_found("job", job_id)
    return row


def export_or_404(session: Session, export_id: UUID) -> ExportRow:
    row = session.get(ExportRow, str(export_id))
    if row is None:
        raise not_found("export", export_id)
    return row
