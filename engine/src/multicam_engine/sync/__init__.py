"""sync — align clips by their audio (GCC-PHAT + drift correction)."""

from multicam_engine.sync.engine import (
    REPORT_SAMPLE_RATE,
    ClipSyncReport,
    PairSync,
    SyncParams,
    SyncReport,
    sync_files,
    sync_signals,
)
from multicam_engine.sync.gcc_phat import Peak, gcc_phat

__all__ = [
    "REPORT_SAMPLE_RATE",
    "ClipSyncReport",
    "PairSync",
    "Peak",
    "SyncParams",
    "SyncReport",
    "gcc_phat",
    "sync_files",
    "sync_signals",
]
