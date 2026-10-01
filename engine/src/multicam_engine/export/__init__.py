"""Timeline export to editing software: FCPXML, Premiere XML (xmeml), CMX3600 EDL."""

from __future__ import annotations

from enum import StrEnum

from multicam_engine.export.edl import to_edl
from multicam_engine.export.fcpxml import to_fcpxml
from multicam_engine.export.timeline import (
    Event,
    Marker,
    NleTimeline,
    Source,
    build_nle_timeline,
)
from multicam_engine.export.xmeml import to_xmeml


class NleFormat(StrEnum):
    FCPXML = "fcpxml"  # Final Cut Pro, DaVinci Resolve
    XMEML = "xmeml"  # Adobe Premiere Pro, DaVinci Resolve
    EDL = "edl"  # anything (video cuts only)


EXTENSIONS = {NleFormat.FCPXML: ".fcpxml", NleFormat.XMEML: ".xml", NleFormat.EDL: ".edl"}


def write_nle(timeline: NleTimeline, fmt: NleFormat) -> str:
    if fmt is NleFormat.FCPXML:
        return to_fcpxml(timeline)
    if fmt is NleFormat.XMEML:
        return to_xmeml(timeline)
    return to_edl(timeline)


__all__ = [
    "EXTENSIONS",
    "Event",
    "Marker",
    "NleFormat",
    "NleTimeline",
    "Source",
    "build_nle_timeline",
    "to_edl",
    "to_fcpxml",
    "to_xmeml",
    "write_nle",
]
