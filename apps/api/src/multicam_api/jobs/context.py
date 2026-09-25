"""Progress, cancellation and errors as seen from inside a running job."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy import update

from multicam_api.config import Settings
from multicam_api.db.models import JobRow
from multicam_api.db.session import Database
from multicam_api.infra.storage import StorageBackend
from multicam_api.schemas import JobKind

PROGRESS_WRITE_INTERVAL_S = 0.25


class JobCancelledError(Exception):
    """Raised inside a step when the user cancelled the job."""


class JobFailedError(Exception):
    """A step failed for a reason the user can act on (message shown as-is)."""


@dataclass
class JobContext:
    job_id: UUID
    project_id: UUID
    kind: JobKind
    params: dict[str, Any]
    db: Database
    storage: StorageBackend
    settings: Settings
    cancel_event: threading.Event
    _last_write: float = 0.0
    _span: tuple[float, float] = (0.0, 1.0)
    warnings: list[str] = field(default_factory=list)

    # -- progress ----------------------------------------------------------
    def span(self, start: float, end: float) -> None:
        """Map the next ``report`` fractions (0..1) into ``start..end`` of the job."""
        self._span = (start, end)

    def report(
        self, stage: str, fraction: float, message: str = "", *, force: bool = False
    ) -> None:
        """Record progress (at most 4 writes/s) and stop here if cancelled."""
        now = time.monotonic()
        if force or now - self._last_write >= PROGRESS_WRITE_INTERVAL_S:
            self._last_write = now
            lo, hi = self._span
            overall = lo + (hi - lo) * min(1.0, max(0.0, fraction))
            with self.db.transaction() as s:
                s.execute(
                    update(JobRow)
                    .where(JobRow.id == str(self.job_id))
                    .values(stage=stage, progress=overall, message=message)
                )
                row = s.get(JobRow, str(self.job_id))
                if row is not None and row.cancel_requested:
                    self.cancel_event.set()
        self.check_cancel()

    def check_cancel(self) -> None:
        if self.cancel_event.is_set():
            raise JobCancelledError

    def progress_callback(self, stage: str) -> Callable[[float], None]:
        return lambda fraction: self.report(stage, fraction)
