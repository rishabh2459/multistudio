# ffmpeg binaries

**Development:** use Homebrew's ffmpeg (`brew install ffmpeg`). It is a GPL
build, which is fine for local development because it is never shipped.

**Desktop builds (Phase 6, internal testing):** the standalone backend ships its
own `ffmpeg` and `ffprobe`, copied next to the `multicam-api` executable by
`packaging/scripts/build_backend.py`. They must be **self-contained (static)**
builds — Homebrew's ffmpeg needs Homebrew's libraries and would fail on a clean
machine (the build script checks this with `otool -L`).

Put both files in a folder named after the build machine, then build:

| Machine | Folder | Where to get static builds |
|---|---|---|
| Mac, Apple Silicon | `packaging/ffmpeg/darwin-arm64/` | ffmpeg.martin-riedl.de → macOS · arm64 · Release: `ffmpeg` and `ffprobe` |
| Mac, Intel | `packaging/ffmpeg/darwin-x64/` | ffmpeg.martin-riedl.de → macOS · amd64 · Release |
| Windows x64 | `packaging/ffmpeg/win32-x64/` | github.com/BtbN/FFmpeg-Builds releases → `win64-lgpl` zip, `bin/ffmpeg.exe` + `bin/ffprobe.exe` |

```bash
mkdir -p packaging/ffmpeg/darwin-arm64
# unzip the downloads into it, then:
chmod +x packaging/ffmpeg/darwin-arm64/ff*
xattr -dr com.apple.quarantine packaging/ffmpeg/darwin-arm64
pnpm --filter @multicam/desktop backend
```

Or pass any folder: `... build_backend.py --ffmpeg-dir /path/to/folder`.

Binaries here are git-ignored.

**Distribution (Phase 11):** the app bundles an **LGPL** ffmpeg/ffprobe built
from source by a script in `packaging/scripts/`, per platform/architecture.
See `docs/PROJECT_PLAN.md` §5.3 for the codec/licensing strategy.
