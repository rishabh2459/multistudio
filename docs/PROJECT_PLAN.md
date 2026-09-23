# Multicam Studio — Master Project Plan

> **Status:** Living document. This is the single source of truth for the project.
> Update the **Progress Tracker** (Section 14) and **Decision Log** (Section 13) as work proceeds.
>
> **Last updated:** 22 September 2026

---

## Table of Contents

1. [Product Summary](#1-product-summary)
2. [Core Principles](#2-core-principles)
3. [Architecture](#3-architecture)
4. [Tech Stack (100% Free & Open Source)](#4-tech-stack-100-free--open-source)
5. [Free-Tools & Licensing Policy](#5-free-tools--licensing-policy)
6. [Where Money Is Unavoidable (and Free Workarounds)](#6-where-money-is-unavoidable-and-free-workarounds)
7. [Project Structure](#7-project-structure)
8. [Core Data Model](#8-core-data-model)
9. [Precision Checklist](#9-precision-checklist)
10. [Phase-wise Development Plan](#10-phase-wise-development-plan)
11. [Testing Strategy](#11-testing-strategy)
12. [Distribution Plan](#12-distribution-plan)
13. [Decision Log](#13-decision-log)
14. [Progress Tracker](#14-progress-tracker)
15. [Working Process](#15-working-process)

---

## 1. Product Summary

A **desktop application** (Windows + macOS) that takes 2+ video files recorded
simultaneously from different cameras (e.g. a podcast), and automatically:

- Syncs all clips using their audio (no timecode or clapperboard needed)
- Detects who is speaking and cuts to that person's camera, like a TV director
- Renders one final, frame-accurate video
- Optionally: auto zoom/reframe, vertical shorts, offline captions, filler-word removal
- Exports editable timelines to Premiere Pro / DaVinci Resolve / Final Cut

**Distribution model:** User downloads **one installer** from our website, installs it,
and works fully offline. Nothing else to install — no Python, no ffmpeg, no models,
no Docker, no account.

**Future:** The same codebase extends to a multi-user cloud version (Phase 13)
without a rewrite.

---

## 2. Core Principles

| # | Principle | What it means in practice |
|---|---|---|
| P1 | **Local-first** | All processing on the user's machine. No uploads, no cloud compute. |
| P2 | **Free & open source only** | Every library, model, and tool must be free with a license that permits our use (see Section 5). |
| P3 | **Minimal external dependency** | No paid APIs, no third-party services required at runtime, no mandatory internet. |
| P4 | **One installer, zero setup** | Python runtime, ffmpeg, and AI models are all bundled inside the app. |
| P5 | **Precision over shortcuts** | Frame-accurate cuts, sub-frame sync, drift correction, continuous audio (see Section 9). |
| P6 | **Cloud-ready architecture** | Storage, queue, and DB sit behind interfaces so a cloud implementation can be swapped in later. |
| P7 | **Engine independent of UI** | The processing engine is a pure Python package usable from CLI, desktop, or cloud workers. |
| P8 | **User stays in control** | Auto-edit is a starting point; the user can review and override every decision. |

---

## 3. Architecture

### 3.1 Desktop mode (what we build now)

```
┌───────────────────────────────────────────────────────────────┐
│                 Electron Desktop App (installer)              │
│                                                               │
│  ┌─────────────────────────┐        ┌──────────────────────┐  │
│  │  Next.js UI             │  HTTP  │  Python Sidecar      │  │
│  │  (static export)        │ ◄────► │  (PyInstaller binary)│  │
│  │  - Dashboard            │  + SSE │                      │  │
│  │  - Clip setup           │        │  FastAPI             │  │
│  │  - Timeline editor      │        │   ├─ SQLite DB       │  │
│  │  - Export               │        │   ├─ Huey job queue  │  │
│  └─────────────────────────┘        │   └─ engine/         │  │
│                                     │       ├─ sync        │  │
│  Electron main process:             │       ├─ vad/switch  │  │
│  - spawns & monitors sidecar        │       ├─ render      │  │
│  - native file dialogs              │       ├─ reframe     │  │
│  - auto-updates                     │       ├─ transcribe  │  │
│                                     │       └─ export      │  │
│                                     │                      │  │
│                                     │  Bundled: ffmpeg,    │  │
│                                     │  ONNX/CT2 models     │  │
│                                     └──────────────────────┘  │
│                                                               │
│  User's video files are read in place (never copied/uploaded) │
└───────────────────────────────────────────────────────────────┘
```

### 3.2 Swappable infrastructure layer

| Interface | Desktop implementation (now) | Cloud implementation (Phase 13) |
|---|---|---|
| `Database` | SQLite (via SQLAlchemy) | PostgreSQL (same SQLAlchemy models) |
| `StorageBackend` | Local filesystem paths | S3-compatible object storage (self-hosted MinIO or any S3) |
| `JobQueue` | Huey with SQLite backend | Celery + Redis/Valkey |
| `Auth` | None (single user) | Self-built auth |
| UI hosting | Static files inside Electron | Same Next.js build served on web |

Config flag `MODE=desktop | cloud` selects implementations. Engine code never changes.

### 3.3 Processing pipeline

```
Clips ──► 1. Probe & Normalize ──► 2. Sync (offset + drift)
                                            │
                                            ▼
          3. Analyze (VAD + energy per track, faces, transcript)
                                            │
                                            ▼
          4. Decide (switch logic → CutList, filler/silence marks)
                                            │
                                            ▼
          5. Review (timeline editor, manual overrides)
                                            │
                                            ▼
          6. Output (render video | export FCPXML/XML/EDL | SRT/VTT)
```

Each step writes cached results, so re-running after an edit only redoes what changed.

---

## 4. Tech Stack (100% Free & Open Source)

### 4.1 Frontend

| Purpose | Tool | License | Cost |
|---|---|---|---|
| UI framework | Next.js (static export: `output: 'export'`) | MIT | Free |
| Language | TypeScript | Apache-2.0 | Free |
| UI library | React | MIT | Free |
| Styling | Tailwind CSS | MIT | Free |
| Components | shadcn/ui (+ Radix primitives) | MIT | Free |
| Waveforms | wavesurfer.js | BSD-3 | Free |
| State management | Zustand | MIT | Free |
| Server-state / fetching | TanStack Query | MIT | Free |
| API client generation | openapi-typescript | MIT | Free |
| Icons | lucide-react | ISC | Free |

> Next.js runs in **static export** mode inside the desktop app: no Node server,
> no Next.js API routes. All logic lives in the Python backend.

### 4.2 Desktop shell

| Purpose | Tool | License | Cost |
|---|---|---|---|
| Desktop runtime | Electron | MIT | Free |
| Installer builder | electron-builder | MIT | Free |
| Auto-update | electron-updater (serves from GitHub Releases) | MIT | Free |

**Why Electron over Tauri:** Electron ships its own Chromium, so video playback and
codec behaviour are identical on Windows and macOS. Tauri uses the OS webview, where
codec support differs. Since the bundle is large anyway (models + Python), Tauri's
size advantage matters little here.

### 4.3 Backend

| Purpose | Tool | License | Cost |
|---|---|---|---|
| Language | Python 3.11+ | PSF | Free |
| Package manager | uv | MIT / Apache-2.0 | Free |
| API framework | FastAPI + Uvicorn | MIT / BSD | Free |
| Validation | Pydantic v2 | MIT | Free |
| ORM | SQLAlchemy 2.x | MIT | Free |
| Migrations | Alembic | MIT | Free |
| Database | SQLite | Public domain | Free |
| Job queue | Huey (SQLite storage) | MIT | Free |
| Live progress | Server-Sent Events (sse-starlette) | BSD-3 | Free |

### 4.4 Processing engine

| Purpose | Tool | License | Cost |
|---|---|---|---|
| Video/audio I/O & render | FFmpeg (**LGPL build**, see 5.3) | LGPL-2.1 | Free |
| Numerics | NumPy, SciPy | BSD-3 | Free |
| Audio analysis | librosa, soundfile | ISC / BSD-3 | Free |
| Sync algorithm | GCC-PHAT (own implementation on SciPy FFT) | Ours | Free |
| Voice activity detection | Silero VAD (ONNX model) | MIT | Free |
| Model runtime | ONNX Runtime | MIT | Free |
| Transcription | faster-whisper (CTranslate2 backend) | MIT | Free |
| Whisper model weights | OpenAI Whisper (converted to CT2) | MIT | Free |
| Face detection | MediaPipe | Apache-2.0 | Free |
| Image ops | OpenCV (headless) | Apache-2.0 | Free |
| Smoothing | Own EMA/Kalman implementation | Ours | Free |
| Timeline export | Own FCPXML / Premiere XML / EDL writers | Ours | Free |

**No PyTorch.** Everything runs on ONNX Runtime or CTranslate2. This keeps the
installer around 400–700 MB instead of 2–3 GB. GPU acceleration comes from
ONNX Runtime execution providers (CoreML on macOS, DirectML on Windows) with no
CUDA install required.

### 4.5 Tooling, testing, packaging

| Purpose | Tool | License | Cost |
|---|---|---|---|
| Version control | Git | GPL-2.0 (tool only) | Free |
| Repo hosting | GitHub (or self-hosted Gitea/Forgejo) | — | Free tier |
| JS package manager | pnpm | MIT | Free |
| Python lint/format | Ruff | MIT | Free |
| Type checking | mypy / pyright | MIT | Free |
| JS lint/format | ESLint, Prettier | MIT | Free |
| Python tests | pytest, pytest-cov | MIT | Free |
| JS tests | Vitest | MIT | Free |
| E2E tests | Playwright | Apache-2.0 | Free |
| Python bundling | PyInstaller (or Nuitka) | GPL + bootloader exception / Apache-2.0 | Free |
| CI/CD | GitHub Actions (or local builds) | — | Free tier |
| Website | Next.js static site on GitHub Pages or Cloudflare Pages | — | Free tier |
| Installer hosting | GitHub Releases | — | Free |
| Crash/error logs | Local log files + "Copy diagnostic report" button | Ours | Free |

---

## 5. Free-Tools & Licensing Policy

### 5.1 Allowed licenses (safe for a closed-source commercial product)

MIT, BSD (2/3-clause), Apache-2.0, ISC, PSF, Public Domain, zlib,
LGPL (**only** when dynamically linked / used as a separate executable, e.g. ffmpeg binary).

### 5.2 Not allowed (unless product becomes open source / non-commercial)

| Category | Examples | Why |
|---|---|---|
| Non-commercial licenses | CC BY-NC, "research only" models (e.g. CrisperWhisper) | Cannot be used in a product we sell |
| GPL-linked code | GPL ffmpeg builds with libx264/libx265 | Would force our whole app to be GPL |
| Gated models | Models needing account/token acceptance (e.g. pyannote on Hugging Face) | External dependency + licensing risk |
| Paid APIs | OpenAI API, cloud transcription, cloud vision | Violates P2/P3 |
| Runtime third-party services | Hosted analytics, hosted crash reporting | Violates P3 and user privacy |

**Rule:** Before adding any dependency, record its name and license in the Decision
Log (Section 13). If the license isn't in 5.1, don't add it.

> This is an engineering policy, not legal advice. Before a commercial launch,
> have the final dependency list reviewed.

### 5.3 FFmpeg & video codec strategy

H.264/HEVC encoding has patent-licensing implications, and the best CPU encoders
(x264/x265) are GPL. Our approach:

1. Bundle an **LGPL ffmpeg build** as a separate executable (not linked into our code).
2. Encode using **OS-provided hardware/system encoders**, which are licensed by the OS vendor:
   - macOS: VideoToolbox (`h264_videotoolbox`, `hevc_videotoolbox`)
   - Windows: Media Foundation (`h264_mf`, `hevc_mf`), plus NVENC / QSV / AMF where available
3. CPU fallback: libopenh264 (BSD) for H.264.
4. Optional royalty-free output: AV1 via SVT-AV1 (BSD).
5. **Decoding** is done by ffmpeg's built-in decoders; preview playback uses Electron's Chromium.

If the project is ever released as open source (GPL), switch to a GPL build with
x264/x265 for higher CPU-encode quality.

---

## 6. Where Money Is Unavoidable (and Free Workarounds)

Development is 100% free. Only **distribution trust** has costs:

| Item | Why it costs | Paid option | Free workaround |
|---|---|---|---|
| macOS code signing + notarization | Apple requires a Developer account | Apple Developer Program (~$99/year) | Ship unsigned; user opens via **System Settings → Privacy & Security → Open Anyway** (one-time). Acceptable for beta, poor for wide launch. |
| Windows code signing | Removes "Unknown publisher" SmartScreen warning | OV certificate or Azure Trusted Signing (monthly fee) | Ship unsigned; user clicks **More info → Run anyway**. Warnings reduce as download reputation grows. |
| CI build minutes for private repos | macOS runners consume free minutes fast | Paid GitHub plan | Build locally on own Windows PC + own Mac (a Mac is required to build the macOS app). Public repos get free CI. |
| Payments (only if selling) | Payment gateway fees | Razorpay / Stripe (per-transaction, no fixed fee) | Not needed until monetizing |

**Plan:** Build and beta-test unsigned (free). Add signing just before public launch.

---

## 7. Project Structure

```
multicam-studio/
├── apps/
│   ├── web/                      # Next.js UI (desktop + future website)
│   │   ├── app/                  # routes: dashboard, project/[id], editor, settings
│   │   ├── components/           # uploader, clip-setup, timeline, player, progress
│   │   ├── lib/                  # api client (generated), sse hooks, stores
│   │   └── next.config.ts        # output: 'export'
│   ├── desktop/                  # Electron
│   │   ├── main/                 # sidecar launcher, window, dialogs, updater
│   │   ├── preload/              # safe IPC bridge
│   │   └── electron-builder.yml
│   ├── site/                     # marketing + download page (static)
│   └── api/                      # FastAPI app
│       ├── main.py
│       ├── routers/              # projects, clips, jobs, exports, system
│       ├── schemas/              # Pydantic models
│       ├── db/                   # SQLAlchemy models, Alembic migrations
│       └── jobs/                 # Huey task definitions (call engine)
├── packages/
│   └── types/                    # TS types generated from engine models (D17)
├── engine/src/multicam_engine/   # pure Python package, no web code (src layout, D16)
│   ├── media/                    # probe, normalize, audio extraction, proxies
│   ├── sync/                     # gcc_phat, drift, confidence
│   ├── analysis/                 # vad (silero onnx), energy, bleed, noise floor
│   ├── decide/                   # switch logic, presets, hysteresis
│   ├── reframe/                  # face detection, smoothing, crop planning
│   ├── transcribe/               # faster-whisper, word timings, fillers
│   ├── render/                   # filter_complex builder, encoders, audio mix
│   ├── export/                   # fcpxml, premiere xml, edl, srt, vtt
│   ├── models/                   # CutList, Segment, time math (shared types)
│   ├── benchmark/                # ground truth + accuracy scoring
│   └── cli.py                    # `multicam` command
├── infra/
│   ├── local/                    # SQLite, filesystem storage, Huey config
│   └── cloud/                    # (Phase 13) Postgres, S3, Celery
├── packaging/
│   ├── pyinstaller.spec
│   ├── ffmpeg/                   # per-platform LGPL binaries (fetched by script)
│   ├── models/                   # bundled model files (fetched by script)
│   └── scripts/                  # build + fetch scripts
├── tests/
│   ├── unit/                     # synthetic-signal tests
│   ├── integration/              # engine end-to-end on short clips
│   ├── accuracy/                 # real-footage benchmarks vs ground truth
│   └── e2e/                      # Playwright UI tests
├── samples/                      # test footage (git-ignored, see 11.2)
├── docs/
│   ├── PROJECT_PLAN.md           # ← this file
│   ├── ARCHITECTURE.md
│   └── DECISIONS.md
├── .github/workflows/
├── pyproject.toml
├── pnpm-workspace.yaml
└── README.md
```

---

## 8. Core Data Model

Defined in Phase 0; this is the contract between engine, API, and UI.

**Rule: all timeline positions are stored as integer frames (or rational time), never floats.**
Float seconds accumulate rounding error and cause off-by-one-frame cuts.

```jsonc
// Project
{
  "id": "uuid",
  "name": "Episode 42",
  "output": { "fps": [30000, 1001], "width": 1920, "height": 1080 },
  "preset": "balanced",               // calm | balanced | dynamic
  "clips": ["clip-id", "..."],
  "created_at": "iso8601"
}

// Clip
{
  "id": "uuid",
  "path": "/Users/.../cam1.mp4",      // referenced in place, never copied
  "role": "speaker",                   // speaker | wide | broll
  "speaker_label": "Host",
  "media": {
    "fps": [30000, 1001], "is_vfr": true, "duration_frames": 108000,
    "width": 3840, "height": 2160, "audio_sample_rate": 48000, "audio_channels": 2,
    "codec": "hevc"
  },
  "sync": {
    "offset_samples": -73512,          // relative to reference clip
    "drift_ppm": 14.2,                 // clock drift, parts per million
    "confidence": 0.97
  }
}

// CutList
{
  "version": 3,                        // bumps on every edit (undo/redo)
  "project_id": "uuid",
  "segments": [
    {
      "start_frame": 0, "end_frame": 184,
      "clip_id": "uuid",
      "source": "auto",                // auto | manual
      "reframe": { "cx": 0.52, "cy": 0.41, "scale": 1.3 }   // optional
    }
  ],
  "removals": [                        // fillers / silences approved by user
    { "start_frame": 912, "end_frame": 931, "kind": "filler", "approved": true }
  ],
  "audio": { "mode": "mix", "gains_db": { "clip-id": 0.0 } }
}
```

---

## 9. Precision Checklist

Every item below must be satisfied before the related phase is marked done.

| # | Problem | Solution | Phase |
|---|---|---|---|
| X1 | Different devices' clocks drift apart (100–300 ms/hour) | Multi-window sync + linear drift model; resample audio / retime video | 1 |
| X2 | Phone footage is variable frame rate (VFR) | Detect VFR; map by timestamps, render to constant frame rate | 1, 3 |
| X3 | Single global offset is unreliable on noisy audio | GCC-PHAT + confidence score + fallback windows | 1 |
| X4 | Stream-copy cuts only land on keyframes | Always re-encode output; single `filter_complex` render | 3 |
| X5 | Cutting audio per segment causes clicks/gaps | Continuous master audio track; only video switches | 3 |
| X6 | Float timestamps cause off-by-one frames | Integer frames / rational time everywhere | 0, 3 |
| X7 | Mic bleed triggers wrong cuts | Per-mic noise floor + relative energy + VAD gating | 2 |
| X8 | Rapid back-and-forth cuts | Min shot duration + hysteresis + interruption tolerance | 2 |
| X9 | Face crop jitters | EMA/Kalman smoothing + dead-zone before moving | 8 |
| X10 | Whisper drops "um/uh" | Verbatim prompting + VAD/energy-based filler detection + user review | 10 |
| X11 | Filler cuts sound abrupt | Short audio crossfades; cut all cameras at the same frame | 10 |
| X12 | Hinglish transcripts mix scripts | Language + script preference setting; post-processing | 9 |

---

## 10. Phase-wise Development Plan

Estimates assume **one developer working full-time**. Part-time ≈ double.
Total for the desktop product: **~4–5 months full-time**.

| Phase | Deliverable | Estimate |
|---|---|---|
| 0 | Foundation, repo, data model, test footage | 3–4 days |
| 1 | Sync engine with drift correction | 1–1.5 weeks |
| 2 | Speaker detection + switch logic | 1–1.5 weeks |
| 3 | Frame-accurate render engine | 1 week |
| 4 | Backend (FastAPI + SQLite + Huey) | 1 week |
| 5 | Next.js UI v1 | 1.5–2 weeks |
| 6 | Electron desktop app (first installable build) | 1 week |
| 7 | Timeline editor + NLE export | 2–3 weeks |
| 8 | Auto zoom/reframe + vertical shorts | 1.5 weeks |
| 9 | Offline captions (Hindi/English/Hinglish) | 1.5 weeks |
| 10 | Filler word + silence removal | 1 week |
| 11 | Packaging, updates, website | 1.5–2 weeks |
| 12 | Beta testing + hardening | 2 weeks |
| 13 | (Future) Multi-user cloud version | Separate project |

---

### Phase 0 — Foundation

**Goal:** A solid base everything else stands on.

**Tasks**
- [ ] Monorepo: pnpm workspaces (JS) + uv (Python)
- [ ] Ruff, mypy/pyright, ESLint, Prettier, pre-commit hooks
- [ ] GitHub repo + Actions workflow running lint + tests on every push
- [ ] Define core data model (Section 8) as Pydantic models + generated TS types
- [ ] Record decisions: app name, ffmpeg LGPL strategy, license policy
- [ ] `packaging/scripts/fetch_ffmpeg` and `fetch_models` scripts (dev machines)
- [ ] Build test footage library (Section 11.2) with ground-truth annotation files

**Done when:** A fresh clone sets up with one command, CI is green, and test footage + ground truth exist.

---

### Phase 1 — Sync Engine

**Goal:** Align any set of clips with sub-frame accuracy.

**Tasks**
- [x] `media/probe`: ffprobe wrapper (fps, VFR detection, duration, codecs, audio layout)
- [x] `media/audio`: extract mono audio at fixed rate; cache to disk
- [x] `sync/gcc_phat`: coarse offset via GCC-PHAT on downsampled audio, refine at full rate
- [x] `sync/drift`: sync N windows across the recording, fit linear drift model
- [x] `sync/confidence`: peak sharpness + window agreement → 0–1 score
- [x] Handle clips that start late / end early / have partial overlap
- [x] Handle very weak or silent audio (low confidence → user warning, no crash)
- [x] CLI: `multicam sync cam1.mp4 cam2.mp4 --out sync.json`
- [x] Unit tests: synthetic signals with known offset, known drift, added noise
- [ ] Accuracy benchmark on real footage (T1, T3, T5, T6): `make test-accuracy`

**Done when:** On the test library, sync error < 1 frame at start **and** end of 60+ minute recordings; low-quality audio yields a warning, not a crash.

---

### Phase 2 — Speaker Detection + Switch Logic

**Goal:** Make cutting decisions like a human director.

**Tasks**
- [ ] `analysis/vad`: Silero VAD via ONNX Runtime, per track
- [ ] `analysis/energy`: per-window RMS in dB, per-mic noise-floor calibration
- [ ] `analysis/bleed`: relative-energy scoring so a faint voice on another mic doesn't win
- [ ] `decide/switch`: active-speaker timeline → CutList with min shot length, hysteresis, interruption tolerance
- [ ] Wide-shot rules: cross-talk or silence → wide camera (if assigned)
- [ ] Presets: calm / balanced / dynamic (parameter sets, stored in project)
- [ ] CLI: `multicam cutlist --sync sync.json --preset balanced`
- [ ] Accuracy script: compare CutList vs ground-truth speaker annotations

**Done when:** Speaker accuracy on test library meets the target set in Phase 0 (e.g. ≥ 95% of speech time on the correct camera), with no cuts shorter than the minimum shot length.

---

### Phase 3 — Render Engine

**Goal:** Broadcast-quality output from a CutList.

**Tasks**
- [ ] `render/graph`: build a single ffmpeg `filter_complex` from the CutList
- [ ] Apply sync offsets + drift correction per clip in the graph
- [ ] Continuous master audio (mix or chosen track, per-clip gain)
- [ ] Frame snapping; VFR → CFR output
- [ ] Encoder selection: VideoToolbox / Media Foundation / NVENC / QSV / AMF, openh264 fallback
- [ ] Proxy generation (low-res, all-intra-friendly) for the editor
- [ ] Output presets: YouTube 1080p, YouTube 4K, high-quality master
- [ ] Progress parsing (percent + ETA) and cancellation
- [ ] Very long timelines: chunked render + lossless join if graph gets too large

**Done when:** A 60-minute 3-camera episode renders with every cut on the exact frame and no audible artifacts at cut points.

---

### Phase 4 — Backend

**Goal:** Turn the engine into a controllable local service.

**Tasks**
- [ ] FastAPI app; routers for projects, clips, jobs, exports, system info
- [ ] SQLAlchemy models + Alembic migrations on SQLite
- [ ] `StorageBackend`, `JobQueue` interfaces with local implementations
- [ ] Huey tasks: probe, sync, analyze, decide, render, export
- [ ] SSE endpoint for live job progress; cancel + retry
- [ ] Reference files by path; detect moved/missing files gracefully
- [ ] Caching: skip steps whose inputs haven't changed
- [ ] OpenAPI schema → generated TS client
- [ ] API tests with pytest + httpx

**Done when:** A script can create a project, add clips, run the full pipeline, and get the final video — entirely via the API.

---

### Phase 5 — Next.js UI v1

**Goal:** First usable interface.

**Tasks**
- [ ] Next.js static-export setup, Tailwind, shadcn/ui, design tokens, dark/light theme
- [ ] Screens: Dashboard → New Project → Clip Setup → Processing → Result
- [ ] Clip setup: assign speaker names, mark wide camera, choose preset
- [ ] Live progress via SSE; sync confidence warnings
- [ ] Result preview player + export options
- [ ] Settings: output folder, encoder, default preset
- [ ] Vitest component tests; Playwright happy-path test

**Done when:** The full flow works end-to-end in a browser against the local API.

---

### Phase 6 — Electron Desktop App

**Goal:** First double-click, installable build.

**Tasks**
- [ ] Electron main process loads the static Next.js build
- [ ] Sidecar launcher: pick free port, spawn Python binary, health check, restart on crash, clean shutdown
- [ ] Secure IPC via preload (native file/folder dialogs, open-in-finder/explorer)
- [ ] First PyInstaller build of the backend with ffmpeg + models bundled
- [ ] Log files in the OS app-data folder; "Copy diagnostic report" button
- [ ] Unsigned internal builds for Windows x64 and macOS (Apple Silicon + Intel)

**Done when:** On a clean machine with **no Python and no ffmpeg installed**, the app installs and runs the full flow.

---

### Phase 7 — Timeline Editor + NLE Export

**Goal:** Let users review and fix the auto-edit; hand off to pro editors.

**Tasks**
- [ ] Timeline: per-camera lanes, waveforms, color-coded segments, playhead, zoom
- [ ] Edit actions: change camera for a segment, drag cut points, split, merge
- [ ] Multi-angle preview from proxies, kept in sync with the playhead
- [ ] Undo/redo (CutList versions) + autosave
- [ ] Keyboard shortcuts (1/2/3 to switch camera, J/K/L playback)
- [ ] Export: FCPXML (Final Cut / DaVinci), Premiere XML, CMX3600 EDL
- [ ] Verify exports open correctly in DaVinci Resolve (free) and Premiere

**Done when:** Any cut can be changed and re-rendered correctly, and exports open with correct sync in DaVinci Resolve and Premiere.

---

### Phase 8 — Auto Zoom / Reframe

**Goal:** Dynamic framing + vertical shorts.

**Tasks**
- [ ] MediaPipe face detection on sampled frames; track faces per clip
- [ ] Smoothing (EMA/Kalman) + dead-zone to prevent jitter
- [ ] Punch-in variation: alternate wide/tight on the same camera
- [ ] 9:16 vertical export keeping the active speaker centered
- [ ] Per-segment zoom editable in the timeline
- [ ] Graceful fallback when no face is found (center crop, no crash)

**Done when:** Both 16:9 and 9:16 outputs keep faces smoothly framed; low light degrades gracefully.

---

### Phase 9 — Offline Captions

**Goal:** Accurate captions without any cloud service.

**Tasks**
- [ ] faster-whisper with word-level timestamps, VAD-filtered
- [ ] Model size decision (accuracy vs installer size vs speed) — benchmark small / medium / turbo on Hindi + English test clips
- [ ] Languages: English, Hindi, Hinglish; script preference (Roman / Devanagari)
- [ ] Caption editor in UI (text + timing)
- [ ] Style presets (font, size, colors, word-by-word highlight) rendered via ASS subtitles
- [ ] Export SRT / VTT; burn-in option

**Done when:** A 60-minute episode transcribes in acceptable time on a normal laptop, and captions stay in sync.

---

### Phase 10 — Filler Word + Silence Removal

**Goal:** A tight, clean edit.

**Tasks**
- [ ] Filler detection: verbatim prompting + word timings + VAD/energy gap analysis
- [ ] Silence detection with configurable threshold and padding
- [ ] Review list UI: approve/reject each removal, preview each one
- [ ] Apply removals across all cameras at the same frame, with audio crossfades
- [ ] Captions and CutList retimed automatically after removals

**Done when:** Output sounds natural, and every removal can be undone.

---

### Phase 11 — Packaging & Distribution

**Goal:** Anyone can download from the website and run it.

**Tasks**
- [ ] Final PyInstaller (or Nuitka) config; minimize bundle size
- [ ] electron-builder: NSIS `.exe` (Windows), `.dmg` (macOS arm64 + x64)
- [ ] electron-updater with GitHub Releases as the update feed
- [ ] Build pipeline: GitHub Actions (public repo) or documented local build scripts
- [ ] Download page on the static site (GitHub Pages / Cloudflare Pages)
- [ ] First-run experience: short onboarding, sample project
- [ ] (Optional) Offline license keys: Ed25519-signed keys verified locally, no server
- [ ] (Before public launch) Code signing + notarization (Section 6)

**Done when:** Fresh Windows and Mac machines can download → install → run, and receive an update automatically.

---

### Phase 12 — Beta & Hardening

**Goal:** Ready for real users.

**Tasks**
- [ ] 10–20 beta users; structured feedback form
- [ ] Performance tuning for low-end laptops (8 GB RAM, integrated GPU)
- [ ] Stress tests: 3-hour recordings, 4+ cameras, low disk space
- [ ] Format coverage: MOV, MP4, MKV, iPhone HEVC, ProRes, 10-bit
- [ ] Corrupt/partial files handled with clear error messages
- [ ] User guide + troubleshooting docs

**Done when:** No open critical bugs from beta; crash rate acceptably low.

---

### Phase 13 — Multi-user Cloud Version (Future)

Not built now. Made possible by the interfaces in Phases 0 and 4.

- PostgreSQL implementation of `Database`
- S3-compatible `StorageBackend` (self-hosted MinIO or any S3 provider)
- Celery + Redis/Valkey `JobQueue`, GPU worker pool
- Self-built authentication, team workspaces, sharing
- Resumable large uploads (tus protocol, self-hosted)
- Billing and usage limits
- One account across desktop and cloud

---

## 11. Testing Strategy

### 11.1 Test layers

| Layer | Tool | What it checks | When |
|---|---|---|---|
| Unit | pytest | Sync, drift, VAD gating, switch rules, filter graph generation on synthetic data | Every commit |
| Integration | pytest | Engine end-to-end on short (30–60 s) real clips | Every commit |
| Accuracy benchmark | pytest + scripts | Sync error, speaker accuracy, caption WER vs ground truth | Every phase + before release |
| API | pytest + httpx | Endpoints, jobs, error paths | Every commit |
| UI | Vitest, Playwright | Components and full user flows | Every commit (from Phase 5) |
| Install test | Manual checklist | Clean Windows + Mac install, first run, update | Every release |

### 11.2 Test footage library

Stored outside git (too large). Each recording has a ground-truth JSON with
true offsets and who-spoke-when annotations.

| ID | Setup | Tests |
|---|---|---|
| T1 | 2 cams, 2 speakers, quiet room, ~5 min | Baseline |
| T2 | 3 cams (2 speakers + wide), ~10 min | Wide-shot logic |
| T3 | Phone + webcam, VFR phone footage | VFR handling |
| T4 | Noisy room / fan / AC hum | VAD robustness |
| T5 | Heavy cross-talk and interruptions | Hysteresis, bleed |
| T6 | 60+ minutes, different devices | Clock drift |
| T7 | Hindi + Hinglish conversation | Captions, fillers |
| T8 | Low light | Face detection fallback |

### 11.3 Regression rule

No phase is complete if any earlier accuracy benchmark gets worse.

---

## 12. Distribution Plan

| Item | Plan |
|---|---|
| Platforms | Windows 10/11 x64; macOS 12+ on Apple Silicon and Intel |
| Installer size target | ~400–700 MB (depends on bundled Whisper model) |
| Installer hosting | GitHub Releases (free) |
| Website | Static site on GitHub Pages / Cloudflare Pages (free) |
| Updates | electron-updater reading GitHub Releases |
| Internet required? | Only to download the installer and check for updates (update check can be disabled) |
| User data | Stays on the user's machine; no telemetry by default |
| Signing | Unsigned during beta; signed before public launch (Section 6) |

---

## 13. Decision Log

Record every significant decision here (or in `docs/DECISIONS.md`). **D14 onwards live in `docs/DECISIONS.md`.**

| # | Date | Decision | Reason |
|---|---|---|---|
| D1 | 2026-09-22 | Desktop app first, cloud later | Local-first, no infra cost; architecture keeps cloud possible |
| D2 | 2026-09-22 | Electron over Tauri | Consistent Chromium video playback on Win + Mac |
| D3 | 2026-09-22 | Next.js in static-export mode | Same UI reusable for future web version |
| D4 | 2026-09-22 | No PyTorch; ONNX Runtime + CTranslate2 | Installer ~400–700 MB instead of 2–3 GB |
| D5 | 2026-09-22 | Silero VAD instead of webrtcvad | Better accuracy on noisy audio |
| D6 | 2026-09-22 | faster-whisper instead of openai-whisper | Faster, no torch, word timestamps |
| D7 | 2026-09-22 | Skip pyannote in desktop version | Requires torch + gated model |
| D8 | 2026-09-22 | LGPL ffmpeg + OS encoders | Avoid GPL + codec patent issues for closed source |
| D9 | 2026-09-22 | Free/open-source-only policy (Section 5) | No external dependency, no recurring cost |
| D10 | 2026-09-22 | Integer frames for all timeline math | Frame-accurate precision |
| D11 | 2026-09-22 | Working name: Multicam Studio | Placeholder until branding |
| D12 | — | Bundled Whisper model size | *Open — decide in Phase 9 after benchmark* |
| D13 | — | Open source or closed source? | *Open — affects ffmpeg build choice* |

---

## 14. Progress Tracker

| Phase | Status | Started | Completed | Notes |
|---|---|---|---|---|
| 0 — Foundation | 🔄 In progress | 2026-09-22 | | Scaffold done; test footage pending |
| 1 — Sync engine | 🔄 In progress | 2026-09-23 | | Code + synthetic tests done (1 h clip: < 0.3 ms error, ~5 s). Real-footage benchmark pending (D29) |
| 2 — Speaker detection + switch | ⬜ Not started | | | Reuse existing `switch.py` if available |
| 3 — Render engine | ⬜ Not started | | | |
| 4 — Backend | ⬜ Not started | | | |
| 5 — Next.js UI v1 | ⬜ Not started | | | |
| 6 — Electron desktop | ⬜ Not started | | | |
| 7 — Timeline editor + export | ⬜ Not started | | | |
| 8 — Reframe | ⬜ Not started | | | |
| 9 — Captions | ⬜ Not started | | | |
| 10 — Filler removal | ⬜ Not started | | | |
| 11 — Packaging & distribution | ⬜ Not started | | | |
| 12 — Beta & hardening | ⬜ Not started | | | |
| 13 — Cloud (future) | ⬜ Not started | | | |

Legend: ⬜ Not started · 🔄 In progress · ✅ Done · ⏸ Blocked

---

## 15. Working Process

1. **Start a phase:** Share this file + the current code state (or relevant files) so context is complete.
2. **Build:** Code is written phase by phase, file by file, with tests.
3. **Run locally:** Run tests and the pipeline on your own machine with the test footage.
4. **Report:** Share errors, logs, and accuracy numbers.
5. **Fix & tune:** Iterate until the phase's "Done when" criteria pass.
6. **Close the phase:** Update the Progress Tracker and Decision Log, commit, tag (`phase-N-done`).

**Golden rules**
- The engine never imports web/UI code.
- Every new dependency is checked against Section 5 and logged in Section 13.
- No phase ships if an earlier benchmark regresses.
- The data model (Section 8) changes only with a version bump and a migration.
