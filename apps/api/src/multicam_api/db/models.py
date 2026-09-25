"""Database tables (SQLAlchemy 2.0, SQLite now, PostgreSQL in Phase 13).

Engine objects (Project, Clip, CutList, MediaInfo, SyncResult) are stored as JSON
produced by their Pydantic models, so the engine's validation is the single
source of truth. Only what we query on gets its own column.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, ClassVar

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    TypeDecorator,
    UniqueConstraint,
)
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator[datetime]):
    """Timezone-aware UTC datetimes, also on SQLite (which drops the zone)."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetime")
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        return value.replace(tzinfo=UTC) if value is not None else None


class Base(DeclarativeBase):
    type_annotation_map: ClassVar[dict[Any, Any]] = {dict[str, Any]: JSON, datetime: UTCDateTime}


class ProjectRow(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    preset: Mapped[str] = mapped_column(String(20))
    output: Mapped[dict[str, Any]]  # OutputSettings
    output_custom: Mapped[bool] = mapped_column(Boolean, default=False)
    reference_clip_id: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(default=utc_now, onupdate=utc_now)

    clips: Mapped[list[ClipRow]] = relationship(
        back_populates="project", cascade="all, delete-orphan", order_by="ClipRow.position"
    )


class ClipRow(Base):
    __tablename__ = "clips"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    path: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(10))
    speaker_label: Mapped[str | None] = mapped_column(String(100))
    media: Mapped[dict[str, Any] | None] = mapped_column(JSON)  # MediaInfo
    sync: Mapped[dict[str, Any] | None] = mapped_column(JSON)  # SyncResult
    file_size: Mapped[int | None] = mapped_column(BigInteger)
    file_mtime_ns: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(default=utc_now)

    project: Mapped[ProjectRow] = relationship(back_populates="clips")


class CutListRow(Base):
    """Every edit is a new version (undo/redo in Phase 7)."""

    __tablename__ = "cutlists"
    __table_args__ = (UniqueConstraint("project_id", "version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(Integer)
    data: Mapped[dict[str, Any]]  # CutList
    source: Mapped[str] = mapped_column(String(10))  # auto | manual
    input_hash: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(default=utc_now)


class JobRow(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(12), index=True)
    stage: Mapped[str] = mapped_column(String(40), default="")
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    message: Mapped[str] = mapped_column(Text, default="")
    params: Mapped[dict[str, Any]]
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    input_hash: Mapped[str | None] = mapped_column(String(64))
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    retry_of: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(default=utc_now)
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]


class ExportRow(Base):
    __tablename__ = "exports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    job_id: Mapped[str | None] = mapped_column(String(36))
    kind: Mapped[str] = mapped_column(String(20))  # video (Phase 3); fcpxml/edl/srt later
    path: Mapped[str] = mapped_column(Text)
    preset: Mapped[str | None] = mapped_column(String(40))
    input_hash: Mapped[str | None] = mapped_column(String(64))
    frames: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(default=utc_now)


class StepCacheRow(Base):
    """Last successful inputs of each pipeline step, so unchanged steps are skipped."""

    __tablename__ = "step_cache"
    __table_args__ = (UniqueConstraint("project_id", "step"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    step: Mapped[str] = mapped_column(String(20))
    input_hash: Mapped[str] = mapped_column(String(64))
    result: Mapped[dict[str, Any]]
    created_at: Mapped[datetime] = mapped_column(default=utc_now, onupdate=utc_now)
