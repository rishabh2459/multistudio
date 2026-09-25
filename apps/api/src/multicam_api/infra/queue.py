"""Background job queue.

``JobQueue`` is the interface; ``HueyJobQueue`` runs Huey (SQLite storage) with
its worker threads *inside* the API process - the desktop sidecar is a single
process. Phase 13 swaps in Celery + Redis behind the same interface.

The database row is the source of truth for a job; the queue only carries its id.
Cancellation: a queued job is revoked; a running job sees its ``threading.Event``
set (render/sync/analysis check it between steps).
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID

from huey import SqliteHuey
from huey.consumer import Consumer

log = logging.getLogger(__name__)


class JobQueue(Protocol):
    def submit(self, job_id: UUID) -> None: ...

    def cancel_event(self, job_id: UUID) -> threading.Event: ...

    def request_cancel(self, job_id: UUID) -> None: ...

    def start(self) -> None: ...

    def stop(self) -> None: ...


class CancelRegistry:
    """One ``threading.Event`` per job id."""

    def __init__(self) -> None:
        self._events: dict[UUID, threading.Event] = {}
        self._lock = threading.Lock()

    def event(self, job_id: UUID) -> threading.Event:
        with self._lock:
            return self._events.setdefault(job_id, threading.Event())

    def cancel(self, job_id: UUID) -> None:
        self.event(job_id).set()

    def cancel_all(self) -> None:
        with self._lock:
            for event in self._events.values():
                event.set()

    def forget(self, job_id: UUID) -> None:
        with self._lock:
            self._events.pop(job_id, None)


class _EmbeddedConsumer(Consumer):  # type: ignore[misc]
    """Huey consumer that leaves the host process's signal handlers alone."""

    def _set_signal_handlers(self) -> None:
        pass


class HueyJobQueue:
    def __init__(
        self,
        queue_path: Path,
        run_job: Callable[[UUID], None],
        *,
        workers: int = 1,
    ) -> None:
        self._huey = SqliteHuey(name="multicam", filename=str(queue_path))
        self._run_job = run_job
        self._workers = workers
        self._cancel = CancelRegistry()
        self._consumer: Any = None

        def execute(job_id: str) -> None:
            uid = UUID(job_id)
            try:
                self._run_job(uid)
            finally:
                self._cancel.forget(uid)

        self._task: Any = self._huey.task(name="run_job", retries=0)(execute)

    def submit(self, job_id: UUID) -> None:
        self._task(str(job_id))

    def cancel_event(self, job_id: UUID) -> threading.Event:
        return self._cancel.event(job_id)

    def request_cancel(self, job_id: UUID) -> None:
        self._cancel.cancel(job_id)

    def flush(self) -> None:
        """Drop everything still waiting (the database decides what to resubmit)."""
        self._huey.flush()

    def start(self) -> None:
        if self._consumer is not None:
            return
        self._consumer = _EmbeddedConsumer(
            self._huey,
            workers=self._workers,
            periodic=False,
            worker_type="thread",
            initial_delay=0.05,
            backoff=1.2,
            max_delay=0.5,
            check_worker_health=False,
        )
        self._consumer.start()
        log.info("job queue started with %d worker(s)", self._workers)

    def stop(self) -> None:
        if self._consumer is None:
            return
        self._cancel.cancel_all()
        self._consumer.stop(graceful=False)  # running jobs were told to cancel
        self._consumer = None
