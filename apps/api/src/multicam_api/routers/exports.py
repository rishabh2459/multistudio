"""Rendered files: list, download/stream, forget."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, HTTPException, Response, status
from fastapi.responses import FileResponse
from sqlalchemy import select

from multicam_api.db.models import ExportRow
from multicam_api.routers._common import SessionDep, export_or_404, project_or_404
from multicam_api.schemas import ExportOut
from multicam_api.views import export_out

router = APIRouter(prefix="/api", tags=["exports"])


@router.get("/projects/{project_id}/exports", response_model=list[ExportOut])
def list_exports(project_id: UUID, session: SessionDep) -> list[ExportOut]:
    project_or_404(session, project_id)
    rows = session.scalars(
        select(ExportRow)
        .where(ExportRow.project_id == str(project_id))
        .order_by(ExportRow.created_at.desc())
    ).all()
    return [export_out(r) for r in rows]


@router.get("/exports/{export_id}/file", response_class=FileResponse)
def download_export(export_id: UUID, session: SessionDep) -> FileResponse:
    """The rendered file (supports HTTP range requests, so a video player can seek)."""
    row = export_or_404(session, export_id)
    path = Path(row.path)
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"file no longer exists: {path}")
    return FileResponse(path, filename=path.name)


@router.delete("/exports/{export_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_export(export_id: UUID, session: SessionDep, delete_file: bool = False) -> Response:
    row = export_or_404(session, export_id)
    if delete_file:
        Path(row.path).unlink(missing_ok=True)
    session.delete(row)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
