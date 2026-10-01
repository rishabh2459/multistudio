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
| D52 | 2026-09-25 | The window loads the static UI from a privileged custom scheme `app://multicam/` (served by the main process with a strict CSP), not `file://` | Absolute `/_next/` paths and `/project/?id=` routes work; stable secure origin for CORS (`MULTICAM_CORS=app://multicam`) |
| D53 | 2026-09-25 | Engine lifecycle: `multicam-api --port 0 --watch-stdin`; ready line + health poll; per-launch token; stop = close stdin (kill after 8 s); crash → up to 3 restarts in 5 min on the same port (window reloads only if the port changed) | Same clean shutdown on macOS and Windows; an app crash closes the pipe so the engine never lingers |
| D54 | 2026-09-25 | Backend frozen with PyInstaller one-folder (`packaging/pyinstaller/multicam-api.spec`), static ffmpeg/ffprobe next to the executable (engine looks there when frozen), model inside the bundle; build script smoke-tests it with a minimal PATH | No Python/ffmpeg needed on the user's machine; one-folder starts fast (~2 s) |
| D55 | 2026-09-25 | Preload is sandboxed and exposes only `window.multicam` (config via one sync IPC call; dialogs, show in folder, diagnostics, logs via invoke); IPC answers only frames from our origin | Renderer has no Node access; small, auditable surface |
| D56 | 2026-09-25 | Internal macOS builds are ad-hoc signed (`identity: '-'`), not notarized; Windows NSIS unsigned. Real signing/notarization in Phase 11 | Runs on Apple Silicon for testers (right-click → Open) without paying for certificates yet |
| D57 | 2026-09-26 | NLE exports are built from the render plan's timing (offset + drift): video = one clip per shot trimmed to what the camera recorded; audio = one track per camera, split only where drift would exceed ¼ frame | Export and render cut on the same source frame (integration test); NLEs cannot express clock drift |
| D58 | 2026-09-26 | Formats: FCPXML 1.9 (gap in the spine, shots on lane 1 video-only, camera audio on lanes −1…−n), FCP7 XML v5 for Premiere, CMX3600 EDL video-only with reel names + `FROM CLIP NAME` | Widest support (Final Cut, Resolve 17+, Premiere); EDL for conform tools |
| D59 | 2026-09-26 | Embedded start timecode is read at probe time (`MediaInfo.start_timecode`, optional) and used as the source start in all exports; drop-frame at 29.97/59.94 | NLEs match media by timecode; without it relinking would be off by hours |
| D60 | 2026-09-26 | Editor preview = 540p proxies (`proxy` job, short GOP) played in one `<video>` per camera, re-seeked only when >0.25 s off while playing; audio from the reference camera | Smooth multi-angle scrubbing without decoding 4K originals; one audio source avoids comb filtering |
| D61 | 2026-09-26 | Edit state lives in a per-project zustand store (undo/redo stack, 200 steps); every change is autosaved 0.8 s later as a new CutList version | Nothing is lost; versions double as a history the export and render always read from (latest) |
| D62 | 2026-09-26 | A camera key/click switches cameras *from the playhead* (splits the shot), like a vision mixer; double-click on a camera lane does the same at that point | Matches how multicam editing is done live; the simplest mental model for users |
| D63 | 2026-09-26 | Face detection: YuNet 2023mar ONNX (OpenCV Zoo, MIT, 230 KB) on the existing onnxruntime instead of MediaPipe; pure numpy pre/post-processing | No new heavy dependency (MediaPipe wheels are large and lag Python releases); ~25 ms per 640 px frame on CPU |
| D64 | 2026-09-26 | Faces sampled from keyframes only (`-skip_frame nokey`, 1 frame / 0.5 s), full decode only if keyframes are too sparse; detections cached as a JSON artifact per clip | Decoding keyframes is ~10× faster than full decode; re-running auto framing is instant |
| D65 | 2026-09-26 | Camera path = dead zone + exponential ease run forward and backward (zero lag), then RDP-simplified to keyframes; the render crops with piecewise-linear `x(t)`/`y(t)` expressions | No lag behind the speaker, no jitter, small cutlists; one ffmpeg crop per shot |
| D66 | 2026-09-26 | Punch-ins split a long same-camera run at the on-screen speaker's pause nearest the middle, alternating 1.0× / tight; never mid-sentence | Cuts on pauses feel natural; deterministic, so re-running gives the same result |
| D67 | 2026-09-26 | Segment framing is two fields: `reframe` (16:9, None = full frame) and `reframe_vertical` (9:16, None = centred crop), each optional `path` keys + `manual` flag; auto framing never overwrites manual framing | Both outputs from one edit; hand-tuned shots survive re-runs |
| D29 | 2026-09-23 | Continue Phase 1 before test footage exists, using synthetic signals + generated video files; phase is marked done only after the real-footage benchmark passes | Unblocks development; accuracy on real devices still has to be proven |
| D68 | 2026-09-29 | Plugins are thin; the engine service does all processing (Rule A of `PLUGIN_PLAN.md`) | One engine, one set of tests, all hosts get fixes at once |
| D74 | 2026-09-29 | Switching works on cameras with **cover sets** (`CameraLayout.covers`: which speakers are in frame; shot type solo/two/three/four/wide/broll; priority 0.5–1.5). `Speaker` = name + mic clip (+ channel). Projects without a layout derive it from clip roles (solo per SPEAKER clip, WIDE covers everyone) | Every AutoPod layout and more (two-shots, several angles per person, one multi-channel recorder); old projects cut the same (regression-tested against the v1 algorithm) |
| D78 | 2026-09-29 | Layout/speakers are additive optional fields on `Project` (no `SCHEMA_VERSION` bump); the API stores them in a nullable `projects.layout` JSON column (migration 0002) and prunes references to deleted clips on read | Old JSON stays valid; no data migration needed; a removed clip can't make a project unreadable |
| D79 | 2026-09-29 | Sync confidence also counts a long line of agreeing windows as sharpness (beyond 6 inliers: `1 - exp(-(n-6)/5)`) | Real rooms (T1: 3 iPhones, 69 min, PSR 6–12) aligned correctly on 21/28 windows but scored 0.33 (now 0.77) and warned; periodic sound can fool a handful of windows but not 20 |
| D80 | 2026-09-29 | Variety (`max_shot_s`) = extra Viterbi age states: free until `max_shot_s`, then a cost ramping to 1.0/step over 4 s; cuts allowed from any age ≥ min shot. `wide_frequency` scales group rewards (0.5–1.5×, capped below a solo) and the talk-over window; at the default 0.3 and `max_shot_s = 0` rewards are identical to v1 | Exact optimum stays exact; defaults reproduce old edits; PUNCHY 1 h decide < 1 s |
| D81 | 2026-09-29 | After the 0.1 s Viterbi, each cut onto a new solo speaker is snapped to that speaker's first voiced 10 ms frame minus `lead_s` (within ±1 step, never breaking min shot); each segment gets `confidence` (agreement × speaker margin over the first 0.5 s of speech) | Cuts land on the word, not on a 100 ms grid; plugins can mark low-confidence cuts for review |
| D82 | 2026-09-29 | Analysis warns when > 20 % of speech is labelled cross-talk ("mics hear everyone about equally") | T1 (camera mics only): level difference host/guest mic is unimodal around 0 dB, 29 % of time labelled cross-talk. Better cuts there need per-person mics or visual speaker detection (PL8); say so instead of silently cutting to wide |
| D83 | 2026-09-29 | User presets: `user_presets` table + `/api/presets` (list built-in + user, create, delete, export/import `.mcpreset.json`); a project's custom sliders live in `projects.switch` (cleared when the preset changes) | AutoPod-style saved presets; shareable files; decide cache keys include custom settings and layout |
| D84 | 2026-09-29 | Mics are decoded and analysed in parallel (≤ 4 threads) in sync and analyze | ffmpeg decodes in its own process and ONNX Runtime releases the GIL; T1 analyze 9.5 s → 7.6 s on 2 cores, more on 8+ cores |
| D69 | 2026-10-01 | Host-neutral `EditPlan` (engine `editplan/`) is the only thing plugins apply: live events, every camera split per cut (stacked), audio pieces, markers, approved removals; source times as own-rate frames, samples and Premiere ticks | Adapters stay tiny and never do time maths; XML exporters read the same plan (`plan_to_timeline`) |
| D70 | 2026-10-01 | `GET /api/plugin/v1/sessions/{id}/export?format=fcpxml\|xmeml\|edl` writes the plan as an importable file (Rule C) | A host API gap never blocks the user |
| D75 | 2026-10-01 | Discovery: `multicam-api --headless` / `--discovery` writes `engine.json` (port, random token, pid, api) to the data folder, holds an OS lock (`engine.lock`), prefers port 47811; a second start prints `MULTICAM_API_RUNNING port=N` and exits 0; headless exits after `--idle-exit` (30m) with no request and no job. Desktop registers `multicam://` (`start`, `open?session=`) | Plugins find and start the engine without the app window; one engine per data folder |
| D76 | 2026-10-01 | Plugin API under `/api/plugin/v1` with its own models (`plugin_schemas.py`) and `{code, message, hint}` errors (stable codes); sessions are idempotent on `(host app, host_sequence_id)` and keep the host's clip ids | Plugins update on their own schedule; re-runs reuse the analysis cache |
| D77 | 2026-10-01 | Default apply method `stacked_enable` (stored per session, overridable per request) | Most robust across hosts, easy to adjust by hand |
| D85 | 2026-10-01 | Sound-only files are clips with role `mic` (`MediaInfo.has_video = false`, 100 fps "frames", 0×0): never cameras, only audio tracks; a sound-only reference makes the output follow the first camera | Separate recorders / Zoom H6 tracks from the NLE come in as they are |
| D86 | 2026-10-01 | The desktop app runs its engine with `--discovery`; if a headless engine owns the folder, the app asks it to stop (`POST /api/system/shutdown`, token-only, refused while jobs run) and starts its own. `multicam://start` with the app closed spawns a detached headless engine and quits | Exactly one engine per data folder; plugins and app always share it |
| D87 | 2026-10-01 | Premiere panel applies by **xmeml import** by default (`maxNativeEvents = 0`); native SequenceEditor apply (`cuts` 1 transaction, `stacked_enable` place + disable) ships behind a beta switch until the PL4 spike confirms the UXP DOM | XML import is one undo step and needs no unverified API; native code is ready and mock-tested for PL5 |
| D88 | 2026-10-01 | Premiere selection = the active sequence: video tracks are cameras, audio-only files on audio tracks are mics, the first item per file gives its position; clips all at frame 0 with no trim count as *not* synced (engine runs audio sync) | Works for synced multicam timelines and for clips just dropped in |
| D89 | 2026-10-01 | Shared panel UI takes injectable primitives; Premiere passes UXP Spectrum widgets (`sp-*`, events wired with listeners) | One set of React views for UXP and Electron |

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
| onnxruntime | MIT | engine | Runs the Silero VAD model (Phase 2) and the YuNet face model (Phase 8) |
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
| electron | MIT | desktop | App shell (Phase 6) |
| electron-builder | MIT | dev only | Installers |
| pyinstaller | GPL-2.0 with bootloader exception | build only (`uv run --with`) | Standalone backend; the exception allows shipping the result |
