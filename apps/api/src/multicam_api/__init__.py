"""Multicam Studio local API (FastAPI + SQLite + Huey)."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("multicam-api")
except PackageNotFoundError:  # running from a source tree without install
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
