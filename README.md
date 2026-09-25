# Multicam Studio

Local, offline multicam auto-switching for podcasts: sync cameras by audio,
cut to whoever is speaking, render a frame-accurate video.
Everything runs on your own machine using free, open-source components.

📘 **Plan:** [`docs/PROJECT_PLAN.md`](docs/PROJECT_PLAN.md) ·
🏛 **Rules:** [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) ·
🧾 **Decisions:** [`docs/DECISIONS.md`](docs/DECISIONS.md) ·
🎥 **Test footage:** [`docs/TEST_FOOTAGE.md`](docs/TEST_FOOTAGE.md)

**Current phase:** 4 — Local backend done (real-footage checks for Phases 1–3 pending); next: Phase 5 UI

---

## Setup (macOS)

### 1. Install prerequisites (one time)

```bash
xcode-select --install          # git + make (skip if already installed)
brew install uv node@22 pnpm ffmpeg
```

If Homebrew says `node@22` is keg-only, follow its printed instruction to add it to your PATH.
`uv` installs Python 3.12 automatically — no separate Python install needed.

### 2. Set up the project

```bash
cd multicam-studio
make setup     # Python env, JS deps, git hooks, generated types
make doctor    # verifies every tool
make check     # lint + types + tests + generated-file check (same as CI)
```

### 3. First commit

```bash
make format                     # normalize formatting once
git add -A
git commit -m "Phase 0: project scaffold"
```

Commit `uv.lock`, `pnpm-lock.yaml`, `schemas/` and `packages/types/src/generated/`
— CI needs them.

---

## Everyday commands

| Command | What it does |
|---|---|
| `make help` | List all commands |
| `make test` | Fast tests |
| `make check` | Everything CI runs |
| `make format` | Auto-format Python + JS |
| `make schemas` | Regenerate JSON Schema + TS types after changing models |
| `make gt-audio REC=samples/T1` | Extract WAVs for labeling |
| `make gt-build REC=samples/T1` | Build ground truth from Audacity labels |
| `make gt-check` | Validate all test recordings |
| `make gt-eval REC=samples/T1` | Score sync accuracy against ground truth |
| `make fetch-models` | Download pinned model files |
| `uv run multicam probe cam1.mp4` | Frame rate, VFR, duration, audio of a file |
| `uv run multicam sync cam1.mp4 cam2.mp4 --out sync.json` | Sync clips by audio |
| `uv run multicam cutlist --sync sync.json --label cam1.mp4=Host --wide wide.mp4` | Auto-edit: who speaks → camera cuts (writes cutlist.json + project.json) |
| `uv run multicam gt eval-switch samples/T2` | Score speaker accuracy against ground truth |
| `uv run multicam render --project project.json --cutlist cutlist.json --out episode.mp4` | Render the final video (`--preset youtube-1080p/youtube-4k/master/draft`) |
| `uv run multicam encoders` | Show which hardware/software encoders work on this machine |
| `uv run multicam proxy cam1.mp4 cam2.mp4` | Low-res proxies for the editor |
| `uv run multicam-api` | Start the local API on http://127.0.0.1:8765 (docs at `/docs`) |
| `uv run python scripts/api_demo.py cam1.mp4 cam2.mp4` | Whole pipeline through the API (server must be running) |
| `pnpm --filter @multicam/web dev` | The UI on http://localhost:3000 (start `uv run multicam-api` first) |
| `pnpm --filter @multicam/web build` | Static UI build in `apps/web/out/` (loaded by the desktop app) |
| `pnpm --filter @multicam/web test` | UI unit/component tests (Vitest) |
| `pnpm --filter @multicam/web e2e` | Full UI flow in Chromium against a real API (Playwright) |
| `uv run python scripts/make_demo_media.py` | Synthetic 3-camera recording in `samples/demo/` to try the app |
| `uv run multicam --help` | Engine CLI |

## Repository layout

```
engine/src/multicam_engine/   Python engine: media, sync, analysis, decide, render, models
apps/api/src/multicam_api/    Local backend: FastAPI + SQLite + Huey (Phase 4)
packages/types/               TypeScript types generated from engine models
schemas/                      Generated JSON Schema + OpenAPI (sources for TS types/client)
scripts/                      Dev scripts (doctor, schema export)
packaging/                    Model manifest, ffmpeg notes, fetch scripts
tests/                        pytest suite
samples/                      Test footage (git-ignored)
docs/                         Plan, architecture, decisions, test protocol
```
