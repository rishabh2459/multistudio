"""Check the developer toolchain. Run with: make doctor"""

from __future__ import annotations

import platform
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass

OK, WARN, FAIL = "\033[32m✔\033[0m", "\033[33m!\033[0m", "\033[31m✘\033[0m"


@dataclass
class Result:
    status: str
    name: str
    detail: str


def _run(*cmd: str) -> str | None:
    if shutil.which(cmd[0]) is None:
        return None
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=20, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return (proc.stdout or proc.stderr).strip()


def _major(text: str) -> int | None:
    m = re.search(r"(\d+)\.", text)
    return int(m.group(1)) if m else None


def check_python() -> Result:
    v = sys.version_info
    status = OK if (v.major, v.minor) == (3, 12) else FAIL
    return Result(status, "Python", f"{v.major}.{v.minor}.{v.micro} (need 3.12)")


def check_simple(name: str, cmd: list[str], min_major: int | None, hint: str) -> Result:
    out = _run(*cmd)
    if out is None:
        return Result(FAIL, name, f"not found — {hint}")
    first = out.splitlines()[0]
    if min_major is not None:
        major = _major(first.lstrip("v"))
        if major is None or major < min_major:
            return Result(FAIL, name, f"{first} (need >= {min_major}) — {hint}")
    return Result(OK, name, first)


def check_ffmpeg() -> list[Result]:
    results: list[Result] = []
    version = _run("ffmpeg", "-hide_banner", "-version")
    if version is None:
        return [Result(FAIL, "ffmpeg", "not found — brew install ffmpeg")]
    results.append(Result(OK, "ffmpeg", version.splitlines()[0]))

    if "--enable-gpl" in version:
        results.append(
            Result(
                WARN,
                "ffmpeg license",
                "GPL build — fine for development; the shipped app uses an LGPL build (Phase 11)",
            )
        )
    else:
        results.append(Result(OK, "ffmpeg license", "LGPL build"))

    probe = _run("ffprobe", "-version")
    results.append(
        Result(OK, "ffprobe", probe.splitlines()[0])
        if probe
        else Result(FAIL, "ffprobe", "not found — comes with ffmpeg")
    )

    encoders = _run("ffmpeg", "-hide_banner", "-encoders") or ""
    if platform.system() == "Darwin":
        hw = "h264_videotoolbox" in encoders
        results.append(
            Result(
                OK if hw else WARN,
                "VideoToolbox",
                "hardware H.264 encoder available" if hw else "h264_videotoolbox missing",
            )
        )
    return results


def main() -> int:
    print(f"Multicam Studio doctor — {platform.system()} {platform.machine()}\n")
    results = [
        check_python(),
        check_simple("uv", ["uv", "--version"], None, "brew install uv"),
        check_simple("Node.js", ["node", "--version"], 22, "brew install node@22"),
        check_simple("pnpm", ["pnpm", "--version"], 9, "brew install pnpm"),
        check_simple("git", ["git", "--version"], None, "xcode-select --install"),
        *check_ffmpeg(),
    ]
    width = max(len(r.name) for r in results)
    for r in results:
        print(f"  {r.status} {r.name:<{width}}  {r.detail}")

    failed = sum(r.status == FAIL for r in results)
    print(f"\n{'All good.' if not failed else f'{failed} problem(s) found.'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
