"""FastAPI application factory.

Startup (lifespan): create the data folder, run database migrations, recover jobs
interrupted by a crash/quit, start the in-process job queue.
"""

from __future__ import annotations

import hmac
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select, update

from multicam_api import __version__
from multicam_api.config import Settings
from multicam_api.db.migrate import upgrade
from multicam_api.db.models import JobRow, utc_now
from multicam_api.db.session import Database
from multicam_api.infra.queue import HueyJobQueue, JobQueue
from multicam_api.infra.storage import LocalStorage
from multicam_api.jobs.runner import JobRunner
from multicam_api.routers import clips, cutlists, exports, jobs, projects, system
from multicam_api.schemas import JobStatus
from multicam_api.state import AppState

log = logging.getLogger(__name__)

TOKEN_HEADER = "X-Multicam-Token"
OPEN_PATHS = ("/api/system/health",)


def recover_jobs(db: Database, queue: JobQueue) -> int:
    """Jobs 'running' when the app last stopped failed; 'queued' ones run again."""
    with db.transaction() as s:
        s.execute(
            update(JobRow)
            .where(JobRow.status == JobStatus.RUNNING.value)
            .values(
                status=JobStatus.FAILED.value,
                error="interrupted: the app was closed while this job was running",
                message="interrupted",
                finished_at=utc_now(),
            )
        )
        queued = s.scalars(
            select(JobRow.id)
            .where(JobRow.status == JobStatus.QUEUED.value)
            .order_by(JobRow.created_at)
        ).all()
    if isinstance(queue, HueyJobQueue):
        queue.flush()  # the database, not the old queue file, decides what runs
    for job_id in queued:
        queue.submit(UUID(job_id))
    return len(queued)


def build_state(settings: Settings, queue: JobQueue | None = None) -> AppState:
    db = Database(settings.db_path)
    storage = LocalStorage(settings.storage_dir)
    holder: dict[str, JobQueue] = {}
    runner = JobRunner(db, storage, settings, lambda job_id: holder["q"].cancel_event(job_id))
    holder["q"] = queue or HueyJobQueue(settings.queue_path, runner.run, workers=settings.workers)
    return AppState(settings=settings, db=db, storage=storage, queue=holder["q"], runner=runner)


def create_app(settings: Settings | None = None, queue: JobQueue | None = None) -> FastAPI:
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        state = build_state(settings, queue)
        upgrade(state.db.engine)
        app.state.ctx = state
        resubmitted = recover_jobs(state.db, state.queue)
        state.queue.start()
        log.info("API ready (data: %s, %d job(s) resumed)", settings.data_dir, resubmitted)
        try:
            yield
        finally:
            state.queue.stop()
            state.db.dispose()

    app = FastAPI(
        title="Multicam Studio API",
        version=__version__,
        description="Local backend: projects, clips, jobs (sync, auto-edit, render).",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_methods=["*"],
        allow_headers=["*"],
    )

    if settings.token:
        expected = settings.token

        @app.middleware("http")
        async def require_token(
            request: Request, call_next: Callable[[Request], Awaitable[Response]]
        ) -> Response:
            path = request.url.path
            if request.method != "OPTIONS" and path.startswith("/api") and path not in OPEN_PATHS:
                given = request.headers.get(TOKEN_HEADER) or request.query_params.get("token") or ""
                if not hmac.compare_digest(given, expected):
                    return JSONResponse({"detail": "missing or wrong API token"}, status_code=401)
            return await call_next(request)

    for module in (system, projects, clips, cutlists, jobs, exports):
        app.include_router(module.router)
    return app
