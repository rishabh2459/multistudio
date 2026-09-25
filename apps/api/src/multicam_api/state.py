"""Everything a request or a job needs, created once per app."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING

from fastapi import Request
from sqlalchemy.orm import Session

from multicam_api.config import Settings
from multicam_api.db.session import Database
from multicam_api.infra.queue import JobQueue
from multicam_api.infra.storage import StorageBackend

if TYPE_CHECKING:
    from multicam_api.jobs.runner import JobRunner


@dataclass
class AppState:
    settings: Settings
    db: Database
    storage: StorageBackend
    queue: JobQueue
    runner: JobRunner


def get_state(request: Request) -> AppState:
    state: AppState = request.app.state.ctx
    return state


def get_session(request: Request) -> Iterator[Session]:
    """A session per request. Routes that change data call ``session.commit()``
    themselves before responding (so the client never sees uncommitted state);
    anything left over is rolled back."""
    with get_state(request).db.session() as session:
        try:
            yield session
        finally:
            session.rollback()
