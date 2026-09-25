"""Projects: create, list, read, update, delete."""

from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select

from multicam_api.db.models import JobRow, ProjectRow
from multicam_api.routers._common import UNPROCESSABLE, SessionDep, StateDep, project_or_404
from multicam_api.schemas import JobStatus, ProjectCreate, ProjectOut, ProjectSummary, ProjectUpdate
from multicam_api.views import project_out, project_summary
from multicam_engine.models import OutputSettings
from multicam_engine.models.time import FPS_29_97

router = APIRouter(prefix="/api/projects", tags=["projects"])

DEFAULT_OUTPUT = OutputSettings(fps=FPS_29_97, width=1920, height=1080)


@router.get("", response_model=list[ProjectSummary])
def list_projects(session: SessionDep) -> list[ProjectSummary]:
    rows = session.scalars(select(ProjectRow).order_by(ProjectRow.updated_at.desc())).all()
    return [project_summary(r, session) for r in rows]


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(body: ProjectCreate, session: SessionDep) -> ProjectOut:
    row = ProjectRow(
        id=str(uuid4()),
        name=body.name,
        preset=body.preset.value,
        output=(body.output or DEFAULT_OUTPUT).model_dump(mode="json"),
        output_custom=body.output is not None,
    )
    session.add(row)
    session.commit()
    return project_out(row, session)


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(project_id: UUID, session: SessionDep) -> ProjectOut:
    return project_out(project_or_404(session, project_id), session)


@router.patch("/{project_id}", response_model=ProjectOut)
def update_project(project_id: UUID, body: ProjectUpdate, session: SessionDep) -> ProjectOut:
    row = project_or_404(session, project_id)
    if body.name is not None:
        row.name = body.name
    if body.preset is not None:
        row.preset = body.preset.value
    if body.output is not None:
        row.output = body.output.model_dump(mode="json")
        row.output_custom = True
    if body.reference_clip_id is not None and str(body.reference_clip_id) != row.reference_clip_id:
        if str(body.reference_clip_id) not in {c.id for c in row.clips}:
            raise HTTPException(UNPROCESSABLE, "reference must be a clip of this project")
        row.reference_clip_id = str(body.reference_clip_id)
        for clip in row.clips:  # offsets were relative to the old reference
            clip.sync = None
    session.commit()
    return project_out(row, session)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: UUID, session: SessionDep, state: StateDep) -> Response:
    """Deletes the project and its caches/renders in the data folder. Your media is untouched."""
    row = project_or_404(session, project_id)
    busy = session.scalars(
        select(JobRow).where(
            JobRow.project_id == row.id,
            JobRow.status.in_([JobStatus.QUEUED.value, JobStatus.RUNNING.value]),
        )
    ).first()
    if busy is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "project has queued or running jobs; cancel them first"
        )
    session.delete(row)
    session.commit()
    state.storage.delete_project(project_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
