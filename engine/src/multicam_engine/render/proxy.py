"""Low-resolution proxies for smooth scrubbing in the timeline editor (Phase 7).

A proxy keeps the source's own timestamps (no frame-rate conversion), so sync
offsets and cut positions computed for the original apply unchanged. Short GOPs
(every 0.5 s) make seeking fast.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from multicam_engine.media.ffmpeg import run_tool
from multicam_engine.media.probe import probe
from multicam_engine.render.encoders import choose_encoder

PROXY_HEIGHT = 540


def proxy_path(source: Path, proxy_dir: Path) -> Path:
    stat = source.stat()
    key = hashlib.sha256(
        f"{source.resolve()}|{stat.st_size}|{stat.st_mtime_ns}".encode()
    ).hexdigest()
    return proxy_dir / f"{source.stem}.{key[:10]}.proxy.mp4"


def make_proxy(source: str | Path, proxy_dir: Path, *, height: int = PROXY_HEIGHT) -> Path:
    """Create (or reuse) the proxy for ``source``. Returns its path."""
    source = Path(source)
    out = proxy_path(source, proxy_dir)
    if out.is_file():
        return out
    proxy_dir.mkdir(parents=True, exist_ok=True)
    info = probe(source)
    enc, _ = choose_encoder("h264")
    gop = max(1, round(float(info.media.fps.to_fraction()) / 2))
    rate = ["-q:v", "5"] if enc == "mpeg4" else ["-b:v", "2500k"]
    tmp = out.with_suffix(".part.mp4")
    args = [
        "-loglevel", "error", "-y", "-i", str(source),
        "-map", "0:v:0", "-map", "0:a:0?",
        "-vf", f"scale=-2:{min(height, info.media.height)}:flags=bicubic,format=yuv420p",
        "-c:v", enc, *rate, "-g", str(gop), "-bf", "0",
        "-fps_mode", "passthrough",
        "-c:a", "aac", "-b:a", "96k",
        "-movflags", "+faststart",
        str(tmp),
    ]  # fmt: skip
    run_tool("ffmpeg", args)
    tmp.replace(out)
    return out
