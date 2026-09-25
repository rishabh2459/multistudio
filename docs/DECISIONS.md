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
| D25 | 2026-09-23 | Sync analyses audio at **8 kHz mono**; offsets reported at 48 kHz | Speech < 4 kHz is enough; sub-sample peak interpolation gives µs precision; 1 h clip ≈ 115 MB RAM |
| D26 | 2026-09-23 | Sync = coarse GCC-PHAT (1 kHz, whole clip, top-3 candidates) → windowed GCC-PHAT (8 kHz) → robust line fit (RANSAC-style) → second pass reading the clip along the fitted line | Handles partial overlap, drift up to ±500 ppm, noisy windows; drift doesn't smear the peak |
| D27 | 2026-09-23 | PHAT restricted to 80 Hz–0.95·Nyquist with a magnitude floor | Plain PHAT gave false peaks from DC/hum/roll-off bins common to both recordings |
| D28 | 2026-09-23 | Audio decoded by ffmpeg to a pipe (`f32le`); cache as `.npy` in the user cache folder | No soundfile/librosa dependency; re-runs skip decoding |
| D30 | 2026-09-24 | Speaker detection = per-mic loudness relative to that mic's own speech level (P90 while anyone speaks), winner needs a 3 dB lead; talk-over from a 1 s window where 2+ people each hold ≥ 30 % | Camera mics all hear everyone (bleed); relative level calibrates away gain/distance differences |
| D31 | 2026-09-24 | VAD: Silero v5 ONNX (MIT) at 8 kHz on the sync audio, batched in 30 s blocks with 1 s warm-up; energy VAD fallback when the model is missing | ~1 000 model calls per hour of audio (3 × 1 h mics ≈ 11 s); dev works before `make fetch-models` |
| D32 | 2026-09-24 | Switching solved globally with dynamic programming (Viterbi over camera × time-in-shot) instead of a frame-by-frame state machine | Exact min-shot guarantee, cut cost = hysteresis/interruption tolerance, cuts placed just before the next speaker; 1 h plans in < 0.5 s |
| D33 | 2026-09-24 | Scoring: speech time on the right camera; during talk-over any active speaker or the wide counts | Matches the Phase 2 target in TEST_FOOTAGE.md §6 |
| D34 | 2026-09-24 | One timing formula for picture and sound: `pts = audio_start + t·(1+drift) + offset`; video retimed with `setpts`, then `fps` (round=near) to CFR, exact frame counts enforced by trim + clone-pad + trim | Every cut on its exact frame, VFR handled, drift corrected, A/V locked |
| D35 | 2026-09-24 | Render in chunks (≤ 5 min / 24 cuts), each one ffmpeg `filter_complex`; join with the concat demuxer **without re-encoding** | Small graphs for 3-hour/500-cut episodes; join is lossless; verified frame-exact |
| D36 | 2026-09-24 | Master audio mixed in Python (streamed, 48 kHz, Catmull-Rom resampling for drift), piped into the AAC encoder | Sample-exact, no pitch/tempo filters, no clicks at cuts (continuous), no giant temp WAV |
| D37 | 2026-09-24 | Encoder order: VideoToolbox → NVENC → QSV → AMF → Media Foundation → OpenH264 → (libx264 dev only) → mpeg4; each candidate test-encoded before use | Listed ≠ working (e.g. NVENC without GPU); LGPL-friendly; tests run anywhere |
| D38 | 2026-09-24 | Uncovered moments (camera not recording) render as black, with a warning | Never shows wrong/frozen content; user sees it and fixes the cut |
| D39 | 2026-09-25 | Backend = `apps/api` uv workspace member (`multicam_api`, src layout); plan's `infra/local` lives in `multicam_api/infra` | One Python package per app; importable by tests and the future PyInstaller build |
| D40 | 2026-09-25 | Engine objects stored as JSON (their Pydantic dumps) in SQLite rows; cutlists versioned (every save = new row) | Engine stays the single validator; free undo history for Phase 7 |
| D41 | 2026-09-25 | Huey (SQLite storage) runs its worker threads inside the API process, signal handlers disabled; the DB row is the job's source of truth, the queue carries only ids; on startup running→failed, queued→resubmitted | Single-process sidecar; survives crashes cleanly |
| D42 | 2026-09-25 | Per-step input hashes (`step_cache` table): unchanged sync/analysis/decision/render are skipped; `analyze` and `decide` are separate so a new preset re-cuts from the stored analysis (`.npz`) | Instant re-runs; changing preset takes < 1 s |
| D43 | 2026-09-25 | API listens on 127.0.0.1 only; optional per-launch token (`X-Multicam-Token` or `?token=` for SSE) | Stops other local programs / web pages from driving the API |
| D44 | 2026-09-25 | Phase 4 publishes `schemas/openapi.json` (CI-checked); the TypeScript client is generated with openapi-typescript when the UI starts (Phase 5) | Client lives next to its only consumer; contract is fixed now |
| D45 | 2026-09-25 | UI = Next.js 16 static export (`output: 'export'`, `trailingSlash`), React 19, TanStack Query for server state, zustand (localStorage) for settings | Electron loads plain files (no Node server in the app); cache + invalidation handled in one place |
| D46 | 2026-09-25 | No dynamic routes: the project page is `/project/?id=…` (read with `useSearchParams` under Suspense); Setup / Auto edit / Export are steps on that page | Static export cannot pre-render unknown ids; one page keeps live job state while moving between steps |
| D47 | 2026-09-25 | shadcn-style components written in the repo (cva + tailwind-merge, native `<select>`), no Radix yet; system font stack | Few dependencies, works offline, accessible by default; Radix can come with the timeline editor (Phase 7) |
| D48 | 2026-09-25 | API types generated by openapi-typescript into `@multicam/types/api` (`make schemas`, CI-checked); UI uses `Schema<'JobOut'>` etc. | Backend changes break the UI build instead of failing at runtime |
| D49 | 2026-09-25 | Desktop bridge contract `window.multicam` (apiBase, apiToken, pickFiles, pickFolder, showInFolder) defined now; in a browser the UI falls back to typed paths and settings | Phase 6 only has to implement the preload side |
| D50 | 2026-09-25 | One project event stream (`/api/projects/{id}/events`) feeds the jobs cache; polling (1 s) only while the stream is down; a job finishing refetches project, cutlist and exports | One connection per page, instant updates, still works without SSE |
| D51 | 2026-09-25 | CORS middleware is outermost (after the token check) | A wrong token shows as "401" in the browser instead of "cannot reach the engine" |
| D29 | 2026-09-23 | Continue Phase 1 before test footage exists, using synthetic signals + generated video files; phase is marked done only after the real-footage benchmark passes | Unblocks development; accuracy on real devices still has to be proven |

