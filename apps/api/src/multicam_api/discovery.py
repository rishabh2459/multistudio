"""How NLE plugins find (and start) the engine (PLUGIN_PLAN 3.2, D75).

When the engine runs with discovery on (``--headless``, or the desktop app's
``--discovery``) it writes ``engine.json`` to the app-data folder::

    {"port": 47811, "token": "...", "pid": 1234, "api": "1.0.0", ...}

A plugin reads that file, then calls ``GET /api/plugin/v1/handshake`` with the
token. Only one engine per data folder may own the file: ``InstanceLock`` holds an
OS file lock for the engine's lifetime (released by the OS if it crashes), and a
second engine started while one runs just reports the running one and exits.

``IdleWatch`` stops a headless engine after a quiet period: no HTTP request and no
queued / running job for ``idle_s`` seconds.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, Any

ENGINE_FILE = "engine.json"
LOCK_FILE = "engine.lock"
#: Preferred port for a discoverable engine (any free port if taken).
DEFAULT_PORT = 47811


@dataclass(frozen=True)
class EngineInfo:
    port: int
    token: str
    pid: int
    api: str
    engine_version: str = ""
    mode: str = "headless"  # headless | desktop
    started_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"


def engine_file(data_dir: Path) -> Path:
    return data_dir / ENGINE_FILE


def write_engine_file(data_dir: Path, info: EngineInfo) -> Path:
    """Atomically write ``engine.json`` (readable by the user only: it holds the token)."""
    data_dir.mkdir(parents=True, exist_ok=True)
    path = engine_file(data_dir)
    tmp = path.with_suffix(f".{info.pid}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(asdict(info), fh, indent=2)
    tmp.replace(path)
    return path


def read_engine_file(data_dir: Path) -> EngineInfo | None:
    """The running engine's details, or None if absent / unreadable / stale."""
    try:
        raw: dict[str, Any] = json.loads(engine_file(data_dir).read_text(encoding="utf-8"))
        info = EngineInfo(**raw)
    except (OSError, ValueError, TypeError):
        return None
    return info if pid_alive(info.pid) else None


def remove_engine_file(data_dir: Path, pid: int | None = None) -> bool:
    """Remove ``engine.json`` if it belongs to ``pid`` (default: this process)."""
    pid = os.getpid() if pid is None else pid
    path = engine_file(data_dir)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if raw.get("pid") != pid:
        return False
    try:
        path.unlink()
    except OSError:
        return False
    return True


def pid_alive(pid: int) -> bool:
    # One if/else (not early returns): type checkers treat sys.platform as a constant.
    if pid <= 0:
        alive = False
    elif sys.platform == "win32":
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        code = ctypes.c_ulong()
        ok = bool(handle) and kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
        if handle:
            kernel32.CloseHandle(handle)
        alive = bool(ok) and code.value == 259  # STILL_ACTIVE
    else:
        try:
            os.kill(pid, 0)
            alive = True
        except ProcessLookupError:
            alive = False
        except PermissionError:
            alive = True
    return alive


class InstanceLock:
    """An exclusive OS lock on ``engine.lock`` in the data folder.

    ``acquire()`` returns False when another engine holds it. The OS drops the lock
    when the process exits, so a crash never leaves the folder locked."""

    def __init__(self, data_dir: Path) -> None:
        self.path = data_dir / LOCK_FILE
        self._fh: IO[str] | None = None

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fh = self.path.open("a+", encoding="utf-8")  # held for the lifetime
        try:
            if sys.platform == "win32":
                import msvcrt

                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            fh.close()
            return False
        fh.seek(0)
        fh.truncate()
        fh.write(str(os.getpid()))
        fh.flush()
        self._fh = fh
        return True

    def release(self) -> None:
        if self._fh is None:
            return
        try:
            if sys.platform == "win32":
                import msvcrt

                self._fh.seek(0)
                msvcrt.locking(self._fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        self._fh.close()
        self._fh = None

    @property
    def held(self) -> bool:
        return self._fh is not None


class Activity:
    """Time of the last HTTP request (updated by a middleware)."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._last = clock()
        self._open = 0  # requests in flight (long SSE streams count as activity)
        self._lock = threading.Lock()

    def begin(self) -> None:
        with self._lock:
            self._open += 1
            self._last = self._clock()

    def end(self) -> None:
        with self._lock:
            self._open = max(0, self._open - 1)
            self._last = self._clock()

    def idle_for(self) -> float:
        with self._lock:
            return 0.0 if self._open else self._clock() - self._last


class IdleWatch:
    """Calls ``on_idle`` once nothing happened for ``idle_s`` seconds.

    ``busy()`` reports queued / running jobs; while it is true the engine is never idle."""

    def __init__(
        self,
        activity: Activity,
        idle_s: float,
        busy: Callable[[], bool],
        on_idle: Callable[[], None],
        *,
        poll_s: float = 15.0,
    ) -> None:
        self.activity, self.idle_s, self.busy, self.on_idle = activity, idle_s, busy, on_idle
        self.poll_s = poll_s
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def check(self) -> bool:
        """One check; True (and ``on_idle`` called) if the engine is idle."""
        if self.activity.idle_for() < self.idle_s:
            return False
        try:
            if self.busy():
                return False
        except Exception:
            return False
        self.on_idle()
        return True

    def start(self) -> None:
        def run() -> None:
            while not self._stop.wait(self.poll_s):
                if self.check():
                    return

        self._thread = threading.Thread(target=run, name="idle-watch", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()


def active_jobs(db: Any) -> int:
    """Queued + running jobs (``db`` is a ``multicam_api.db.session.Database``)."""
    from sqlalchemy import func, select

    from multicam_api.db.models import JobRow
    from multicam_api.schemas import JobStatus

    active = (JobStatus.QUEUED.value, JobStatus.RUNNING.value)
    with db.session() as s:
        n = s.scalar(select(func.count()).select_from(JobRow).where(JobRow.status.in_(active)))
    return int(n or 0)


def parse_duration(text: str) -> float:
    """``"30m"`` / ``"90s"`` / ``"1h"`` / ``"45"`` (seconds) -> seconds; 0 = never."""
    text = text.strip().lower()
    units = {"s": 1, "m": 60, "h": 3600}
    unit = units.get(text[-1:], 0)
    value = float(text[:-1]) * unit if unit else float(text)
    if value < 0:
        raise ValueError("duration must be >= 0")
    return value
