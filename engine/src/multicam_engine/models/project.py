"""Project, Clip and related types."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Final, Literal
from uuid import UUID, uuid4

from pydantic import AwareDatetime, Field, field_validator, model_validator

from multicam_engine.models._base import StrictModel
from multicam_engine.models.time import Rational

SCHEMA_VERSION: Final = 1


class ClipRole(StrEnum):
    SPEAKER = "speaker"  # a camera pointed at one person
    WIDE = "wide"  # a camera showing everyone
    BROLL = "broll"  # never auto-selected; manual use only


class Preset(StrEnum):
    CALM = "calm"
    BALANCED = "balanced"
    DYNAMIC = "dynamic"


class MediaInfo(StrictModel):
    """Facts about a source file, read with ffprobe (Phase 1)."""

    fps: Rational
    is_vfr: bool
    duration_frames: int = Field(ge=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    video_codec: str
    audio_codec: str | None = None
    audio_sample_rate: int | None = Field(default=None, gt=0)
    audio_channels: int = Field(default=0, ge=0)


class SyncResult(StrictModel):
    """How a clip lines up with the project's reference clip.

    Sign convention (shared with ``benchmark.GroundTruth``):
        ``offset_samples`` = position of an event in THIS clip
                             minus position of the same event in the REFERENCE clip.
        Positive  -> this clip started recording EARLIER than the reference.
        Negative  -> this clip started recording LATER than the reference.

    ``drift_ppm``: how much faster this clip's clock runs than the reference,
    in parts per million. A value of +100 means the clip accumulates 0.36 s
    of extra duration per hour. This is a model parameter, not a timeline
    position, so a float is acceptable here.
    """

    reference_clip_id: UUID
    offset_samples: int
    sample_rate: int = Field(gt=0)
    drift_ppm: float = 0.0
    confidence: float = Field(ge=0.0, le=1.0)


class Clip(StrictModel):
    id: UUID = Field(default_factory=uuid4)
    path: str = Field(min_length=1, description="Absolute path; files are referenced in place")
    role: ClipRole = ClipRole.SPEAKER
    speaker_label: str | None = None
    media: MediaInfo | None = None
    sync: SyncResult | None = None


class OutputSettings(StrictModel):
    fps: Rational
    width: int = Field(gt=0)
    height: int = Field(gt=0)

    @field_validator("width", "height")
    @classmethod
    def _even(cls, value: int) -> int:
        # H.264/HEVC with 4:2:0 chroma require even dimensions.
        if value % 2:
            raise ValueError("must be an even number")
        return value


def _utc_now() -> datetime:
    return datetime.now(UTC)


class Project(StrictModel):
    schema_version: Literal[1] = SCHEMA_VERSION
    id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=1, max_length=200)
    output: OutputSettings
    preset: Preset = Preset.BALANCED
    clips: list[Clip] = Field(default_factory=list)
    reference_clip_id: UUID | None = None
    created_at: AwareDatetime = Field(default_factory=_utc_now)

    @model_validator(mode="after")
    def _check_clips(self) -> Project:
        ids = [c.id for c in self.clips]
        if len(ids) != len(set(ids)):
            raise ValueError("clip ids must be unique")
        if self.reference_clip_id is not None and self.reference_clip_id not in ids:
            raise ValueError("reference_clip_id must be one of the project's clips")
        return self

    def clip(self, clip_id: UUID) -> Clip:
        for c in self.clips:
            if c.id == clip_id:
                return c
        raise KeyError(f"no clip with id {clip_id}")
