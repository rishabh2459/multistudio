"""Settings, read from the environment once at startup.

MULTICAM_DATA_DIR   where the database, job queue, caches and renders live
                    (default: the OS application-data folder)
MULTICAM_API_TOKEN  if set, every /api request must send it (header
                    ``X-Multicam-Token`` or ``?token=``); the desktop app sets a
                    random one per launch so other local programs can't use the API
MULTICAM_CORS       comma-separated extra origins allowed to call the API (dev UI)
MULTICAM_MODE       ``desktop`` (default). ``cloud`` is reserved for Phase 13.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

APP_DIR_NAME = "Multicam Studio"
DEV_UI_ORIGINS = ("http://localhost:3000", "http://127.0.0.1:3000")


def default_data_dir() -> Path:
    # One if/elif/else (not early returns): type checkers treat sys.platform as a
    # constant and would flag the other platforms' branches as unreachable.
    if sys.platform == "darwin":
        path = Path.home() / "Library" / "Application Support" / APP_DIR_NAME
    elif sys.platform == "win32":
        path = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / APP_DIR_NAME
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
        path = base / "multicam-studio"
    return path


@dataclass(frozen=True)
class Settings:
    data_dir: Path = field(default_factory=default_data_dir)
    token: str | None = None
    cors_origins: tuple[str, ...] = DEV_UI_ORIGINS
    mode: Literal["desktop", "cloud"] = "desktop"
    workers: int = 1
    #: Seconds between SSE progress polls.
    sse_interval: float = 0.25

    @property
    def db_path(self) -> Path:
        return self.data_dir / "multicam.db"

    @property
    def queue_path(self) -> Path:
        return self.data_dir / "queue.db"

    @property
    def storage_dir(self) -> Path:
        return self.data_dir / "projects"

    @property
    def audio_cache_dir(self) -> Path:
        return self.data_dir / "cache" / "audio"

    @classmethod
    def from_env(cls) -> Settings:
        mode = os.environ.get("MULTICAM_MODE", "desktop")
        if mode != "desktop":
            raise ValueError(f"MULTICAM_MODE={mode!r} is not supported yet (Phase 13)")
        extra = tuple(
            o.strip() for o in os.environ.get("MULTICAM_CORS", "").split(",") if o.strip()
        )
        data_dir = os.environ.get("MULTICAM_DATA_DIR")
        return cls(
            data_dir=Path(data_dir) if data_dir else default_data_dir(),
            token=os.environ.get("MULTICAM_API_TOKEN") or None,
            cors_origins=DEV_UI_ORIGINS + extra,
        )
