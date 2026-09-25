"""Background jobs: start, list, cancel, retry, and live progress (SSE)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import ValidationError
from sqlalchemy import select
from sse_starlette import EventSourceResponse
from starlette.concurrency import run_in_threadpool

from multicam_api.db.models import JobRow
from multicam_api.routers._common import (
    UNPROCESSABLE,
    SessionDep,
    StateDep,
    job_or_404,
    project_or_404,
)
from multicam_api.schemas import PARAMS_BY_KIND, JobCreate, JobKind, JobOut, JobStatus
from multicam_api.state import AppState
from multicam_api.views import job_out

router = APIRouter(prefix="/api", tags=["jobs"])


def validate_params(kind: JobKind, params: dict[str, Any]) -> dict[str, Any]:
    try:
        return PARAMS_BY_KIND[kind].model_validate(params).model_dump(mode="json")
    except ValidationError as exc:
        raise HTTPException(UNPROCESSABLE, f"invalid params for {kind.value}: {exc}") from exc


def enqueue(state: AppState, session: SessionDep, row: JobRow) -> None:
    session.add(row)
    session.flush()
    session.commit()  # the worker must see the row before it picks the job up
    state.queue.submit(UUID(row.id))


@router.post(
    "/projects/{project_id}/jobs", response_model=JobOut, status_code=status.HTTP_202_ACCEPTED
)
def create_job(project_id: UUID, body: JobCreate, session: SessionDep, state: StateDep) -> JobOut:
    project_or_404(session, project_id)
    row = JobRow(
        id=str(uuid4()),
        project_id=str(project_id),
        kind=body.kind.value,
        status=JobStatus.QUEUED.value,
        params=validate_params(body.kind, body.params),
    )
    enqueue(state, session, row)
    return job_out(row)


@router.get("/projects/{project_id}/jobs", response_model=list[JobOut])
def list_jobs(project_id: UUID, session: SessionDep, limit: int = 50) -> list[JobOut]:
    project_or_404(session, project_id)
    rows = session.scalars(
        select(JobRow)
        .where(JobRow.project_id == str(project_id))
        .order_by(JobRow.created_at.desc())
        .limit(max(1, min(limit, 500)))
    ).all()
    return [job_out(r) for r in rows]


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: UUID, session: SessionDep) -> JobOut:
    return job_out(job_or_404(session, job_id))


@router.post("/jobs/{job_id}/cancel", response_model=JobOut)
def cancel_job(job_id: UUID, session: SessionDep, state: StateDep) -> JobOut:
    """Queued jobs are cancelled at once; running jobs stop at their next checkpoint."""
    row = job_or_404(session, job_id)
    current = JobStatus(row.status)
    if current.finished:
        raise HTTPException(status.HTTP_409_CONFLICT, f"job already {current.value}")
    row.cancel_requested = True
    if current is JobStatus.QUEUED:
        row.status = JobStatus.CANCELLED.value
        row.message = "cancelled before it started"
    state.queue.request_cancel(job_id)
    session.commit()
    return job_out(row)


@router.post("/jobs/{job_id}/retry", response_model=JobOut, status_code=status.HTTP_202_ACCEPTED)
def retry_job(job_id: UUID, session: SessionDep, state: StateDep) -> JobOut:
    """Start a new job with the same kind and parameters as a failed/cancelled one."""
    old = job_or_404(session, job_id)
    if JobStatus(old.status) not in (JobStatus.FAILED, JobStatus.CANCELLED):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "only failed or cancelled jobs can be retried"
        )
    row = JobRow(
        id=str(uuid4()),
        project_id=old.project_id,
        kind=old.kind,
        status=JobStatus.QUEUED.value,
        params=old.params,
        retry_of=old.id,
    )
    enqueue(state, session, row)
    return job_out(row)


# ---------------------------------------------------------------- live progress
def _snapshot(state: AppState, job_id: UUID) -> JobOut | None:
    with state.db.session() as s:
        row = s.get(JobRow, str(job_id))
        return job_out(row) if row else None


def _project_snapshot(state: AppState, project_id: UUID) -> list[JobOut]:
    with state.db.session() as s:
        rows = s.scalars(
            select(JobRow)
            .where(JobRow.project_id == str(project_id))
            .order_by(JobRow.created_at.desc())
            .limit(20)
        ).all()
        return [job_out(r) for r in rows]


def _key(job: JobOut) -> tuple[object, ...]:
    return (job.status, round(job.progress, 3), job.stage, job.message)


@router.get("/jobs/{job_id}/events")
async def job_events(job_id: UUID, request: Request, state: StateDep) -> EventSourceResponse:
    """Server-Sent Events: a ``job`` event whenever the job changes; ends when it finishes."""
    first = await run_in_threadpool(_snapshot, state, job_id)
    if first is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"job {job_id} not found")

    async def stream() -> AsyncIterator[dict[str, str]]:
        job: JobOut | None = first
        last: tuple[object, ...] | None = None
        while job is not None and not await request.is_disconnected():
            if _key(job) != last:
                last = _key(job)
                yield {"event": "job", "data": job.model_dump_json()}
            if job.status.finished:
                return
            await asyncio.sleep(state.settings.sse_interval)
            job = await run_in_threadpool(_snapshot, state, job_id)

    return EventSourceResponse(stream(), ping=15)


@router.get("/projects/{project_id}/events")
async def project_events(
    project_id: UUID, request: Request, state: StateDep, follow: bool = True
) -> EventSourceResponse:
    """Server-Sent Events for the project's recent jobs: first their current state,
    then every change (the UI keeps this open). ``follow=false`` stops after the
    current state."""

    async def stream() -> AsyncIterator[dict[str, str]]:
        seen: dict[UUID, tuple[object, ...]] = {}
        while not await request.is_disconnected():
            for job in reversed(await run_in_threadpool(_project_snapshot, state, project_id)):
                if seen.get(job.id) != _key(job):
                    seen[job.id] = _key(job)
                    yield {"event": "job", "data": job.model_dump_json()}
            if not follow:
                return
            await asyncio.sleep(state.settings.sse_interval)

    with state.db.session() as s:
        project_or_404(s, project_id)
    return EventSourceResponse(stream(), ping=15)
