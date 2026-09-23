"""The CutList: the single source of truth for an edit.

All positions are integer frames at ``CutList.fps`` (the project's output rate).
Segments cover the timeline contiguously from frame 0 with no gaps or overlaps.
"""

from __future__ import annotations

import bisect
from enum import StrEnum
from typing import TYPE_CHECKING, Literal
from uuid import UUID

from pydantic import Field, model_validator

from multicam_engine.models._base import StrictModel
from multicam_engine.models.project import SCHEMA_VERSION
from multicam_engine.models.time import Rational

if TYPE_CHECKING:
    from multicam_engine.models.project import Project


class SegmentSource(StrEnum):
    AUTO = "auto"
    MANUAL = "manual"


class Reframe(StrictModel):
    """Crop/zoom for a segment. Normalized coordinates (0..1) of the crop center."""

    cx: float = Field(ge=0.0, le=1.0)
    cy: float = Field(ge=0.0, le=1.0)
    scale: float = Field(ge=1.0, le=4.0)


class _FrameRange(StrictModel):
    start_frame: int = Field(ge=0)
    end_frame: int = Field(gt=0, description="Exclusive")

    @model_validator(mode="after")
    def _ordered(self) -> _FrameRange:
        if self.end_frame <= self.start_frame:
            raise ValueError(
                f"end_frame ({self.end_frame}) must be > start_frame ({self.start_frame})"
            )
        return self

    @property
    def duration_frames(self) -> int:
        return self.end_frame - self.start_frame


class Segment(_FrameRange):
    clip_id: UUID
    source: SegmentSource = SegmentSource.AUTO
    reframe: Reframe | None = None


class RemovalKind(StrEnum):
    FILLER = "filler"
    SILENCE = "silence"
    MANUAL = "manual"


class Removal(_FrameRange):
    kind: RemovalKind
    approved: bool = False


class AudioMode(StrEnum):
    MIX = "mix"  # mix all clips' audio (per-clip gain)
    SINGLE = "single"  # use one clip's audio only


class AudioConfig(StrictModel):
    mode: AudioMode = AudioMode.MIX
    gains_db: dict[UUID, float] = Field(default_factory=dict)
    single_clip_id: UUID | None = None

    @model_validator(mode="after")
    def _single_needs_clip(self) -> AudioConfig:
        if self.mode is AudioMode.SINGLE and self.single_clip_id is None:
            raise ValueError("single_clip_id is required when mode is 'single'")
        return self


class CutList(StrictModel):
    schema_version: Literal[1] = SCHEMA_VERSION
    version: int = Field(default=1, ge=1, description="Edit revision; bumps on every change")
    project_id: UUID
    fps: Rational
    segments: list[Segment] = Field(min_length=1)
    removals: list[Removal] = Field(default_factory=list)
    audio: AudioConfig = Field(default_factory=AudioConfig)

    @model_validator(mode="after")
    def _check_timeline(self) -> CutList:
        expected = 0
        for i, seg in enumerate(self.segments):
            if seg.start_frame != expected:
                kind = "gap" if seg.start_frame > expected else "overlap"
                raise ValueError(
                    f"segment {i}: {kind} — starts at frame {seg.start_frame}, expected {expected}"
                )
            expected = seg.end_frame

        prev_end = 0
        for i, rem in enumerate(self.removals):
            if rem.start_frame < prev_end:
                raise ValueError(f"removal {i}: overlaps or is out of order")
            if rem.end_frame > self.duration_frames:
                raise ValueError(f"removal {i}: extends past end of timeline")
            prev_end = rem.end_frame
        return self

    @property
    def duration_frames(self) -> int:
        return self.segments[-1].end_frame

    def segment_at(self, frame: int) -> Segment:
        """Segment containing ``frame`` (O(log n))."""
        if not 0 <= frame < self.duration_frames:
            raise IndexError(f"frame {frame} outside timeline [0, {self.duration_frames})")
        starts = [s.start_frame for s in self.segments]
        return self.segments[bisect.bisect_right(starts, frame) - 1]

    def check_against(self, project: Project) -> None:
        """Cross-validate with a project. Raises ``ValueError`` on mismatch."""
        if self.project_id != project.id:
            raise ValueError("cutlist belongs to a different project")
        if self.fps != project.output.fps:
            raise ValueError(f"cutlist fps {self.fps} != project output fps {project.output.fps}")
        known = {c.id for c in project.clips}
        used = {s.clip_id for s in self.segments} | set(self.audio.gains_db)
        if self.audio.single_clip_id is not None:
            used.add(self.audio.single_clip_id)
        unknown = used - known
        if unknown:
            raise ValueError(f"unknown clip ids: {sorted(map(str, unknown))}")
