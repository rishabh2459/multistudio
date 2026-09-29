"""Core data model — the contract between engine, API and UI.

Changing anything here? Bump ``SCHEMA_VERSION`` if the change is breaking,
then run ``make schemas`` so the TypeScript types stay in sync.
"""

from multicam_engine.models.cutlist import (
    AudioConfig,
    AudioMode,
    CutList,
    Reframe,
    ReframeKey,
    Removal,
    RemovalKind,
    Segment,
    SegmentSource,
)
from multicam_engine.models.project import (
    MAX_CAMERAS,
    MAX_SPEAKERS,
    SCHEMA_VERSION,
    CameraLayout,
    Clip,
    ClipRole,
    MediaInfo,
    OutputSettings,
    Preset,
    Project,
    ShotType,
    Speaker,
    SyncResult,
)
from multicam_engine.models.time import Rational, Rounding

__all__ = [
    "MAX_CAMERAS",
    "MAX_SPEAKERS",
    "SCHEMA_VERSION",
    "AudioConfig",
    "AudioMode",
    "CameraLayout",
    "Clip",
    "ClipRole",
    "CutList",
    "MediaInfo",
    "OutputSettings",
    "Preset",
    "Project",
    "Rational",
    "Reframe",
    "ReframeKey",
    "Removal",
    "RemovalKind",
    "Rounding",
    "Segment",
    "SegmentSource",
    "ShotType",
    "Speaker",
    "SyncResult",
]
