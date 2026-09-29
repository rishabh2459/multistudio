"""Editing styles. Built-in presets live here; user presets are stored as
``SwitchSettings`` JSON (API database, ``.mcpreset.json`` files)."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from pydantic import Field

from multicam_engine.models._base import StrictModel
from multicam_engine.models.project import Preset


@dataclass(frozen=True)
class SwitchParams:
    #: No shot is ever shorter than this (except a lone final shot on a tiny clip).
    min_shot_s: float
    #: Price of one cut, in seconds of "right camera on screen". A cut is made only
    #: when it gains more than this, so shorter interjections ("mm-hmm", "right")
    #: never cause one: interruption tolerance / hysteresis.
    switch_delay_s: float
    #: Pauses shorter than this do not end someone's turn.
    bridge_gap_s: float
    #: Cut this long before the new speaker's first word (feels natural, not late).
    lead_s: float
    #: Two people talking over each other this long -> wide shot (if there is one).
    crosstalk_to_wide_s: float
    #: Nobody talking this long -> wide shot (if there is one).
    silence_to_wide_s: float
    #: > 0: a shot longer than this starts paying a growing cost, so auto-edit cuts
    #: to another camera that also shows the speaker (group or wide): variety.
    max_shot_s: float = 0.0
    #: 0 = group / wide shots only when needed, 1 = often ("more wide shots").
    wide_frequency: float = 0.3
    #: Reward of a two/three/four-shot that contains the speaker (a solo scores 1).
    group_reward: float = 0.7


class SwitchSettings(StrictModel):
    """``SwitchParams`` as a validated, serialisable model (user presets, API)."""

    min_shot_s: float = Field(ge=0.3, le=30.0)
    switch_delay_s: float = Field(ge=0.0, le=10.0)
    bridge_gap_s: float = Field(ge=0.0, le=5.0)
    lead_s: float = Field(ge=0.0, le=1.0)
    crosstalk_to_wide_s: float = Field(ge=0.1, le=30.0)
    silence_to_wide_s: float = Field(ge=0.1, le=60.0)
    max_shot_s: float = Field(default=0.0, ge=0.0, le=120.0, description="0 = no limit")
    wide_frequency: float = Field(default=0.3, ge=0.0, le=1.0)
    group_reward: float = Field(default=0.7, ge=0.0, le=0.95)

    def to_params(self) -> SwitchParams:
        return SwitchParams(**self.model_dump())

    @classmethod
    def from_params(cls, params: SwitchParams) -> SwitchSettings:
        return cls(**asdict(params))


PRESETS: dict[Preset, SwitchParams] = {
    Preset.CALM: SwitchParams(
        min_shot_s=4.0,
        switch_delay_s=1.2,
        bridge_gap_s=1.0,
        lead_s=0.15,
        crosstalk_to_wide_s=2.0,
        silence_to_wide_s=4.0,
    ),
    Preset.BALANCED: SwitchParams(
        min_shot_s=2.5,
        switch_delay_s=0.7,
        bridge_gap_s=0.7,
        lead_s=0.15,
        crosstalk_to_wide_s=1.2,
        silence_to_wide_s=3.0,
    ),
    Preset.DYNAMIC: SwitchParams(
        min_shot_s=1.5,
        switch_delay_s=0.4,
        bridge_gap_s=0.5,
        lead_s=0.1,
        crosstalk_to_wide_s=0.8,
        silence_to_wide_s=2.0,
    ),
    Preset.PUNCHY: SwitchParams(
        min_shot_s=1.0,
        switch_delay_s=0.3,
        bridge_gap_s=0.4,
        lead_s=0.08,
        crosstalk_to_wide_s=0.8,
        silence_to_wide_s=1.5,
        max_shot_s=8.0,
        wide_frequency=0.2,
    ),
}

#: Which punch-in level (auto framing) goes with each editing style.
PUNCH_FOR_PRESET: dict[Preset, str] = {
    Preset.CALM: "calm",
    Preset.BALANCED: "balanced",
    Preset.DYNAMIC: "dynamic",
    Preset.PUNCHY: "dynamic",
}


def params_for(preset: Preset | str) -> SwitchParams:
    return PRESETS[Preset(preset)]
