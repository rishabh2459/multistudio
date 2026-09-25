"""Rows <-> engine models, file checks and cache keys."""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from multicam_api.db.models import ClipRow, CutListRow, ProjectRow
from multicam_engine.models import Clip, CutList, OutputSettings, Project
from multicam_engine.models.project import ClipRole, MediaInfo, Preset, SyncResult


class FileStatus(StrEnum):
    OK = "ok"
    MISSING = "missing"  # moved or deleted: relink with PATCH /api/clips/{id}
    CHANGED = "changed"  # same path, different file (size/mtime): re-probe + re-sync
    UNKNOWN = "unknown"  # never probed


def file_stat(path: str) -> tuple[int, int] | None:
    try:
        st = Path(path).stat()
    except OSError:
        return None
    return st.st_size, st.st_mtime_ns


def file_status(clip: ClipRow) -> FileStatus:
    stat = file_stat(clip.path)
    if stat is None:
        return FileStatus.MISSING
    if clip.file_size is None:
        return FileStatus.UNKNOWN
    if stat != (clip.file_size, clip.file_mtime_ns):
        return FileStatus.CHANGED
    return FileStatus.OK


def clip_to_engine(row: ClipRow) -> Clip:
    return Clip(
        id=UUID(row.id),
        path=row.path,
        role=ClipRole(row.role),
        speaker_label=row.speaker_label,
        media=MediaInfo.model_validate(row.media) if row.media else None,
        sync=SyncResult.model_validate(row.sync) if row.sync else None,
    )


def project_to_engine(row: ProjectRow) -> Project:
    return Project(
        id=UUID(row.id),
        name=row.name,
        output=OutputSettings.model_validate(row.output),
        preset=Preset(row.preset),
        clips=[clip_to_engine(c) for c in row.clips],
        reference_clip_id=UUID(row.reference_clip_id) if row.reference_clip_id else None,
        created_at=row.created_at,
    )


def latest_cutlist(session: Session, project_id: str) -> CutListRow | None:
    return session.scalars(
        select(CutListRow)
        .where(CutListRow.project_id == project_id)
        .order_by(CutListRow.version.desc())
        .limit(1)
    ).first()


def add_cutlist_version(
    session: Session,
    project_id: str,
    cutlist: CutList,
    *,
    source: str,
    input_hash: str | None = None,
) -> CutListRow:
    previous = latest_cutlist(session, project_id)
    version = (previous.version + 1) if previous else 1
    stored = cutlist.model_copy(update={"version": version})
    row = CutListRow(
        project_id=project_id,
        version=version,
        data=stored.model_dump(mode="json"),
        source=source,
        input_hash=input_hash,
    )
    session.add(row)
    session.flush()
    return row


def stable_hash(data: Any) -> str:
    """SHA-256 of canonical JSON (sorted keys): the cache key of a job's inputs."""
    text = json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(text.encode()).hexdigest()


def clip_fingerprint(row: ClipRow) -> dict[str, Any]:
    return {"id": row.id, "path": row.path, "size": row.file_size, "mtime": row.file_mtime_ns}


def _even(value: int) -> int:
    return max(2, value - value % 2)


def follow_reference(project: ProjectRow) -> None:
    """Unless the user chose output settings, output follows the reference clip."""
    if project.output_custom or project.reference_clip_id is None:
        return
    ref = next((c for c in project.clips if c.id == project.reference_clip_id), None)
    if ref is None or ref.media is None:
        return
    media = MediaInfo.model_validate(ref.media)
    project.output = OutputSettings(
        fps=media.fps, width=_even(media.width), height=_even(media.height)
    ).model_dump(mode="json")
