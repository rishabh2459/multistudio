# Multicam Studio

Local, offline multicam auto-switching for podcasts: sync cameras by audio,
cut to whoever is speaking, render a frame-accurate video.
Everything runs on your own machine using free, open-source components.

📘 **Plan:** [`docs/PROJECT_PLAN.md`](docs/PROJECT_PLAN.md) ·
🏛 **Rules:** [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) ·
🧾 **Decisions:** [`docs/DECISIONS.md`](docs/DECISIONS.md) ·
🎥 **Test footage:** [`docs/TEST_FOOTAGE.md`](docs/TEST_FOOTAGE.md)

**Current phase:** 0 — Foundation

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
| `make fetch-models` | Download pinned model files |
| `uv run multicam --help` | Engine CLI |

## Repository layout

```
engine/src/multicam_engine/   Python engine (models, benchmark; more per phase)
packages/types/               TypeScript types generated from engine models
schemas/                      Generated JSON Schema (source for TS types)
scripts/                      Dev scripts (doctor, schema export)
packaging/                    Model manifest, ffmpeg notes, fetch scripts
tests/                        pytest suite
samples/                      Test footage (git-ignored)
docs/                         Plan, architecture, decisions, test protocol
```
