"""Where the backend keeps its own files (analysis caches, sync reports, renders).

The user's media is never copied: clips are referenced by path (desktop).
``StorageBackend`` is the seam for Phase 13, where an S3-compatible store
replaces the local folders.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Protocol
from uuid import UUID


class StorageBackend(Protocol):
    def artifact_path(self, project_id: UUID, name: str) -> Path:
        """Local path for a named artifact of a project (parent folder exists)."""
        ...

    def exports_dir(self, project_id: UUID) -> Path: ...

    def delete_project(self, project_id: UUID) -> None: ...


class LocalStorage:
    """``<root>/<project id>/{artifacts,exports}/``."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def _project_dir(self, project_id: UUID) -> Path:
        return self.root / str(project_id)

    def artifact_path(self, project_id: UUID, name: str) -> Path:
        if "/" in name or "\\" in name or name.startswith("."):
            raise ValueError(f"invalid artifact name {name!r}")
        folder = self._project_dir(project_id) / "artifacts"
        folder.mkdir(parents=True, exist_ok=True)
        return folder / name

    def exports_dir(self, project_id: UUID) -> Path:
        folder = self._project_dir(project_id) / "exports"
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def delete_project(self, project_id: UUID) -> None:
        shutil.rmtree(self._project_dir(project_id), ignore_errors=True)
