"""EditPlan: the host-neutral edit every NLE plugin applies (D69).

One plan describes the finished edit in the terms an editing application uses:
media items, the live cut ("video events"), every camera on its own track split at
each cut (for the enable/disable method), audio tracks, markers and approved
removals. Adapters for Premiere, Resolve and Final Cut turn the *same* plan into
host operations; the XML exporters write it as a file (the fallback, Rule C).

Positions are integer frames on the plan's sequence (``sequence.fps``). Source
positions are given three ways so no adapter has to do time arithmetic:
frames at the media's own rate, samples at its audio rate, and Premiere ticks
(254 016 000 000 per second, exact for every common frame and sample rate).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal
from uuid import UUID

from pydantic import Field, model_validator

from multicam_engine.models._base import StrictModel
from multicam_engine.models.cutlist import AudioMode, Reframe
from multicam_engine.models.project import ShotType
from multicam_engine.models.time import Rational

PLAN_VERSION: Final = 1
TICKS_PER_SECOND = 254_016_000_000
#: Cuts less sure than this get a marker so the editor checks them first.
LOW_CONFIDENCE = 0.6


class PlanMethod(StrEnum):
    CUTS = "cuts"  # one video track with the live cut
    STACKED_ENABLE = "stacked_enable"  # one track per camera, non-live pieces disabled
    MULTICAM = "multicam"  # native multicam clip + angle switches


class HostApp(StrEnum):
    PREMIERE = "premiere"
    RESOLVE = "resolve"
    FCP = "fcp"
    GENERIC = "generic"


class MarkerColor(StrEnum):
    RED = "red"
    YELLOW = "yellow"
    GREEN = "green"
    BLUE = "blue"


class PlanSequence(StrictModel):
    name: str
    fps: Rational
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    duration_frames: int = Field(gt=0)
    #: Where plan frame 0 sits on the host's own sequence when the clips came from an
    #: already-synced sequence (so a plugin can line the result up with the source).
    host_start_frame: int = 0


class PlanMedia(StrictModel):
    """One source file (camera or recorder)."""

    clip_id: UUID
    path: str
    name: str
    label: str
    host_ref: str | None = Field(default=None, description="The host's id of this media item")
    fps: Rational
    duration_frames: int = Field(ge=0, description="At the media's own frame rate")
    width: int
    height: int
    has_audio: bool
    audio_channels: int
    sample_rate: int
    start_timecode_frames: int = Field(description="Embedded start timecode, own-rate frames")
    has_timecode: bool
    shot: ShotType
    angle: int | None = Field(description="1-based multicam angle (cameras only)")
    video_track: int | None = Field(description="1-based track for stacked_enable")
    audio_track: int | None = Field(description="1-based audio track, if its audio is used")
    record_start_frame: int = Field(
        description="Sequence frame where the media's first frame lands (< 0: starts before "
        "the sequence). Approximate under clock drift; pieces carry exact source times."
    )
    drift_ppm: float = 0.0


class PlanPiece(StrictModel):
    """Sequence frames [start, end) show the media from ``source_in``."""

    start: int = Field(ge=0)
    end: int = Field(gt=0)
    clip_id: UUID
    source_in_frame: int = Field(description="Frames at the media's own rate (nearest)")
    source_in_sample: int = Field(description="Samples at the media's audio rate (nearest)")
    source_in_ticks: int = Field(description="Premiere ticks (254016000000 per second)")

    @model_validator(mode="after")
    def _ordered(self) -> PlanPiece:
        if self.end <= self.start:
            raise ValueError("piece end must be after its start")
        return self

    @property
    def frames(self) -> int:
        return self.end - self.start


class PlanTransformKey(StrictModel):
    """Where the media sits at one sequence frame, in the host's Motion terms.

    ``scale`` is percent of the media's native size (Premiere Motion > Scale) and
    ``x``/``y`` the media's centre in sequence pixels (Motion > Position). Hosts
    interpolate linearly between keys and hold outside them.
    """

    frame: int = Field(ge=0, description="Sequence frame")
    scale: float = Field(gt=0, description="Percent of the media's native size")
    x: float = Field(description="Media centre, sequence pixels from the left")
    y: float = Field(description="Media centre, sequence pixels from the top")


class VideoEvent(PlanPiece):
    """A piece of the live edit (what the viewer sees)."""

    shot: ShotType
    confidence: float | None = None
    reframe: Reframe | None = None
    reframe_vertical: Reframe | None = None
    transform: list[PlanTransformKey] | None = Field(
        default=None, description="Motion keyframes that show the reframe (None: as placed)"
    )


class TrackPiece(PlanPiece):
    enabled: bool = Field(description="Live at this time (stacked_enable)")
    transform: list[PlanTransformKey] | None = None


class PlanOverlay(PlanPiece):
    """A picture above the edit (watermark / logo) on its own video track."""

    track: int = Field(ge=1, description="1 = first track above the cameras")
    opacity: float = Field(default=1.0, ge=0.0, le=1.0)
    transform: list[PlanTransformKey] | None = None


class VideoTrack(StrictModel):
    index: int = Field(ge=1)
    clip_id: UUID
    pieces: list[TrackPiece]


class AudioTrack(StrictModel):
    index: int = Field(ge=1)
    clip_id: UUID
    gain_db: float = 0.0
    pieces: list[PlanPiece]


class PlanMarker(StrictModel):
    frame: int = Field(ge=0)
    duration: int = Field(default=1, ge=1)
    color: MarkerColor = MarkerColor.YELLOW
    kind: Literal["low_confidence", "removal", "note"] = "note"
    note: str = ""


class PlanRemoval(StrictModel):
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    kind: str


class EditPlan(StrictModel):
    plan_version: Literal[1] = PLAN_VERSION
    project_id: UUID
    cutlist_version: int
    host: HostApp = HostApp.GENERIC
    method: PlanMethod = PlanMethod.STACKED_ENABLE
    sequence: PlanSequence
    media: list[PlanMedia]
    video_events: list[VideoEvent]
    video_tracks: list[VideoTrack]
    audio_mode: AudioMode = AudioMode.MIX
    audio_tracks: list[AudioTrack]
    removals: list[PlanRemoval] = Field(default_factory=list, description="Approved only")
    markers: list[PlanMarker] = Field(default_factory=list)
    overlays: list[PlanOverlay] = Field(default_factory=list)
    #: "16:9", "4:5", "9:16" or "1:1" for a social clip; None for the full edit.
    aspect: str | None = None
    #: Approved removals are already taken out (a jump-cut edit).
    rippled: bool = False
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check(self) -> EditPlan:
        known = {m.clip_id for m in self.media}
        pieces: list[PlanPiece] = [*self.video_events]
        for track in self.video_tracks:
            pieces.extend(track.pieces)
        for atrack in self.audio_tracks:
            pieces.extend(atrack.pieces)
        pieces.extend(self.overlays)
        for p in pieces:
            if p.clip_id not in known:
                raise ValueError(f"piece refers to unknown media {p.clip_id}")
            if p.end > self.sequence.duration_frames:
                raise ValueError("piece extends past the end of the sequence")
        last = 0
        for ev in self.video_events:
            if ev.start < last:
                raise ValueError("video events must be sorted and must not overlap")
            last = ev.end
        return self

    def media_by_id(self) -> dict[UUID, PlanMedia]:
        return {m.clip_id: m for m in self.media}

    @property
    def cut_count(self) -> int:
        return max(0, len(self.video_events) - 1)
