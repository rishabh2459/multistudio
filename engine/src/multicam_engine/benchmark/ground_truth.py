"""Ground truth for a test recording (see docs/TEST_FOOTAGE.md).

All times are integer milliseconds. Clap positions are measured in each
clip's OWN file timeline; speech turns are on the REFERENCE clip's timeline.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from multicam_engine.models._base import StrictModel
from multicam_engine.models.project import ClipRole


class GTClip(StrictModel):
    file: str = Field(min_length=1, description="File name inside the recording folder")
    role: ClipRole = ClipRole.SPEAKER
    speaker_label: str | None = None
    clap_start_ms: int = Field(ge=0)
    clap_end_ms: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _claps_ordered(self) -> GTClip:
        if self.clap_end_ms is not None and self.clap_end_ms <= self.clap_start_ms:
            raise ValueError(f"{self.file}: clap_end_ms must be after clap_start_ms")
        return self


class SpeechTurn(StrictModel):
    speaker_label: str = Field(min_length=1)
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)

    @model_validator(mode="after")
    def _ordered(self) -> SpeechTurn:
        if self.end_ms <= self.start_ms:
            raise ValueError("end_ms must be > start_ms")
        return self


class MsRange(StrictModel):
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)

    @model_validator(mode="after")
    def _ordered(self) -> MsRange:
        if self.end_ms <= self.start_ms:
            raise ValueError("end_ms must be > start_ms")
        return self


class GroundTruth(StrictModel):
    schema_version: Literal[1] = 1
    recording_id: str = Field(pattern=r"^T\d+$")
    description: str = ""
    reference_file: str
    clips: list[GTClip] = Field(min_length=2)
    speech: list[SpeechTurn] = Field(default_factory=list)
    annotated_range: MsRange | None = Field(
        default=None,
        description="Window (reference timeline) where speech is fully labeled. "
        "None = whole recording. Speaker-accuracy is scored only inside it.",
    )

    @model_validator(mode="after")
    def _consistent(self) -> GroundTruth:
        files = [c.file for c in self.clips]
        if len(files) != len(set(files)):
            raise ValueError("clip files must be unique")
        if self.reference_file not in files:
            raise ValueError(f"reference_file {self.reference_file!r} is not one of the clips")
        labels = {c.speaker_label for c in self.clips if c.speaker_label}
        for turn in self.speech:
            if turn.speaker_label not in labels:
                raise ValueError(
                    f"speech label {turn.speaker_label!r} does not match any clip "
                    f"(known: {sorted(labels)})"
                )
        return self

    # ------------------------------------------------------------ derived truth
    def clip(self, file: str) -> GTClip:
        for c in self.clips:
            if c.file == file:
                return c
        raise KeyError(file)

    @property
    def reference(self) -> GTClip:
        return self.clip(self.reference_file)

    def true_offset_ms(self, file: str) -> int:
        """Same sign convention as ``SyncResult.offset_samples``:
        positive = this clip started recording earlier than the reference."""
        return self.clip(file).clap_start_ms - self.reference.clap_start_ms

    def true_drift_ppm(self, file: str) -> float | None:
        """Clock drift vs the reference, from the start/end claps. None if unmeasurable."""
        clip, ref = self.clip(file), self.reference
        if clip.clap_end_ms is None or ref.clap_end_ms is None:
            return None
        ref_span = ref.clap_end_ms - ref.clap_start_ms
        clip_span = clip.clap_end_ms - clip.clap_start_ms
        return (clip_span - ref_span) / ref_span * 1_000_000
