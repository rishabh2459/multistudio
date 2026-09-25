"""Request / response models of the HTTP API (they define the OpenAPI schema)."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from multicam_api.services.projects import FileStatus
from multicam_engine.models import CutList, OutputSettings
from multicam_engine.models.project import ClipRole, MediaInfo, Preset, SyncResult


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ------------------------------------------------------------------ system
class Health(ApiModel):
    status: Literal["ok"] = "ok"
    version: str


class SystemInfo(ApiModel):
    api_version: str
    engine_version: str
    data_dir: str
    ffmpeg: str | None
    ffmpeg_version: str | None
    vad_model_available: bool
    encoders_h264: list[str] | None = Field(description="None until requested with ?encoders=true")
    encoders_hevc: list[str] | None
    render_presets: list[str]


# ------------------------------------------------------------------ clips
class ClipCreate(ApiModel):
    path: str = Field(min_length=1, description="Absolute path; the file is referenced in place")
    role: ClipRole = ClipRole.SPEAKER
    speaker_label: str | None = Field(default=None, max_length=100)


class ClipUpdate(ApiModel):
    role: ClipRole | None = None
    speaker_label: str | None = Field(default=None, max_length=100)
    path: str | None = Field(default=None, min_length=1, description="Relink a moved file")
    force: bool = Field(default=False, description="Relink even if the new file looks different")


class ClipOut(ApiModel):
    id: UUID
    project_id: UUID
    path: str
    name: str
    role: ClipRole
    speaker_label: str | None
    media: MediaInfo | None
    sync: SyncResult | None
    file_status: FileStatus
    is_reference: bool


# ------------------------------------------------------------------ projects
class ProjectCreate(ApiModel):
    name: str = Field(min_length=1, max_length=200)
    preset: Preset = Preset.BALANCED
    output: OutputSettings | None = Field(
        default=None, description="Omit to follow the reference clip's frame rate and size"
    )


class ProjectUpdate(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    preset: Preset | None = None
    output: OutputSettings | None = None
    reference_clip_id: UUID | None = None


class ProjectSummary(ApiModel):
    id: UUID
    name: str
    preset: Preset
    clip_count: int
    cutlist_version: int | None
    created_at: datetime
    updated_at: datetime


class ProjectOut(ApiModel):
    id: UUID
    name: str
    preset: Preset
    output: OutputSettings
    output_custom: bool
    reference_clip_id: UUID | None
    clips: list[ClipOut]
    cutlist_version: int | None
    created_at: datetime
    updated_at: datetime


# ------------------------------------------------------------------ cutlists
class CutListOut(ApiModel):
    version: int
    source: str
    created_at: datetime
    cutlist: CutList


class CutListVersion(ApiModel):
    version: int
    source: str
    segments: int
    created_at: datetime


class CutListIn(ApiModel):
    cutlist: CutList


# ------------------------------------------------------------------ jobs
class JobKind(StrEnum):
    PROBE = "probe"  # read frame rate, duration, audio of every clip
    SYNC = "sync"  # align clips by audio
    ANALYZE = "analyze"  # who speaks when
    DECIDE = "decide"  # camera cuts from the analysis (new cutlist version)
    AUTO = "auto"  # probe + sync + analyze + decide
    RENDER = "render"  # final video from the latest cutlist


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def finished(self) -> bool:
        return self in (JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED)


class AnalyzeParams(ApiModel):
    vad: Literal["auto", "silero", "energy"] = "auto"


class DecideParams(ApiModel):
    preset: Preset | None = Field(default=None, description="Default: the project's preset")


class AutoParams(ApiModel):
    vad: Literal["auto", "silero", "energy"] = "auto"
    preset: Preset | None = None


class RenderParams(ApiModel):
    preset: str = "youtube-1080p"
    encoder: str = "auto"
    output_path: str | None = Field(
        default=None, description="Default: the project's exports folder in the data dir"
    )
    audio_clip_id: UUID | None = Field(default=None, description="Use only this clip's audio")


class EmptyParams(ApiModel):
    pass


PARAMS_BY_KIND: dict[JobKind, type[ApiModel]] = {
    JobKind.PROBE: EmptyParams,
    JobKind.SYNC: EmptyParams,
    JobKind.ANALYZE: AnalyzeParams,
    JobKind.DECIDE: DecideParams,
    JobKind.AUTO: AutoParams,
    JobKind.RENDER: RenderParams,
}


class JobCreate(ApiModel):
    kind: JobKind
    params: dict[str, Any] = Field(default_factory=dict)


class JobOut(ApiModel):
    id: UUID
    project_id: UUID
    kind: JobKind
    status: JobStatus
    stage: str
    progress: float = Field(ge=0.0, le=1.0)
    message: str
    params: dict[str, Any]
    result: dict[str, Any] | None
    error: str | None
    retry_of: UUID | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


# ------------------------------------------------------------------ exports
class ExportOut(ApiModel):
    id: UUID
    project_id: UUID
    job_id: UUID | None
    kind: str
    path: str
    preset: str | None
    frames: int | None
    exists: bool
    size_bytes: int | None
    created_at: datetime


class ErrorOut(ApiModel):
    detail: str
