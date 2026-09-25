"""``multicam-api``: run the local API server.

The desktop app starts it with ``--port 0`` (pick any free port) and reads the
first stdout line ``MULTICAM_API_READY port=<n>`` to know where to connect.
"""

from __future__ import annotations

import argparse
import logging
import socket
import sys
from collections.abc import Sequence
from pathlib import Path

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


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="multicam-api", description="Multicam Studio local API")
    parser.add_argument("--port", type=int, default=8765, help="0 = any free port")
    parser.add_argument("--data-dir", help="override MULTICAM_DATA_DIR")
    parser.add_argument("--log-level", default="info")
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
    uvicorn.Server(config).run(sockets=[sock])
    return 0


if __name__ == "__main__":
    sys.exit(main())
