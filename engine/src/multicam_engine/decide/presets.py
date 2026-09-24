"""Editing styles. The project stores only the preset name; values live here."""

from __future__ import annotations

from dataclasses import dataclass

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
}


def params_for(preset: Preset | str) -> SwitchParams:
    return PRESETS[Preset(preset)]