## Dependencies added

| Package | License | Where | Why |
|---------|---------|-------|-----|
| pydantic | MIT | engine | Data model + validation + JSON Schema |
| hatchling | MIT | engine build | Build backend |
| ruff, mypy, pytest, pytest-cov, pre-commit | MIT | dev only | Quality tooling |
| typescript | Apache-2.0 | dev only | Types |
| eslint, @eslint/js, typescript-eslint, prettier | MIT | dev only | Lint/format |
| json-schema-to-typescript | MIT | dev only | Type generation |
| numpy | BSD-3 | engine | Signal arrays (Phase 1) |
| scipy | BSD-3 | engine | FFT, resampling, filters (Phase 1) |
| onnxruntime | MIT | engine | Runs the Silero VAD model (Phase 2) |
| fastapi, starlette | MIT / BSD-3 | api | HTTP API (Phase 4) |
| uvicorn | BSD-3 | api | ASGI server |
| sqlalchemy, alembic | MIT | api | Database + migrations |
| huey | MIT | api | Job queue (SQLite storage) |
| sse-starlette | BSD-3 | api | Server-Sent Events |
| httpx | BSD-3 | dev only | API tests + demo script |
| next, react, react-dom | MIT | web | UI framework (Phase 5) |
| @tanstack/react-query | MIT | web | Server state, caching |
| zustand | MIT | web | Settings store |
| tailwindcss, @tailwindcss/postcss, postcss | MIT | web (build) | Styling |
| class-variance-authority, clsx, tailwind-merge | Apache-2.0 / MIT / MIT | web | Component variants |
| lucide-react | ISC | web | Icons |
| openapi-typescript | MIT | dev only | API types from `schemas/openapi.json` |
| vitest, jsdom, @testing-library/* | MIT | dev only | Component tests |
| @playwright/test | Apache-2.0 | dev only | End-to-end test |
