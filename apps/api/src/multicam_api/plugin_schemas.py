"""Request / response models of the Plugin API v1 (``/api/plugin/v1``, D76).

Versioned separately from the app API: a breaking change means ``/v2``, served
next to ``/v1`` for a year. Everything here is additive-only within v1.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import Field

from multicam_api.schemas import ApiModel, JobOut, ProjectLayout
from multicam_api.services.projects import FileStatus
from multicam_engine.decide.presets import SwitchSettings
from multicam_engine.editplan import EditPlan, HostApp, PlanMethod
from multicam_engine.models.project import CameraLayout, ClipRole, Preset, Speaker
from multicam_engine.models.time import Rational

PLUGIN_API_VERSION = "1.0.0"


class ErrorCode(StrEnum):
    """Stable error codes plugins can switch on."""

    MEDIA_OFFLINE = "media_offline"
    UNSUPPORTED_CODEC = "unsupported_codec"
    SYNC_LOW_CONFIDENCE = "sync_low_confidence"
    NO_SPEECH = "no_speech"
    SETUP_REQUIRED = "setup_required"
    NO_PLAN = "no_plan"
    NOT_FOUND = "not_found"
    INVALID_REQUEST = "invalid_request"
    NOT_AVAILABLE = "not_available"
    ENGINE_BUSY = "engine_busy"
    LICENCE_REQUIRED = "licence_required"
    JOB_FAILED = "job_failed"


class PluginErrorOut(ApiModel):
    code: ErrorCode
    message: str
    hint: str = ""


# ------------------------------------------------------------------ handshake
class ModelsAvailable(ApiModel):
    vad: bool
    face: bool
    asr: bool = False


class LicenceInfo(ApiModel):
    status: Literal["dev", "trial", "active", "expired", "missing"] = "dev"
    plan: str | None = None


class Handshake(ApiModel):
    engine_version: str
    api_version: str = PLUGIN_API_VERSION
    capabilities: list[str]
    models: ModelsAvailable
    licence: LicenceInfo
    data_dir: str
    pid: int


# ------------------------------------------------------------------ sessions
class HostInfo(ApiModel):
    app: HostApp
    version: str = Field(default="", max_length=40)
    os: Literal["mac", "windows", "linux", ""] = ""


class HostSequence(ApiModel):
    fps: Rational
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    name: str | None = Field(default=None, max_length=200)


class SessionClipIn(ApiModel):
    """A clip as the host sees it. Frames are at the host *sequence* rate."""

    path: str = Field(min_length=1)
    kind: Literal["video", "audio"] = Field(
        default="video", description="audio = a sound-only mic / recorder track"
    )
    host_ref: str | None = Field(default=None, max_length=300)
    track: int | None = Field(default=None, ge=1)
    record_start_frame: int = Field(
        default=0, description="Sequence frame where the clip item starts"
    )
    in_frame: int = Field(
        default=0, ge=0, description="Media offset of the clip item's first frame"
    )
    out_frame: int | None = Field(default=None, ge=0)
    audio_channels: int | None = Field(default=None, ge=0)
    label: str | None = Field(default=None, max_length=100)


class SessionCreate(ApiModel):
    host: HostInfo
    host_sequence_id: str | None = Field(
        default=None, max_length=200, description="Re-sending the same id reuses the session"
    )
    sequence: HostSequence
    already_synced: bool = Field(
        default=False, description="Clips come from a synced sequence: skip audio sync"
    )
    clips: list[SessionClipIn] = Field(min_length=1, max_length=20)


class SessionState(StrEnum):
    SETUP = "setup"  # waiting for the user to run
    RUNNING = "running"
    READY = "ready"  # a plan can be fetched
    FAILED = "failed"


class SessionClipOut(ApiModel):
    clip_id: UUID
    path: str
    name: str
    kind: Literal["video", "audio"]
    role: ClipRole
    label: str | None
    host_ref: str | None
    track: int | None
    file_status: FileStatus
    synced: bool
    sync_confidence: float | None


class PlanSummary(ApiModel):
    cutlist_version: int
    source: str
    cuts: int
    duration_frames: int
    low_confidence_cuts: int


class SessionOut(ApiModel):
    id: UUID
    project_id: UUID
    reused: bool = False
    host: HostInfo
    host_sequence_id: str | None
    already_synced: bool
    method: PlanMethod
    state: SessionState
    name: str
    clips: list[SessionClipOut]
    speakers: list[Speaker]
    cameras: list[CameraLayout]
    layout_custom: bool
    preset: Preset
    switch: SwitchSettings
    switch_custom: bool
    job: JobOut | None
    plan: PlanSummary | None
    warnings: list[str]


class RoleIn(ApiModel):
    clip_id: UUID
    role: ClipRole
    speaker_label: str | None = Field(default=None, max_length=100)


class SessionSetup(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    roles: list[RoleIn] | None = Field(
        default=None, description="Quick setup: a role (+ name) per clip"
    )
    layout: ProjectLayout | None = None
    reset_layout: bool = False
    preset: Preset | None = None
    switch: SwitchSettings | None = None
    method: PlanMethod | None = None


RunStep = Literal["sync", "analyze", "decide", "reframe"]


class RunIn(ApiModel):
    steps: Literal["auto"] | list[RunStep] = Field(
        default="auto", description='"auto" = everything; or exactly one step, e.g. ["decide"]'
    )
    vad: Literal["auto", "silero", "energy"] = "auto"
    framing: bool = Field(default=False, description="Also auto-frame (faces, punch-ins)")


class RunOut(ApiModel):
    job_id: UUID
    kind: str
    events_url: str


class ExportFileOut(ApiModel):
    format: str
    path: str
    cutlist_version: int
    warnings: list[str]


class FeedbackIn(ApiModel):
    plan: EditPlan = Field(description="The editor's final timeline, read back from the host")
    note: str | None = Field(default=None, max_length=2000)


class FeedbackOut(ApiModel):
    stored: bool
    path: str
    cuts_auto: int
    cuts_final: int
    cuts_kept: int = Field(description="Auto cuts the editor kept (within 2 frames)")


SocialAspect = Literal["16:9", "4:5", "9:16", "1:1"]


class WatermarkIn(ApiModel):
    path: str = Field(description="PNG / JPEG / GIF / WebP (or a short video)")
    corner: Literal["top_left", "top_right", "bottom_left", "bottom_right", "center"] = (
        "bottom_right"
    )
    size: float = Field(default=0.18, gt=0.0, le=1.0, description="Fraction of the frame width")
    opacity: float = Field(default=0.9, ge=0.0, le=1.0)
    margin: float = Field(default=0.04, ge=0.0, le=0.4, description="Fraction of the width")


class EndPageIn(ApiModel):
    path: str = Field(description="A still or a video appended after the clip")
    seconds: float = Field(default=3.0, gt=0.0, le=60.0)


class SocialIn(ApiModel):
    in_frame: int = Field(ge=0, description="Plan frame where the clip starts")
    out_frame: int = Field(gt=0, description="Plan frame where it ends (exclusive)")
    aspects: list[SocialAspect] = Field(min_length=1)
    name: str | None = Field(default=None, min_length=1, max_length=120)
    watermark: WatermarkIn | None = None
    end_page: EndPageIn | None = None
    jump_cuts: bool = Field(default=False, description="Ripple out the approved removals")
    version: int | None = Field(default=None, ge=1, description="Cutlist version (latest)")
    xml: bool = Field(default=True, description="Also write an xmeml per aspect (Premiere)")


class RemovalOut(ApiModel):
    index: int = Field(description="Position in the cutlist's removals (for PATCH)")
    start: int
    end: int
    kind: str
    approved: bool
    seconds: float


class RemovalsOut(ApiModel):
    cutlist_version: int
    duration_frames: int
    removed_frames: int = Field(description="Approved removals only")
    removed_seconds: float
    removals: list[RemovalOut]


class RemovalsPatch(ApiModel):
    approve: list[int] = Field(default_factory=list)
    reject: list[int] = Field(default_factory=list)
    all: bool | None = Field(default=None, description="Approve (true) / reject (false) all first")


class SocialClipOut(ApiModel):
    aspect: SocialAspect
    name: str
    width: int
    height: int
    duration_frames: int
    plan: EditPlan
    xml_path: str | None = Field(description="xmeml of this clip (import fallback)")
    render_path: str = Field(description="Suggested output file for the batch export")


class SocialOut(ApiModel):
    clips: list[SocialClipOut]
    export_dir: str
    warnings: list[str]
