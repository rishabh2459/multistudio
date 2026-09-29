"""Build the standalone backend for the desktop app (no Python needed to run it).

    uv run --with "pyinstaller>=6.10,<7" python packaging/scripts/build_backend.py
    (or: pnpm --filter @multicam/desktop backend)

Steps:
  1. check the model files (``make fetch-models``) and find ffmpeg + ffprobe;
  2. PyInstaller one-folder build -> ``packaging/dist/multicam-api/``;
  3. copy ffmpeg/ffprobe next to the executable (the engine looks there);
  4. smoke test: start the built server with a minimal PATH, check that it answers,
     finds the bundled ffmpeg and the AI model, and stops when stdin closes.

ffmpeg must be a self-contained (static) build, because the app has to run on
machines without Homebrew. Put ``ffmpeg`` and ``ffprobe`` in
``packaging/ffmpeg/<platform>-<arch>/`` (e.g. ``darwin-arm64``) or pass
``--ffmpeg-dir``. See packaging/ffmpeg/README.md.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

# A plain str (not sys.platform itself) so type checkers do not treat the other
# platforms' branches as unreachable.
PLATFORM: str = sys.platform
ROOT = Path(__file__).resolve().parents[2]
SPEC = ROOT / "packaging" / "pyinstaller" / "multicam-api.spec"
DIST = ROOT / "packaging" / "dist"
WORK = ROOT / "packaging" / "build" / "pyinstaller"
MODELS = ROOT / "packaging" / "models"
BUNDLED_MODELS = ("silero_vad.onnx", "face_detection_yunet_2023mar.onnx")
MANIFEST = ROOT / "packaging" / "models" / "manifest.json"
EXE_SUFFIX = ".exe" if PLATFORM == "win32" else ""
TOOLS = ("ffmpeg", "ffprobe")

# Shared libraries a self-contained binary may link against (system only).
SYSTEM_LIB_PREFIXES = {
    "darwin": ("/usr/lib/", "/System/Library/"),
    "linux": ("/lib", "/usr/lib", "linux-vdso", "/lib64"),
}


class BuildError(RuntimeError):
    pass


def platform_tag() -> str:
    machine = platform.machine().lower()
    arch = {"x86_64": "x64", "amd64": "x64", "arm64": "arm64", "aarch64": "arm64"}.get(
        machine, machine
    )
    return f"{PLATFORM}-{arch}"


def linked_libraries(binary: Path) -> list[str]:
    """Non-system shared libraries the binary needs (empty = self-contained)."""
    if PLATFORM == "darwin":
        out = subprocess.run(["otool", "-L", str(binary)], capture_output=True, text=True)
        libs = [line.strip().split(" ")[0] for line in out.stdout.splitlines()[1:]]
    elif PLATFORM.startswith("linux"):
        out = subprocess.run(["ldd", str(binary)], capture_output=True, text=True)
        if "not a dynamic executable" in out.stdout + out.stderr:
            return []
        libs = [
            (line.split("=>")[1] if "=>" in line else line).strip().split(" ")[0]
            for line in out.stdout.splitlines()
        ]
    else:
        return []  # Windows builds (BtbN/gyan) are static; nothing to check
    prefixes = SYSTEM_LIB_PREFIXES["darwin" if PLATFORM == "darwin" else "linux"]
    return [lib for lib in libs if lib and not lib.startswith(prefixes)]


def find_ffmpeg(ffmpeg_dir: Path | None, allow_system: bool) -> dict[str, Path]:
    folder = ffmpeg_dir or ROOT / "packaging" / "ffmpeg" / platform_tag()
    found: dict[str, Path] = {}
    for tool in TOOLS:
        candidate = folder / f"{tool}{EXE_SUFFIX}"
        if candidate.is_file():
            found[tool] = candidate
        elif allow_system and (on_path := shutil.which(tool)):
            found[tool] = Path(on_path).resolve()
        else:
            raise BuildError(
                f"{tool} not found in {folder}. Put static ffmpeg + ffprobe builds there "
                "(see packaging/ffmpeg/README.md), or pass --ffmpeg-dir."
            )
    for path in found.values():
        extra = linked_libraries(path)
        if extra:
            raise BuildError(
                f"{path} is not self-contained: it needs {', '.join(extra[:4])}"
                f"{' ...' if len(extra) > 4 else ''}. Homebrew's ffmpeg only works on machines "
                "with Homebrew; use a static build (packaging/ffmpeg/README.md)."
            )
    return found


def check_models() -> None:
    """Bundled models must be the pinned files (not an error page or LFS pointer)."""
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    pinned = {m["dest"]: m["sha256"] for m in manifest["models"]}
    for name in BUNDLED_MODELS:
        path = MODELS / name
        if not path.is_file():
            raise BuildError(f"{name} missing: run `make fetch-models` first")
        if hashlib.sha256(path.read_bytes()).hexdigest() != pinned.get(name):
            raise BuildError(f"{name} does not match the manifest: run `make fetch-models`")


def run_pyinstaller() -> Path:
    cmd = [sys.executable, "-m", "PyInstaller", str(SPEC), "--noconfirm", "--clean",
           "--distpath", str(DIST), "--workpath", str(WORK)]  # fmt: skip
    print("$", " ".join(cmd), flush=True)
    try:
        subprocess.run(cmd, check=True, cwd=ROOT)
    except FileNotFoundError as exc:
        raise BuildError(f"could not run PyInstaller: {exc}") from exc
    except subprocess.CalledProcessError as exc:
        raise BuildError(f"PyInstaller failed (exit {exc.returncode})") from exc
    out = DIST / "multicam-api"
    if not (out / f"multicam-api{EXE_SUFFIX}").is_file():
        raise BuildError(f"PyInstaller finished but {out} has no executable")
    return out


def bundle_tools(out: Path, tools: dict[str, Path]) -> None:
    for tool, src in tools.items():
        dest = out / f"{tool}{EXE_SUFFIX}"
        shutil.copy2(src, dest)
        dest.chmod(dest.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        if PLATFORM == "darwin":
            # Apple Silicon refuses to run unsigned code; ad-hoc sign (no identity).
            subprocess.run(["codesign", "--force", "--sign", "-", str(dest)], check=True)
        print(f"bundled {tool}: {src}")


def minimal_env(data_dir: Path) -> dict[str, str]:
    """Environment without developer tools on PATH, like a clean machine."""
    keep = ("SYSTEMROOT", "WINDIR", "TEMP", "TMP", "HOME", "USERPROFILE", "LANG")
    env = {k: v for k, v in os.environ.items() if k.upper() in keep}
    env["PATH"] = (
        str(Path(os.environ.get("SYSTEMROOT", r"C:\Windows")) / "System32")
        if PLATFORM == "win32"
        else "/usr/bin:/bin"
    )
    env["MULTICAM_API_TOKEN"] = "smoke-test"
    env["MULTICAM_DATA_DIR"] = str(data_dir)
    return env


def smoke_test(out: Path) -> None:
    exe = out / f"multicam-api{EXE_SUFFIX}"
    with tempfile.TemporaryDirectory() as tmp:
        started = time.monotonic()
        proc = subprocess.Popen(
            [str(exe), "--port", "0", "--watch-stdin", "--log-level", "warning"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, env=minimal_env(Path(tmp)),
        )  # fmt: skip
        try:
            assert proc.stdout is not None and proc.stdin is not None
            line = proc.stdout.readline().decode().strip()
            if not line.startswith("MULTICAM_API_READY port="):
                raise BuildError(f"unexpected first line from the built server: {line!r}")
            base = f"http://127.0.0.1:{int(line.split('=')[1])}"
            info = _wait_for_info(base, deadline=time.monotonic() + 60)
            startup = time.monotonic() - started
            ffmpeg = str(info.get("ffmpeg") or "")
            if not ffmpeg or Path(ffmpeg).resolve().parent != out.resolve():
                raise BuildError(f"the built server does not use the bundled ffmpeg: {ffmpeg!r}")
            if not info.get("vad_model_available"):
                raise BuildError("the built server cannot find the AI speech model")
            proc.stdin.close()
            code = proc.wait(timeout=30)
            if code != 0:
                raise BuildError(f"the built server exited with code {code} on shutdown")
        finally:
            if proc.poll() is None:
                proc.kill()
    size = sum(f.stat().st_size for f in out.rglob("*") if f.is_file()) / 1e6
    print(f"smoke test OK: started in {startup:.1f} s, {info.get('ffmpeg_version')}")
    print(f"backend: {out} ({size:.0f} MB)")


def _wait_for_info(base: str, deadline: float) -> dict[str, object]:
    request = urllib.request.Request(
        f"{base}/api/system/info", headers={"X-Multicam-Token": "smoke-test"}
    )
    while True:
        try:
            with urllib.request.urlopen(request, timeout=5) as resp:
                data: dict[str, object] = json.load(resp)
                return data
        except (urllib.error.URLError, ConnectionError):
            if time.monotonic() > deadline:
                raise BuildError("the built server did not answer within 60 s") from None
            time.sleep(0.2)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the standalone backend.")
    parser.add_argument("--ffmpeg-dir", type=Path, help="folder with static ffmpeg + ffprobe")
    parser.add_argument(
        "--allow-system-ffmpeg",
        action="store_true",
        help="use ffmpeg from PATH if it is self-contained",
    )
    parser.add_argument("--skip-smoke-test", action="store_true")
    args = parser.parse_args(argv)
    try:
        check_models()
        tools = find_ffmpeg(args.ffmpeg_dir, args.allow_system_ffmpeg)
        out = run_pyinstaller()
        bundle_tools(out, tools)
        if not args.skip_smoke_test:
            smoke_test(out)
    except BuildError as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
