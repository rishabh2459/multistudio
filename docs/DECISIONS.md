# Decision Log

D1–D13 are recorded in `PROJECT_PLAN.md` §13. New decisions continue here.

| # | Date | Decision | Reason |
|---|------|----------|--------|
| D11 | 2026-09-22 | Working name **Multicam Studio** (`multicam` CLI, `multicam_engine` package) | Placeholder until branding; rename is a search-and-replace |
| D14 | 2026-09-22 | Python pinned to **3.12** | Best wheel coverage for MediaPipe / ONNX Runtime / CTranslate2 |
| D15 | 2026-09-22 | uv workspace (Python) + pnpm workspace (JS) | Fast, reproducible, lockfiles for both |
| D16 | 2026-09-22 | `src/` layout: `engine/src/multicam_engine` | Prevents importing un-installed code by accident |
| D17 | 2026-09-22 | Shared TS types in `packages/types`, generated via JSON Schema (`json-schema-to-typescript`, MIT) | UI and API can never drift apart; CI enforces |
| D18 | 2026-09-22 | Ranges are half-open `[start, end)`; rounding is half-up | Unambiguous, deterministic |
| D19 | 2026-09-22 | Sync sign convention: positive offset = clip started earlier | One convention for engine, benchmarks, UI |
| D20 | 2026-09-22 | Ground truth via claps + Audacity labels (Audacity is a dev tool, not bundled) | Free, ~1 ms precision, no custom tooling |
| D21 | 2026-09-22 | Dev uses Homebrew ffmpeg (GPL); shipped app uses self-built LGPL ffmpeg | GPL is fine for unshipped dev tools; see plan §5.3 |
| D22 | 2026-09-22 | Model files pinned by SHA-256 in `packaging/models/manifest.json` | Reproducible, tamper-evident bundles |
| D23 | 2026-09-22 | CLI uses stdlib `argparse` | One fewer dependency to bundle |
| D24 | 2026-09-22 | CI on Ubuntu for now; macOS jobs added when platform-specific code lands | Conserves free CI minutes |

## Dependencies added

| Package | License | Where | Why |
|---------|---------|-------|-----|
| pydantic | MIT | engine | Data model + validation + JSON Schema |
| hatchling | MIT | engine build | Build backend |
| ruff, mypy, pytest, pytest-cov, pre-commit | MIT | dev only | Quality tooling |
| typescript | Apache-2.0 | dev only | Types |
| eslint, @eslint/js, typescript-eslint, prettier | MIT | dev only | Lint/format |
| json-schema-to-typescript | MIT | dev only | Type generation |
