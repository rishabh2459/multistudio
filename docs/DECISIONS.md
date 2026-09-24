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
