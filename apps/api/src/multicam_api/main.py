"""``multicam-api``: run the local API server.

The desktop app starts it with ``--port 0`` (pick any free port) and reads the
first stdout line ``MULTICAM_API_READY port=<n>`` to know where to connect.
With ``--watch-stdin`` the server shuts down cleanly when its stdin closes: the
app closes it to stop the server, and the OS closes it if the app crashes, so
the backend never outlives the window (works the same on macOS and Windows).
"""

from __future__ import annotations

import argparse
import logging
import socket
import sys
import threading
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import BinaryIO

import uvicorn

from multicam_api.app import create_app
from multicam_api.config import Settings

HOST = "127.0.0.1"  # never listen on the network


def bind_socket(port: int) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
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


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="multicam-api", description="Multicam Studio local API")
    parser.add_argument("--port", type=int, default=8765, help="0 = any free port")
    parser.add_argument("--data-dir", help="override MULTICAM_DATA_DIR")
    parser.add_argument("--log-level", default="info")
    parser.add_argument(
        "--watch-stdin", action="store_true", help="stop when stdin closes (desktop app)"
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=args.log_level.upper(), format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    settings = Settings.from_env()
    if args.data_dir:
        settings = Settings(
            data_dir=Path(args.data_dir), token=settings.token, cors_origins=settings.cors_origins
        )
    sock = bind_socket(args.port)
    port = sock.getsockname()[1]
    print(f"MULTICAM_API_READY port={port}", flush=True)
    config = uvicorn.Config(create_app(settings), log_level=args.log_level, access_log=False)
    server = uvicorn.Server(config)
    if args.watch_stdin:

        def stop() -> None:
            logging.getLogger(__name__).info("stdin closed: shutting down")
            server.should_exit = True

        watch_stream(sys.stdin.buffer, stop)
    server.run(sockets=[sock])
    return 0


if __name__ == "__main__":
    sys.exit(main())
