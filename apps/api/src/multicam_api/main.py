"""``multicam-api``: run the local API server.

The desktop app starts it with ``--port 0`` (pick any free port) and reads the
first stdout line ``MULTICAM_API_READY port=<n>`` to know where to connect.
With ``--watch-stdin`` the server shuts down cleanly when its stdin closes: the
app closes it to stop the server, and the OS closes it if the app crashes, so
the backend never outlives the window (works the same on macOS and Windows).

NLE plugins (PLUGIN_PLAN 3.2): ``--headless`` runs the engine without the app,
writes ``engine.json`` (port + random token) to the data folder so plugins can
find it, prefers port 47811, and exits after ``--idle-exit`` (default 30m) with no
requests and no jobs. Starting a second engine on the same data folder prints
``MULTICAM_API_RUNNING port=<n>`` and exits 0, so ``multicam://start`` is safe to
repeat. The desktop app passes ``--discovery`` to share its engine the same way.
"""

from __future__ import annotations

import argparse
import logging
import os
import secrets
import socket
import sys
import threading
from collections.abc import Callable, Sequence
from dataclasses import replace
from pathlib import Path
from typing import BinaryIO

import uvicorn

from multicam_api import __version__
from multicam_api.app import create_app
from multicam_api.config import Settings
from multicam_api.discovery import (
    DEFAULT_PORT,
    EngineInfo,
    IdleWatch,
    InstanceLock,
    active_jobs,
    parse_duration,
    read_engine_file,
    remove_engine_file,
    write_engine_file,
)
from multicam_api.plugin_schemas import PLUGIN_API_VERSION

HOST = "127.0.0.1"  # never listen on the network


def bind_socket(port: int) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if sys.platform == "win32":
        # SO_REUSEADDR on Windows lets two processes share a listening port; the
        # exclusive option makes a taken port fail, so we fall back to another.
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    else:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((HOST, port))
    sock.set_inheritable(True)
    return sock


def watch_stream(stream: BinaryIO, on_close: Callable[[], None]) -> threading.Thread:
    """Call ``on_close`` once ``stream`` reaches end-of-file (in a daemon thread)."""

    def run() -> None:
        try:
            while stream.read(1024):
                pass
        except (OSError, ValueError):
            pass
        on_close()

    thread = threading.Thread(target=run, name="stdin-watch", daemon=True)
    thread.start()
    return thread


def bind_preferred(port: int | None, fallback_any: bool) -> socket.socket:
    """Bind ``port``; if it is taken and ``fallback_any``, any free port."""
    try:
        return bind_socket(port or 0)
    except OSError:
        if not fallback_any:
            raise
        return bind_socket(0)


def jobs_busy(app: object) -> bool:
    """True while a job is queued or running (or the app is still starting)."""
    ctx = getattr(getattr(app, "state", None), "ctx", None)
    return True if ctx is None else active_jobs(ctx.db) > 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="multicam-api", description="Multicam Studio local API")
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help=f"0 = any free port (default 8765; {DEFAULT_PORT} with --headless/--discovery)",
    )
    parser.add_argument("--data-dir", help="override MULTICAM_DATA_DIR")
    parser.add_argument("--log-level", default="info")
    parser.add_argument(
        "--watch-stdin", action="store_true", help="stop when stdin closes (desktop app)"
    )
    parser.add_argument(
        "--headless", action="store_true", help="engine for NLE plugins (implies --discovery)"
    )
    parser.add_argument(
        "--discovery", action="store_true", help="write engine.json so NLE plugins can connect"
    )
    parser.add_argument(
        "--idle-exit", default="30m", help="headless: stop after this long idle (0 = never)"
    )
    args = parser.parse_args(argv)
    discover = args.headless or args.discovery
    idle_s = parse_duration(args.idle_exit) if args.headless else 0.0

    logging.basicConfig(
        level=args.log_level.upper(), format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    log = logging.getLogger(__name__)
    settings = Settings.from_env()
    if args.data_dir:
        settings = replace(settings, data_dir=Path(args.data_dir))

    lock: InstanceLock | None = None
    if discover:
        lock = InstanceLock(settings.data_dir)
        if not lock.acquire():
            running = read_engine_file(settings.data_dir)
            if running is None:
                print("MULTICAM_API_LOCKED another engine is starting", flush=True)
                return 3
            print(f"MULTICAM_API_RUNNING port={running.port}", flush=True)
            return 0
        if not settings.token:  # plugins read the token from engine.json
            settings = replace(settings, token=secrets.token_urlsafe(24))

    if args.port is not None:
        sock = bind_socket(args.port)
    elif discover:
        sock = bind_preferred(DEFAULT_PORT, fallback_any=True)
    else:
        sock = bind_socket(8765)
    port = sock.getsockname()[1]
    app = create_app(settings)
    config = uvicorn.Config(app, log_level=args.log_level, access_log=False)
    server = uvicorn.Server(config)

    def stop(reason: str) -> None:
        log.info("%s: shutting down", reason)
        server.should_exit = True

    app.state.shutdown = lambda: stop("shutdown requested")
    if args.watch_stdin:
        watch_stream(sys.stdin.buffer, lambda: stop("stdin closed"))
    watch: IdleWatch | None = None
    if idle_s > 0:
        watch = IdleWatch(
            app.state.activity,
            idle_s,
            lambda: jobs_busy(app),
            lambda: stop("idle"),
            poll_s=min(15.0, max(0.5, idle_s / 4)),
        )
        watch.start()
    if discover:
        assert settings.token is not None
        write_engine_file(
            settings.data_dir,
            EngineInfo(
                port=port,
                token=settings.token,
                pid=os.getpid(),
                api=PLUGIN_API_VERSION,
                engine_version=__version__,
                mode="headless" if args.headless else "desktop",
            ),
        )
    print(f"MULTICAM_API_READY port={port}", flush=True)
    try:
        server.run(sockets=[sock])
    finally:
        if watch is not None:
            watch.stop()
        if discover:
            remove_engine_file(settings.data_dir)
        if lock is not None:
            lock.release()
    return 0


if __name__ == "__main__":
    sys.exit(main())
