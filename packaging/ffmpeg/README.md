# ffmpeg binaries

**Development:** use Homebrew's ffmpeg (`brew install ffmpeg`). It is a GPL
build, which is fine for local development because it is never shipped.

**Distribution (Phase 11):** the app bundles an **LGPL** ffmpeg/ffprobe built
from source by a script in `packaging/scripts/`, per platform/architecture.
Binaries are placed here at build time and are git-ignored.

See `docs/PROJECT_PLAN.md` §5.3 for the codec/licensing strategy.
