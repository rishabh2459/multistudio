"""The edit: latest cutlist, its history, and manual edits (new versions)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from multicam_api.db.models import CutListRow
from multicam_api.routers._common import UNPROCESSABLE, SessionDep, not_found, project_or_404
from multicam_api.schemas import CutListIn, CutListOut, CutListVersion
from multicam_api.services.projects import add_cutlist_version, latest_cutlist, project_to_engine
from multicam_api.views import cutlist_out

router = APIRouter(prefix="/api/projects/{project_id}/cutlist", tags=["cutlist"])


@router.get("", response_model=CutListOut)
def get_cutlist(project_id: UUID, session: SessionDep) -> CutListOut:
    project_or_404(session, project_id)
    row = latest_cutlist(session, str(project_id))
    if row is None:
        raise not_found("cutlist for project", project_id)
    return cutlist_out(row)


@router.get("/versions", response_model=list[CutListVersion])
def list_versions(project_id: UUID, session: SessionDep) -> list[CutListVersion]:
    project_or_404(session, project_id)
    rows = session.scalars(
        select(CutListRow)
        .where(CutListRow.project_id == str(project_id))
        .order_by(CutListRow.version.desc())
    ).all()
    return [
        CutListVersion(
            version=r.version,
            source=r.source,
            segments=len(r.data["segments"]),
            created_at=r.created_at,
        )
        for r in rows
    ]


@router.get("/versions/{version}", response_model=CutListOut)
def get_version(project_id: UUID, version: int, session: SessionDep) -> CutListOut:
    project_or_404(session, project_id)
    row = session.scalars(
        select(CutListRow).where(
            CutListRow.project_id == str(project_id), CutListRow.version == version
        )
    ).first()
    if row is None:
        raise not_found(f"cutlist version {version} of project", project_id)
    return cutlist_out(row)


@router.put("", response_model=CutListOut)
def save_cutlist(project_id: UUID, body: CutListIn, session: SessionDep) -> CutListOut:
    """Save an edited cutlist as a new version (the engine validates it first)."""
    project = project_to_engine(project_or_404(session, project_id))
    try:
        body.cutlist.check_against(project)
    except ValueError as exc:
        raise HTTPException(UNPROCESSABLE, str(exc)) from exc
    row = add_cutlist_version(session, str(project_id), body.cutlist, source="manual")
    session.commit()
    return cutlist_out(row)
