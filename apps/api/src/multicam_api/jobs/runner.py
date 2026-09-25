"""Runs one job: status bookkeeping, throttled progress, cancellation, errors.

What each kind actually does lives in ``multicam_api.jobs.steps``.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Any, cast
from uuid import UUID

from sqlalchemy import CursorResult, update

from multicam_api.config import Settings
from multicam_api.db.models import JobRow, utc_now
from multicam_api.db.session import Database
from multicam_api.infra.storage import StorageBackend
from multicam_api.jobs.context import JobCancelledError, JobContext, JobFailedError
from multicam_api.jobs.steps import STEPS
from multicam_api.schemas import JobKind, JobStatus

log = logging.getLogger(__name__)


class JobRunner:
    def __init__(
        self,
        db: Database,
        storage: StorageBackend,
        settings: Settings,
        cancel_event_for: Callable[[UUID], threading.Event],
    ) -> None:
        self.db = db
        self.storage = storage
        self.settings = settings
        self._cancel_event_for = cancel_event_for

    def _claim(self, job_id: UUID) -> JobRow | None:
        """queued -> running, atomically (a cancel may have won the race)."""
        with self.db.transaction() as s:
            result = cast(
                "CursorResult[Any]",
                s.execute(
                    update(JobRow)
                    .where(JobRow.id == str(job_id), JobRow.status == JobStatus.QUEUED.value)
                    .values(status=JobStatus.RUNNING.value, started_at=utc_now(), stage="starting")
                ),
            )
            return s.get(JobRow, str(job_id)) if result.rowcount else None

    def _finish(
        self,
        job_id: UUID,
        status: JobStatus,
        *,
        result: dict[str, Any] | None = None,
        error: str | None = None,
        message: str = "",
    ) -> None:
        values: dict[str, Any] = {
            "status": status.value,
            "finished_at": utc_now(),
            "message": message,
            "error": error,
        }
        if result is not None:
            values["result"] = result
        if status is JobStatus.SUCCEEDED:
            values.update(progress=1.0, stage="done")
        with self.db.transaction() as s:
            s.execute(update(JobRow).where(JobRow.id == str(job_id)).values(**values))

    def run(self, job_id: UUID) -> None:
        row = self._claim(job_id)
        if row is None:
            return  # cancelled while queued, or unknown
        ctx = JobContext(
            job_id=job_id,
            project_id=UUID(row.project_id),
            kind=JobKind(row.kind),
            params=dict(row.params),
            db=self.db,
            storage=self.storage,
            settings=self.settings,
            cancel_event=self._cancel_event_for(job_id),
        )
        if row.cancel_requested:
            ctx.cancel_event.set()
        try:
            result = STEPS[ctx.kind](ctx)
        except JobCancelledError:
            self._finish(job_id, JobStatus.CANCELLED, message="cancelled")
        except JobFailedError as exc:
            self._finish(job_id, JobStatus.FAILED, error=str(exc), message=str(exc))
        except Exception as exc:
            if ctx.cancel_event.is_set():
                self._finish(job_id, JobStatus.CANCELLED, message="cancelled")
                return
            log.exception("job %s (%s) failed", job_id, ctx.kind.value)
            text = str(exc) or exc.__class__.__name__
            self._finish(job_id, JobStatus.FAILED, error=text, message=text)
        else:
            if ctx.warnings:
                result = {**result, "warnings": ctx.warnings}
            self._finish(job_id, JobStatus.SUCCEEDED, result=result, message="done")
