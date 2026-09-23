"""Core data model — the contract between engine, API and UI.

Changing anything here? Bump ``SCHEMA_VERSION`` if the change is breaking,
then run ``make schemas`` so the TypeScript types stay in sync.
"""

from multicam_engine.models.cutlist import (
    AudioConfig,
    AudioMode,
    CutList,
    Reframe,
    Removal,
    RemovalKind,
    Segment,
    SegmentSource,
)
from multicam_engine.models.project import (
    SCHEMA_VERSION,
    Clip,
    ClipRole,
    MediaInfo,
    OutputSettings,
    Preset,
    Project,
    SyncResult,
)
from multicam_engine.models.time import Rational, Rounding

__all__ = [
    "SCHEMA_VERSION",
    "AudioConfig",
    "AudioMode",
    "Clip",
    "ClipRole",
    "CutList",
    "MediaInfo",
    "OutputSettings",
    "Preset",
    "Project",
    "Rational",
    "Reframe",
    "Removal",
    "RemovalKind",
    "Rounding",
    "Segment",
    "SegmentSource",
    "SyncResult",
]
