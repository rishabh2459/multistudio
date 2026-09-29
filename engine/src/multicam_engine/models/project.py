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
#: Most cameras / mics one project may have (AutoPod parity: 10 + 10).
MAX_CAMERAS: Final = 10
MAX_SPEAKERS: Final = 10


class ClipRole(StrEnum):
    SPEAKER = "speaker"  # a camera pointed at one person
    WIDE = "wide"  # a camera showing everyone
    BROLL = "broll"  # never auto-selected; manual use only


class Preset(StrEnum):
    CALM = "calm"
    BALANCED = "balanced"
    DYNAMIC = "dynamic"
    PUNCHY = "punchy"  # reels / high energy: short shots, forced variety


class ShotType(StrEnum):
    """What a camera shows. Switching understands every layout (D74)."""

    SOLO = "solo"  # one person
    TWO = "two"  # two people
    THREE = "three"
    FOUR = "four"
    WIDE = "wide"  # everyone
    BROLL = "broll"  # never auto-selected


class Speaker(StrictModel):
    """A person in the recording and the mic that hears them best."""

    id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=1, max_length=100)
    mic_clip_id: UUID | None = Field(
        default=None, description="Clip whose audio is this person's mic; None: single-mic mode"
    )
    mic_channel: int | None = Field(
        default=None, ge=0, le=31, description="Channel of the mic in a multi-channel file"
    )


class CameraLayout(StrictModel):
    """One camera (clip), what kind of shot it is and who is visible in it."""

    clip_id: UUID
    shot: ShotType
    covers: list[UUID] = Field(default_factory=list, description="Speaker ids in frame")
    priority: float = Field(default=1.0, ge=0.5, le=1.5, description="User bias for this angle")


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
    start_timecode: str | None = Field(
        default=None,
        description="Embedded start timecode (HH:MM:SS:FF, ';' before FF = drop-frame)",
        pattern=r"^\d{2}:\d{2}:\d{2}[:;.]\d{2}$",
    )


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
    #: Explicit people and camera layout. Empty: derived from clip roles
    #: (see ``multicam_engine.layout.resolve_layout``).
    speakers: list[Speaker] = Field(default_factory=list, max_length=MAX_SPEAKERS)
    cameras: list[CameraLayout] = Field(default_factory=list, max_length=MAX_CAMERAS)

    @model_validator(mode="after")
    def _check_clips(self) -> Project:
        ids = [c.id for c in self.clips]
        if len(ids) != len(set(ids)):
            raise ValueError("clip ids must be unique")
        if self.reference_clip_id is not None and self.reference_clip_id not in ids:
            raise ValueError("reference_clip_id must be one of the project's clips")
        known, people = set(ids), {s.id for s in self.speakers}
        if len(people) != len(self.speakers):
            raise ValueError("speaker ids must be unique")
        for spk in self.speakers:
            if spk.mic_clip_id is not None and spk.mic_clip_id not in known:
                raise ValueError(f"speaker {spk.name}: mic clip is not in the project")
        seen: set[UUID] = set()
        for cam in self.cameras:
            if cam.clip_id not in known:
                raise ValueError("camera layout refers to a clip that is not in the project")
            if cam.clip_id in seen:
                raise ValueError("each clip may have only one camera layout")
            seen.add(cam.clip_id)
            if not set(cam.covers) <= people:
                raise ValueError("camera layout covers an unknown speaker")
        if self.cameras and not self.speakers:
            raise ValueError("a camera layout needs the speakers it refers to")
        return self

    def clip(self, clip_id: UUID) -> Clip:
        for c in self.clips:
            if c.id == clip_id:
                return c
        raise KeyError(f"no clip with id {clip_id}")
