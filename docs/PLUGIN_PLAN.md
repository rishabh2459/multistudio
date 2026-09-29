# Multicam Studio — NLE Plugin Plan

> **Status:** In progress — see the [progress tracker](#14-progress-tracker). Companion to `docs/PROJECT_PLAN.md` (phases 0–13) and
> `docs/DECISIONS.md` (D1–D67). Plugin phases are numbered **PL0–PL10** so they never
> clash with the main phases.
>
> **Written:** 29 September 2026 · **Owner:** Rishabh
>
> **One-line goal:** turn the existing local engine into plugins for Premiere, DaVinci
> Resolve and Final Cut that edit a multicam podcast *better and faster than AutoPod*,
> while the standalone app keeps working on the same engine.

---

## Table of Contents

1. [Why a plugin, and what "better than AutoPod" means](#1-why-a-plugin-and-what-better-than-autopod-means)
2. [What we take from AutoPod, and what we fix](#2-what-we-take-from-autopod-and-what-we-fix)
3. [Architecture](#3-architecture)
4. [Repository changes](#4-repository-changes)
5. [Data model additions](#5-data-model-additions)
6. [Plugin API v1 (engine ⇄ plugin contract)](#6-plugin-api-v1-engine--plugin-contract)
7. [Fast, correct camera switching](#7-fast-correct-camera-switching)
8. [Host adapters: how each NLE is driven](#8-host-adapters-how-each-nle-is-driven)
9. [Phase-wise plan (PL0–PL10)](#9-phase-wise-plan-pl0pl10)
10. [Acceptance criteria: the "beat AutoPod" scorecard](#10-acceptance-criteria-the-beat-autopod-scorecard)
11. [Testing strategy for plugins](#11-testing-strategy-for-plugins)
12. [Risks and open questions](#12-risks-and-open-questions)
13. [Decisions to record (D68+)](#13-decisions-to-record-d68)
14. [Progress tracker](#14-progress-tracker)

---

## 1. Why a plugin, and what "better than AutoPod" means

Editors already live inside Premiere / Resolve / Final Cut. A plugin puts our auto-edit
where they work, and the result stays fully editable on their own timeline.

**AutoPod today (baseline, from autopod.fm, checked 29 Sep 2026):**

| Area | AutoPod | Consequence |
|---|---|---|
| Hosts | Premiere Pro 2023+ and DaVinci Resolve | No Final Cut, no Avid |
| Multicam editor | Up to 10 cameras + 10 mics; solo / two / three / four / wide shots; presets; "increase wide shots"; output as cuts, multicam, or enable/disable | Strong baseline — we must match all of this |
| Audio requirement | Needs a **separate mic per speaker**; no single-audio-source mode, no single-speaker mode | Big gap: many creators record one mixed track |
| Sync | Expects footage already synced / in a multicam sequence | Extra manual step for the user |
| Social clips | In/out → new sequence at 16:9, 4:5, 9:16; watermark, end page, batch export; **reframing uses Premiere's built-in auto-reframe** | Generic reframe, not speaker-aware |
| Jump cuts | Silence cut by a **dB threshold** | Breaks on noisy rooms, no filler words |
| Licence | $29/month, one machine per key | Friction when switching machines |

**Our targets** (details and numbers in [Section 10](#10-acceptance-criteria-the-beat-autopod-scorecard)):

1. **Parity:** every AutoPod feature above works in our Premiere and Resolve plugins.
2. **Better edit:** built-in sync, any camera layout, reaction shots, cross-talk handling,
   speaker-aware 9:16 reframing, VAD/transcript-based jump cuts and filler removal.
3. **Faster:** 1-hour 3-camera episode analysed in under 60 s after decoding, applied to
   the timeline in under 5 s, re-cut with a new preset in under 1 s.
4. **Wider:** Premiere, Resolve **Free and Studio**, Final Cut (FCPXML), plus the
   standalone app — one engine, one licence.
5. **Local-first:** no upload, works offline (principles P1–P4 of the main plan).

---

## 2. What we take from AutoPod, and what we fix

### 2.1 Ideas worth taking (reference behaviour)

| # | AutoPod behaviour | How we implement it |
|---|---|---|
| R1 | **Camera layout mapping:** each camera is tagged solo / two-shot / three-shot / wide and linked to the speakers it shows | `CameraLayout.covers` per clip ([5.1](#51-camera-layout)); the switch reward understands every layout |
| R2 | **Output methods:** plain cuts, native multicam, enable/disable on stacked tracks | `OutputMethod` in the EditPlan ([5.3](#53-editplan-the-host-neutral-edit)); every adapter supports all three |
| R3 | **"More wide shots" control** | `wide_frequency` 0–1 in `SwitchParams` ([7.3](#73-engine-changes-for-better-switching)) |
| R4 | **Saved presets** | User presets stored in the engine DB, exported/imported as JSON |
| R5 | **Social clip creator:** in/out → new sequence per aspect ratio, watermark, end page, one-click batch export | PL5 — but with our face-tracked reframe written as native Motion keyframes |
| R6 | **Jump cut editor** | PL5 — VAD + energy, later transcript fillers (main Phase 10) |
| R7 | **Up to 10 cameras / 10 mics** | Engine limit raised to 10 + tested |
| R8 | **Runs from a panel inside the NLE** (Window → Extensions) | Premiere UXP panel, Resolve Workflow Integration + Scripts-menu script |

### 2.2 Weaknesses we fix

| # | AutoPod weakness | Our answer | Phase |
|---|---|---|---|
| F1 | Separate mic per speaker required | **Single-mic mode**: speaker diarization and/or visual active-speaker detection | PL8 |
| F2 | No built-in sync | Our GCC-PHAT sync + drift correction (main Phase 1) runs first when clips aren't synced | PL2 |
| F3 | Generic auto-reframe for social | Speaker-aware face tracking (main Phase 8) → native keyframes | PL5 |
| F4 | dB-threshold jump cuts | Silero VAD + per-mic noise floor; filler words from transcript | PL5, PL8 |
| F5 | No Final Cut | FCPXML export + import path | PL7 |
| F6 | One machine per key, manual switching | Offline Ed25519 licence with self-serve seat move | PL9 |
| F7 | Every run starts over | Step cache (D42): new preset re-cuts from stored analysis in < 1 s | PL1 |
| F8 | Result lands straight on the timeline | Preview + versions inside the panel, then apply; re-apply replaces our own track only | PL5 |
| F9 | OS updates broke the Mac build (their macOS 27 notice) | QA matrix includes OS betas; engine is a separate signed binary ([11](#11-testing-strategy-for-plugins)) | PL10 |

---

## 3. Architecture

### 3.1 Big picture

```
┌──────────────── NLE hosts ────────────────┐
│ Premiere UXP panel   (React + Spectrum)    │
│ Resolve WI plugin    (Electron, Studio)    │──┐
│ Resolve script       (Python, Free+Studio) │  │  HTTP + SSE on 127.0.0.1
│ Final Cut            (FCPXML import)       │  │  token auth (D43)
│ Standalone app       (Electron, Phase 6)   │  │
└────────────────────────────────────────────┘  ▼
                         ┌───────────────────────────────────────┐
                         │ Multicam Engine service (headless)    │
                         │ FastAPI + SQLite + Huey (Phase 4)     │
                         │  ├─ /api/...        (app API)         │
                         │  └─ /api/plugin/v1  (plugin API)      │
                         │ engine: probe · sync · analyze ·      │
                         │         decide · reframe · render ·   │
                         │         export · editplan             │
                         │ bundled ffmpeg + ONNX models          │
                         └───────────────────────────────────────┘
```

**Rule A — the engine does all heavy work.** Plugins never decode media, run models or
compute cuts. They only: read what the user selected → send paths + settings → receive an
EditPlan → apply it to the host timeline.

**Rule B — one host-neutral output.** The engine produces an **EditPlan** (Section 5.3).
Each adapter turns the same EditPlan into host operations. Bugs in cutting logic are fixed
once, in Python, with tests.

**Rule C — always have an XML fallback.** Every EditPlan can also be written as FCPXML /
Premiere XML (xmeml) / EDL (main Phase 7 exporters). If a host API cannot do something,
the adapter imports the XML instead. The plugin never dead-ends.

### 3.2 Engine lifecycle (how a plugin finds and starts the engine)

1. The desktop installer installs the engine and registers a URL scheme `multicam://`.
2. When the engine starts it writes `engine.json` to the app data dir
   (`~/Library/Application Support/Multicam Studio/` or `%APPDATA%\Multicam Studio\`):
   `{ "port": 47811, "token": "<random>", "pid": 1234, "api": "1.0.0" }`.
3. The plugin reads `engine.json` (UXP: file system access to that folder is declared in
   the manifest; Resolve script: plain file read) and calls `GET /api/plugin/v1/handshake`.
4. If there is no engine, the panel shows **Start engine**, which opens `multicam://start`
   (the OS launches the engine in headless tray mode). Plugin polls the handshake for 20 s.
5. Engine with no UI and no active session for 30 min exits by itself (`--idle-exit`).

The Electron app (Phase 6) and the plugins share the same engine instance and database,
so a project started in Premiere can be opened in the app and the other way round.

### 3.3 Flow of one "Auto Edit" run

```
User selects clips/sequence in NLE ─► panel: Setup (roles, names, layout, preset)
   ─► POST /sessions  (paths, host fps/size, existing sync if any)
   ─► POST /sessions/{id}/run  ─► SSE progress: probe → sync → analyze → decide
   ─► GET /sessions/{id}/editplan?host=premiere  ─► preview in panel (mini timeline)
   ─► Apply ─► adapter builds tracks/cuts in ONE undo step ─► markers for low-confidence cuts
   ─► user edits in NLE ─► (optional) "Send corrections" ─► POST /feedback (PL8)
```

---

## 4. Repository changes

```
multistudio/
├─ engine/src/multicam_engine/
│  ├─ decide/switch.py          # CHANGE: cover-set rewards, wide_frequency, variety, reactions
│  ├─ decide/presets.py         # CHANGE: + PUNCHY preset, user presets, new params
│  ├─ editplan/                 # NEW: CutList + layout → host-neutral EditPlan
│  │  ├─ model.py
│  │  ├─ build.py
│  │  └─ social.py              # social clip plans (aspect, reframe keyframes, overlays)
│  ├─ export/                   # (Phase 7) fcpxml / xmeml / edl — consume EditPlan
│  ├─ analysis/diarize.py       # NEW (PL8): single-mic speaker turns
│  └─ analysis/asd.py           # NEW (PL8): visual active-speaker score
├─ apps/api/src/multicam_api/
│  ├─ routers/plugin.py         # NEW: /api/plugin/v1/*
│  ├─ discovery.py              # NEW: engine.json write/remove, idle exit
│  └─ schemas.py                # + plugin request/response models
├─ packages/
│  └─ plugin-core/              # NEW (TypeScript, host-agnostic)
│     ├─ src/client.ts          # typed Plugin API client (generated types)
│     ├─ src/session.ts         # state machine: idle→setup→running→review→applied
│     ├─ src/adapter.ts         # HostAdapter interface (Section 8.1)
│     ├─ src/ui/                # React components: SetupForm, Progress, PlanPreview
│     └─ test/fake-host.ts      # in-memory host for unit tests
├─ apps/plugins/
│  ├─ premiere-uxp/             # NEW: manifest.json, React panel, PremiereAdapter
│  ├─ resolve-wi/               # NEW: Electron Workflow Integration plugin (Studio)
│  ├─ resolve-script/           # NEW: Python script for Workspace → Scripts (Free + Studio)
│  └─ fcp/                      # NEW: docs + FCPXML settings (no code in PL7)
├─ packaging/plugins/           # NEW: .ccx build, Resolve installers, signing scripts
└─ docs/PLUGIN_PLAN.md          # this file
```

Shared TS types keep coming from `schemas/openapi.json` via `make schemas` (D44, D48).
`Makefile` and `.github/workflows/*` are edited on the Mac only (see progress notes).

---

## 5. Data model additions

All new models are pydantic `StrictModel`s, exported to JSON Schema and TypeScript like
the existing ones. Frames stay integers (X6).

### 5.1 Camera layout

```python
class ShotType(StrEnum):
    SOLO = "solo"          # one person
    TWO = "two"            # two people
    THREE = "three"
    FOUR = "four"
    WIDE = "wide"          # everyone
    BROLL = "broll"        # never auto-selected

class CameraLayout(StrictModel):
    clip_id: UUID
    shot: ShotType
    covers: list[UUID]     # speaker ids visible in this camera (empty for BROLL)
    priority: float = 1.0  # user bias, 0.5–1.5 ("I like this angle")

class Speaker(StrictModel):
    id: UUID
    name: str
    mic_clip_id: UUID | None      # None → single-mic mode (PL8)
    mic_channel: int | None = None  # one file with several mic channels
```

This replaces the implicit "one speaker camera per mic + optional wide" model. Old
projects migrate automatically: each `ClipRole.SPEAKER` clip → `SOLO` covering its own
speaker; `ClipRole.WIDE` → `WIDE` covering all. Schema version bump + Alembic migration.

### 5.2 Switch parameters (extended)

```python
@dataclass(frozen=True)
class SwitchParams:
    # existing
    min_shot_s: float; switch_delay_s: float; bridge_gap_s: float
    lead_s: float; crosstalk_to_wide_s: float; silence_to_wide_s: float
    # new
    max_shot_s: float = 0.0        # >0: shots longer than this start paying a cost → variety
    wide_frequency: float = 0.3    # 0 = only when needed, 1 = wide/group shots often
    group_reward: float = 0.7      # reward of a two/three-shot that contains the speaker
    reaction_shots: bool = False   # PL8: cut to a listener's reaction during long monologues
    min_reaction_s: float = 1.2
```

New built-in preset **PUNCHY** (reels / high-energy): `min_shot_s=1.0`,
`switch_delay_s=0.3`, `lead_s=0.08`, `max_shot_s=8`, `wide_frequency=0.2`.
User presets = named `SwitchParams` rows in the DB, exportable as `.mcpreset.json`.

### 5.3 EditPlan (the host-neutral edit)

```jsonc
{
  "plan_version": 1,
  "project_id": "uuid",
  "cutlist_version": 7,
  "sequence": { "fps": [30000, 1001], "width": 1920, "height": 1080,
                "name": "Ep42 — Auto Edit v7" },
  "method": "stacked_enable",          // cuts | stacked_enable | multicam
  "media": [                           // one per source clip
    { "clip_id": "uuid", "path": "/…/camA.mov", "host_ref": "pp:item:…",
      "track": 1, "record_start_frame": -73, // sync offset on the sequence (can be < 0: trim)
      "angle": 1, "label": "Host" }
  ],
  "video_events": [                    // contiguous, sorted, frames on the sequence timeline
    { "start": 0, "end": 184, "clip_id": "uuid", "shot": "solo",
      "reframe": { "keys": [ { "frame": 0, "cx": 0.52, "cy": 0.41, "scale": 1.3 } ] },
      "confidence": 0.93 }
  ],
  "audio": { "mode": "mix", "tracks": [ { "clip_id": "uuid", "gain_db": 0 } ] },
  "removals": [ { "start": 912, "end": 931, "kind": "filler" } ],   // approved only
  "markers":  [ { "frame": 4410, "color": "yellow", "note": "low-confidence cut" } ],
  "captions": null                     // PL8: word list for native caption tracks
}
```

* `host_ref` carries the NLE's own id (Premiere project item GUID, Resolve media pool
  item unique id) so adapters don't re-import media that is already in the project.
* `confidence` comes from the speaker margin at the cut; cuts below 0.6 get a marker so the
  editor checks those first.
* **Removals** are applied as ripple deletes on all tracks at the same frames (X11).

---

## 6. Plugin API v1 (engine ⇄ plugin contract)

Prefix `/api/plugin/v1`, same token auth (D43), JSON only, versioned separately from the
app API. Breaking changes → `/v2`; the engine serves v1 and v2 side by side for one year.

| Method | Path | Purpose |
|---|---|---|
| GET | `/handshake` | `{engine_version, api_version, capabilities[], models{vad,face,asr}, licence{status,plan}}` |
| POST | `/sessions` | Create/reuse a project from host input (below). Idempotent on `host_sequence_id` |
| GET | `/sessions/{id}` | Current state, clips, layout, last plan summary |
| PATCH | `/sessions/{id}/setup` | Speakers, layout, preset, method, social settings |
| POST | `/sessions/{id}/run` | `{"steps": "auto" \| ["decide"]}` → job id |
| GET | `/sessions/{id}/events` | SSE: `progress`, `step_done`, `error`, `plan_ready` |
| GET | `/sessions/{id}/editplan` | `?host=premiere\|resolve\|fcp&version=N` |
| GET | `/sessions/{id}/export` | `?format=fcpxml\|xmeml\|edl\|srt` → file path (fallback path, Rule C) |
| POST | `/sessions/{id}/social` | In/out + aspect list → social EditPlans |
| POST | `/sessions/{id}/feedback` | User's final timeline as an EditPlan → diff stored for "learn my style" (PL8) |
| GET | `/presets`, POST `/presets` | Built-in + user presets |

**`POST /sessions` body**

```jsonc
{
  "host": { "app": "premiere", "version": "26.1", "os": "mac" },
  "host_sequence_id": "…",               // null if user selected loose clips
  "sequence": { "fps": [25,1], "width": 1920, "height": 1080 },
  "already_synced": true,                // clips come from a synced sequence/multicam
  "clips": [
    { "path": "/…/camA.mov", "host_ref": "…", "track": 1,
      "record_start_frame": 0, "in_frame": 120, "out_frame": 90120,
      "audio_channels": 2 }
  ]
}
```

If `already_synced` is true the engine **skips sync** and uses the host positions (users
who already built a multicam sequence get results faster). Otherwise it runs sync and
returns the offsets inside the EditPlan.

Errors use `{code, message, hint}` with stable codes: `media_offline`, `unsupported_codec`,
`sync_low_confidence`, `no_speech`, `licence_required`, `engine_busy`.

---

## 7. Fast, correct camera switching

"Fast" means three different things. Each has a target and a technique.

### 7.1 Processing speed (time from click to plan)

| Step | Technique | Target (1 h, 3 cams, M1 / mid laptop) |
|---|---|---|
| Decode audio | ffmpeg → 16 kHz mono per mic, **all mics in parallel**, audio stream only (no video decode) | ≤ 25 s |
| Sync | GCC-PHAT on decimated audio, multi-window (Phase 1); skipped if `already_synced` | ≤ 5 s |
| VAD + energy | Silero ONNX batched per 30 s chunk, one thread per mic | ≤ 20 s |
| Decide | Viterbi on 0.1 s steps (existing), O(steps × cams × min_steps) | ≤ 1 s |
| Face track (only when reframe/social/ASD enabled) | YuNet on keyframes every 0.5 s, proxy resolution (Phase 8) | ≤ 60 s, optional |
| Re-cut with another preset | Step cache (D42) → only `decide` runs | < 1 s |

Every stage caches by input hash, so pressing Auto Edit a second time is instant.

### 7.2 Apply speed (plan → host timeline)

* **One transaction, one undo step.** Premiere: one `executeTransaction` with a compound
  action. Resolve: one `AppendToTimeline` call with the whole clip list.
* **Batch, don't loop UI calls.** Build all operations first, then apply them in one go.
* **Big edits use XML.** If `video_events > 1500` (or the host is slow), import the
  generated XML as a new sequence instead of issuing thousands of API calls. Measure both
  in PL5/PL6 and pick the default per host.
* Target: **≤ 5 s** to apply a 1-hour edit with ~600 cuts.

### 7.3 Engine changes for better switching

1. **Cover-set rewards (any layout, R1).** Replace "speaker i ↔ camera i + one wide" by a
   reward per *camera*:
   * camera covers the active speaker alone → `1.0 × priority`
   * camera is a group shot that contains the speaker → `group_reward × priority`
   * wide during sustained cross-talk → `1.0`; during long silence → `0.3` (existing)
   * camera does not show the speaker → `0`
   The Viterbi in `_best_path` already works on "rows = cameras"; only `frame_rewards`
   changes. Keep the existing tests green for the old layout (it is a special case).
2. **Variety (`max_shot_s`).** After `max_shot_s` in one shot, a small growing cost makes
   a cut to another camera that also shows the speaker (group or wide) worth it. Needs
   the shot-age state the Viterbi already tracks; cap `d` at `max_shot_s`.
3. **`wide_frequency`.** Scales group/wide rewards between 0.5× and 1.5× and lowers the
   cross-talk threshold. This is AutoPod's "more wide shots" slider.
4. **Faster reaction without jitter.** `lead_s` per preset (cut slightly *before* the
   first word), plus onset detection on the new speaker's mic at 10 ms resolution so the
   cut snaps to the true onset frame instead of the 0.1 s grid.
5. **Reaction shots (PL8).** During a monologue longer than ~15 s, if a listener camera
   shows a strong reaction (face motion / smile from the face track, laughter on audio),
   allow a `min_reaction_s` cut to that listener and back.
6. **Confidence per cut** (speaker margin at the cut) → markers for review.
7. **Frame snapping** stays in `shots_to_segments` (integer frames, X6).

---

## 8. Host adapters: how each NLE is driven

### 8.1 Shared interface (`packages/plugin-core/src/adapter.ts`)

```ts
export interface HostAdapter {
  readonly host: "premiere" | "resolve" | "fcp";
  capabilities(): Promise<HostCaps>;            // multicam? keyframes? enable/disable? captions?
  readSelection(): Promise<SessionInput>;       // clips or sequence the user selected
  applyPlan(plan: EditPlan, opts: ApplyOptions): Promise<ApplyResult>; // one undo step
  importXml(path: string): Promise<ApplyResult>; // Rule C fallback
  addMarkers(markers: Marker[]): Promise<void>;
  readTimeline(): Promise<EditPlan>;            // for feedback / re-apply
}
```

`plugin-core` owns the flow (setup → run → review → apply), all UI, and error handling.
An adapter is only host glue, so it stays small and testable with `fake-host.ts`.

### 8.2 Premiere (UXP) — primary host

* **Why UXP:** Premiere 25.6+ treats UXP as the extension platform for new work; Adobe
  stops accepting new CEP submissions for Premiere in Dec 2027 and disables CEP by default
  in Dec 2028. We build UXP only (min Premiere 25.6). No CEP build.
* **Manifest:** `manifestVersion 5`, panel entry point, `requiredPermissions`: network to
  `http://127.0.0.1` (engine), local file system read for `engine.json`, launch of the
  `multicam://` scheme. *Verify exact permission keys in the PL4 spike.*
* **Read selection:** active sequence → video tracks → track items → project item → media
  path; or selected project items in the bin.
* **Apply methods:**
  * `stacked_enable` (default, most robust): new sequence, one camera per video track,
    razor at every cut, disable the clips that are not live.
  * `cuts`: one video track, overwrite edits per event.
  * `multicam`: create multicam source sequence, nest, switch angles per event. *Spike:
    confirm the UXP DOM exposes multicam angle switching; if not → XML import.*
* **Reframe / social:** write Motion → Position/Scale keyframes from `reframe.keys`
  (piecewise-linear path from Phase 8), sequence settings per aspect ratio.
* **Captions (PL8):** native caption track from word timings.
* **Distribution:** `.ccx` package, installed via Creative Cloud (Adobe Marketplace listing
  in PL9); dev loading via UXP Developer Tool.

### 8.3 DaVinci Resolve — two paths

| | Script (Workspace → Scripts) | Workflow Integration plugin |
|---|---|---|
| Editions | **Free and Studio** (internal scripting) | Studio only |
| OS | Win / Mac / Linux | Win / Mac |
| UI | Resolve UIManager (Qt) or a local web page opened by the engine | Electron — reuses `plugin-core` React UI |
| Tech | Python 3, `DaVinciResolveScript` via the running app | Resolve JS API |

Why both: the Free edition does not allow external scripting (a program outside Resolve
driving it), but scripts started from Resolve's own Scripts menu work. The Free user base
is large and AutoPod-style tools often skip it.

* **Apply:** `MediaPool.AppendToTimeline([...clipInfo])` with `startFrame`, `endFrame`,
  `trackIndex`, `recordFrame` for `cuts` / `stacked`; `TimelineItem.SetClipEnabled` for
  `stacked_enable`; `MediaPool.ImportTimelineFromFile` for XML fallback.
* **Reframe:** the scripting API sets static Zoom/Pan; keyframes likely need FCPXML import
  (adjust-transform keyframes). *Spike in PL6.*
* **Multicam:** Resolve API support for building multicam clips is limited → default to
  `stacked_enable`, offer `multicam` only via XML.

### 8.4 Final Cut Pro — FCPXML

* PL7 ships FCPXML (1.10+) export: a compound/multicam clip with angles + angle switches
  per event, transform keyframes for reframe, markers. User: File → Import → XML.
* Optional later: a Workflow Extension (Mac App Store distribution, Swift). Not in scope
  until there is demand.

---

## 9. Phase-wise plan (PL0–PL10)

Estimates: one developer, full-time. Part-time ≈ double. Total ≈ **16–20 weeks**.

| Phase | Deliverable | Estimate | Depends on |
|---|---|---|---|
| PL0 | Close out main Phases 6–8, real footage, benchmark baseline | 1–1.5 wk | — |
| PL1 | Engine: layouts, better switching, presets, speed | 2 wk | PL0 |
| PL2 | EditPlan + exporters + headless engine + Plugin API v1 | 2 wk | PL1 |
| PL3 | `plugin-core` (client, flow, UI, fake host) | 1 wk | PL2 |
| PL4 | Premiere UXP MVP (XML-import apply) | 1.5 wk | PL3 |
| PL5 | Premiere native apply + social clips + jump cuts | 2.5 wk | PL4 |
| PL6 | Resolve script (Free) + WI plugin (Studio) | 2 wk | PL3 |
| PL7 | Final Cut via FCPXML | 0.5–1 wk | PL2 |
| PL8 | Differentiators: single-mic, reactions, fillers, captions, learn-my-style | 3–4 wk | PL5, main 9–10 |
| PL9 | Packaging, licensing, updates, marketplace | 1.5 wk | PL5, PL6 |
| PL10 | Beta + QA matrix + launch | 2 wk | PL9 |

---

### PL0 — Close out and measure the baseline

**Goal:** the engine is proven on real footage before anyone installs a plugin.

**Tasks**
- [ ] Commit Phase 8 on the Mac (fetch models, `make schemas`, `make check`, e2e), push;
      delete `.phase8-changes.tgz`; update `ci.yml` to fetch all models
- [ ] Push Phases 6–8 to GitHub (GitHub `main` is at Phase 5, `bf31eb6`)
- [ ] Record test footage per `docs/TEST_FOOTAGE.md`: 2-cam, 3-cam + wide, 4-cam, one noisy
      room, one single-mic recording, one Hinglish episode
- [ ] Run sync + switch benchmarks (D29): offset error, cut timing vs a human edit
- [ ] **AutoPod comparison set:** the same 3 episodes edited by (a) a human editor,
      (b) AutoPod trial, (c) our engine. Store the human edit as ground truth
      (`benchmark/ground_truth.py`)
- [ ] Record timings for Section 7.1 on the Mac and one Windows laptop

**Done when:** Phases 6–8 are on GitHub, benchmarks pass, and there is a written baseline
table: our switch accuracy and timings vs AutoPod on the same footage.

---

### PL1 — Engine: layouts, better switching, speed

**Goal:** the engine handles every AutoPod camera layout and cuts at least as well.

**Tasks**
- [ ] `CameraLayout`, `ShotType`, `Speaker` models; schema bump; Alembic migration of old
      projects (roles → layouts)
- [ ] `frame_rewards` → cover-set rewards (7.3 #1); old layouts produce identical cuts
      (regression test on all existing fixtures)
- [ ] `max_shot_s` variety cost, `wide_frequency`, `group_reward`
- [ ] Onset snapping (7.3 #4); per-cut confidence (7.3 #6)
- [ ] PUNCHY preset; user presets (DB table + API + JSON import/export)
- [ ] Raise limits to 10 cameras / 10 mics; multi-channel files (one file, N mic channels)
- [ ] Parallel audio decode + batched VAD; profile and hit Section 7.1 targets
- [ ] Benchmarks: switch accuracy per layout (solo+wide, two-shot+solos, 4 solos + wide)

**Done when:** all layouts in `TEST_FOOTAGE.md` produce edits that match or beat the
AutoPod comparison set on cut timing, and a 1-hour 3-cam episode analyses in ≤ 60 s.

---

### PL2 — EditPlan, exporters, headless engine, Plugin API v1

**Goal:** a plugin can start the engine, send clips, and get a plan it can apply.

**Tasks**
- [ ] `editplan/model.py`, `build.py`: CutList + layout + host sequence → EditPlan;
      `already_synced` path; host timeline offsets (negative record start = trim)
- [ ] Exporters consume EditPlan: FCPXML, xmeml, EDL (reuse Phase 7 code); validate FCPXML
      against Apple DTD in tests
- [ ] Headless engine mode: `multicam-engine serve --headless --idle-exit 30m`
- [ ] `discovery.py`: write/remove `engine.json` (port, token, pid, api version); single
      instance lock
- [ ] `multicam://start` URL scheme registered by the installer (Electron `setAsDefaultProtocolClient`)
- [ ] `routers/plugin.py`: all endpoints in Section 6, stable error codes
- [ ] OpenAPI + TS types regenerated (`make schemas`)
- [ ] `scripts/plugin_demo.py`: full flow against the API with demo media

**Done when:** `plugin_demo.py` goes handshake → session → run → editplan → FCPXML on a
clean machine, and the FCPXML opens correctly in Resolve and Final Cut.

---

### PL3 — `plugin-core`

**Goal:** all shared plugin logic and UI exists once, tested without any NLE.

**Tasks**
- [ ] Typed client + SSE with reconnect and polling fallback (same pattern as D50)
- [ ] Session state machine: `idle → connecting → setup → running → review → applying → applied | error`
- [ ] UI: Connect/Start engine, Setup (camera cards with shot type + who is in frame +
      speaker name + mic), preset picker with sliders (min shot, wide frequency, reaction
      speed), Progress, Plan preview (mini multi-lane timeline, confidence markers), Apply
- [ ] Setup auto-fill: guess shot type from face count (Phase 8 face track) and mic → speaker
      mapping from audio levels; user confirms
- [ ] `HostAdapter` interface + `fake-host.ts`; unit tests for the full flow
- [ ] UI works inside UXP constraints (Spectrum web components, limited CSS) and in
      Electron — build two small render targets from the same components

**Done when:** the full flow runs in Vitest against `fake-host.ts` and the real engine.

---

### PL4 — Premiere UXP MVP

**Goal:** editors can auto-edit from inside Premiere, end to end.

**Tasks**
- [ ] Spike (2 days): UXP permissions for localhost + file read + URL launch; Premiere UXP
      DOM coverage for sequences, track items, razor, enable/disable, multicam, keyframes,
      markers, XML import. Write results into `DECISIONS.md`
- [ ] Panel scaffold (`manifest.json`, React, Spectrum), loads `plugin-core`
- [ ] `PremiereAdapter.readSelection()` for (a) selected sequence, (b) selected bin items
- [ ] Apply via **XML import** (xmeml) into a new sequence, then move into a bin
      "Multicam Studio / Ep — v7"
- [ ] Markers for low-confidence cuts
- [ ] Clear errors: engine missing, media offline, unsupported codec

**Done when:** on Mac and Windows, Premiere 25.6+ → select 3 synced clips → Auto Edit →
a correct new sequence appears, audio in sync, in under 2 minutes for a 1-hour episode.

---

### PL5 — Premiere native apply, social clips, jump cuts

**Goal:** full AutoPod parity in Premiere, plus our better reframing.

**Tasks**
- [ ] Native apply for `stacked_enable` and `cuts` in one transaction / one undo step
- [ ] `multicam` method (native if the spike allows, else XML)
- [ ] Re-apply: replace only sequences/tracks we created; keep versions (v7, v8 …)
- [ ] Measure native vs XML apply time; choose the default (7.2)
- [ ] **Social clip creator:** in/out from the sequence → one sequence per aspect
      (16:9, 4:5, 9:16, 1:1) with face-tracked Motion keyframes, optional watermark
      image + end page clip, all in a "Social" bin; batch export via Media Encoder queue
- [ ] **Jump cuts:** VAD-based silence removal with padding (not dB); preview list;
      ripple delete across all tracks at identical frames with short audio crossfades
- [ ] Preview in panel before apply (plan preview from PL3)

**Done when:** every row in Section 2.1 works in Premiere, and our 9:16 clips keep the
speaker framed where Premiere's auto-reframe drifts (side-by-side on the comparison set).

---

### PL6 — DaVinci Resolve

**Goal:** the same results in Resolve Free and Studio.

**Tasks**
- [ ] Spike (2 days): `AppendToTimeline` with record frames and track index, `SetClipEnabled`,
      markers, FCPXML transform keyframe import, limits in Free
- [ ] `resolve-script`: Python script installed into the Scripts/Utility folder; small
      UIManager window (connect, pick preset, run, apply); reads current timeline clips
- [ ] `resolve-wi`: Electron WI plugin reusing `plugin-core` UI; `ResolveAdapter` via JS API
- [ ] Apply `stacked_enable` / `cuts` natively; reframe + multicam via FCPXML import
- [ ] Installers copy script + WI plugin to the right folders (Win/Mac; script also Linux)

**Done when:** Resolve 19/20 Free (script) and Studio (WI) both produce the same edit as
Premiere for the comparison set, audio in sync.

---

### PL7 — Final Cut Pro

**Goal:** Final Cut users get the edit with no plugin install.

**Tasks**
- [ ] FCPXML with multicam clip + angle switches, transforms, markers
- [ ] "Export for Final Cut" button in the standalone app and in all plugins
- [ ] Test on Final Cut 11.x: import, relink, sync, angle switching still editable

**Done when:** import in Final Cut gives an editable multicam edit identical to Premiere's.

---

### PL8 — Differentiators (beyond AutoPod)

**Goal:** features AutoPod does not have. Each ships behind a setting.

**Tasks**
- [ ] **Single-mic mode (F1).** Research spike first, with the licence gate from main plan
      Section 5 (model weights must allow commercial closed-source use):
      * audio speaker diarization (embedding + clustering on VAD segments), and/or
      * visual active-speaker detection from face tracks (mouth-region motion; a small
        ONNX model if a permissively licensed one exists)
      * fuse both into `SpeakerActivity`, so `decide` is unchanged
- [ ] **Reaction shots** (7.3 #5)
- [ ] **Filler words + transcript** (main Phases 9–10): Hindi/English/Hinglish; removals
      go into the EditPlan; captions as native caption tracks (Premiere) / subtitle track
      (Resolve) / FCPXML captions
- [ ] **Highlight finder:** score 30–90 s windows by speech energy, laughter, turn-taking,
      and transcript keywords → suggested social clips in the panel
- [ ] **Learn my style:** `POST /feedback` stores the editor's final timeline; compute
      per-user adjustments (average shot length, wide share, lead time) → "My style" preset
- [ ] Speaker-colored captions and lower-third names from `Speaker.name`

**Done when:** a single-mic 2-person episode gets a usable auto-edit, and at least one
beta user's "My style" preset reduces their manual corrections on a second episode.

---

### PL9 — Packaging, licensing, updates

**Goal:** a stranger can buy, install and update everything alone.

**Tasks**
- [ ] One installer per OS: engine + desktop app + optional plugins (checkboxes)
- [ ] Premiere `.ccx` signed package; Adobe Marketplace listing (or direct `.ccx` download)
- [ ] Resolve: installer steps copy script + WI plugin; uninstall removes them
- [ ] Code signing + notarization (main plan Section 6)
- [ ] Offline Ed25519 licence keys (main Phase 11): 1 key = 2 machines, self-serve
      deactivate from the app, 14-day grace offline
- [ ] Compatibility matrix in `handshake`: plugin refuses to run against an incompatible
      engine and says which to update
- [ ] Auto-update: engine via electron-updater; Premiere plugin via marketplace/`.ccx`;
      Resolve script via engine (engine rewrites the script file on update)
- [ ] Opt-in crash reports (local file export if the user prefers no network)

**Done when:** fresh Mac + Windows machines: download → install → licence → Auto Edit in
Premiere and Resolve works, and an update arrives by itself.

---

### PL10 — Beta, QA, launch

**Goal:** launch with confidence.

**Tasks**
- [ ] 10–20 podcast editors (Indian creators + 5 international), structured feedback form
- [ ] QA matrix (Section 11.3) run before every release
- [ ] Stress: 3-hour episode, 10 cams, 4K HEVC, 10-bit, VFR phone footage, offline media
- [ ] Docs: quick-start video per host, troubleshooting, layout guide
- [ ] Pricing decision (e.g. lower than $29/mo, or one-time + yearly updates) — record as a decision
- [ ] Launch page with the side-by-side comparison (our edit vs AutoPod vs human)

**Done when:** no open critical bugs, scorecard (Section 10) passes on all hosts.

---

## 10. Acceptance criteria: the "beat AutoPod" scorecard

Measured on the PL0 comparison set (same footage for all).

| # | Metric | AutoPod | Our target |
|---|---|---|---|
| S1 | Cut timing vs human edit (median distance of each cut to nearest human cut) | measure in PL0 | ≤ AutoPod and ≤ 0.25 s |
| S2 | Wrong-camera share (frames showing a non-speaker during clear single speech) | measure | ≤ 2 % |
| S3 | Rapid flicker (shots < min shot) | measure | 0 |
| S4 | Time to plan, 1 h / 3 cams, already synced | measure | ≤ 60 s |
| S5 | Time to apply to timeline | measure | ≤ 5 s |
| S6 | Re-cut with a new preset | full re-run | < 1 s |
| S7 | Works with unsynced clips | no | yes (sync ≤ 1 frame error) |
| S8 | Works with one mixed mic | no | yes (PL8) |
| S9 | 9:16 speaker stays in frame (% of frames face fully inside crop) | measure | ≥ 98 % |
| S10 | Hosts | Premiere, Resolve | Premiere, Resolve Free + Studio, Final Cut, standalone |
| S11 | Undo | measure | one undo step reverts the whole apply |

---

## 11. Testing strategy for plugins

### 11.1 Layers

| Layer | What | Where it runs |
|---|---|---|
| Engine unit | rewards, Viterbi, EditPlan build, exporters (golden files) | CI (pytest) |
| API contract | Plugin API endpoints, error codes, schema drift | CI |
| plugin-core | Flow + UI against `fake-host.ts` and a real engine | CI (Vitest) |
| Adapter unit | Adapter logic with mocked host DOM objects | CI |
| Export validity | FCPXML DTD validation; xmeml parse; EDL round trip | CI |
| Host manual | Scripted QA checklist in real Premiere / Resolve / FCP | Mac + Windows, before release |

CI cannot run Premiere or Resolve, so adapters stay thin and everything else is tested
without a host.

### 11.2 Golden plans

For each fixture in the footage library, store the expected EditPlan JSON. Any change in
cuts shows up as a diff in review (main plan regression rule 11.3).

### 11.3 QA matrix

| Host | Versions | OS |
|---|---|---|
| Premiere | 25.6, latest 26.x, current beta | macOS (current + beta), Windows 11 |
| Resolve Free | 19.x, 20.x | macOS, Windows, Linux (script only) |
| Resolve Studio | 20.x | macOS, Windows |
| Final Cut | 11.x | macOS |

---

## 12. Risks and open questions

| # | Risk / question | Mitigation | Decide in |
|---|---|---|---|
| K1 | Premiere UXP DOM may not cover multicam angle switching or all keyframe types | XML import fallback (Rule C); `stacked_enable` default | PL4 spike |
| K2 | UXP network/file permissions for `127.0.0.1` and app-data file | Spike first; fallback: user pastes a pairing code shown by the engine | PL4 spike |
| K3 | Resolve scripting cannot write keyframes | FCPXML import for reframe | PL6 spike |
| K4 | Resolve Free blocks external scripting | Scripts-menu script runs inside Resolve | PL6 |
| K5 | Single-mic models with a commercial-friendly licence may not exist | Licence gate; fall back to simple mouth-motion ASD built in-house | PL8 spike |
| K6 | Very long timelines slow in host APIs | XML import for large plans (7.2) | PL5 |
| K7 | Media paths differ between host and engine (network drives, relinked media) | Always use the host's resolved path; engine reports `media_offline` per clip | PL2 |
| K8 | Host fps/time base mismatch (29.97 drop-frame, 23.976) | Rational fps end-to-end (X6); golden tests per fps | PL2 |
| K9 | Adobe Marketplace review time | Direct `.ccx` download available from day one | PL9 |
| K10 | OS updates break the engine binary | OS beta in QA matrix; engine updates separately from plugins | PL10 |

---

## 13. Decisions to record (D68+)

Add these to `docs/DECISIONS.md` when each is confirmed.

| # | Decision | Why |
|---|---|---|
| D68 | Plugins are thin; the engine service does all processing (Rule A) | One engine, one set of tests, all hosts get fixes at once |
| D69 | Host-neutral `EditPlan` is the only thing plugins apply (Rule B) | Adapters stay small; XML exporters and plugins share one model |
| D70 | Every host keeps an XML import fallback (Rule C) | Never blocked by host API gaps |
| D71 | Premiere: UXP only, minimum 25.6, no CEP build | CEP is being retired; new work belongs in UXP |
| D72 | Resolve: Scripts-menu Python script (Free + Studio) and WI plugin (Studio) | Free users cannot use external scripting |
| D73 | Final Cut via FCPXML only until there is demand for an extension | Zero install, low cost |
| D74 | `CameraLayout` with cover sets replaces `ClipRole` for switching | Supports every AutoPod layout and more |
| D75 | Engine discovery via `engine.json` + `multicam://start` | Plugins can find and start the engine without the app window |
| D76 | Plugin API versioned separately (`/api/plugin/v1`) | Plugins update on a different schedule than the app |
| D77 | Default apply method `stacked_enable`, single undo step | Most robust across hosts, easy for editors to adjust |

---

## 14. Progress tracker

| Phase | Status | Commit | Notes |
|---|---|---|---|
| PL0 | partly done | Phase 8 commit, PL0 commit | Phase 8 committed; `scripts/bench_pipeline.py`; T1 baseline in `docs/BENCHMARKS.md`; sync-confidence fix (D79). Open: T1 labels, human/AutoPod comparison set, more recordings, Mac/Windows timings |
| PL1 | not started | | |
| PL2 | not started | | |
| PL3 | not started | | |
| PL4 | not started | | |
| PL5 | not started | | |
| PL6 | not started | | |
| PL7 | not started | | |
| PL8 | not started | | |
| PL9 | not started | | |
| PL10 | not started | | |

### Sources checked for this plan (29 Sep 2026)

- AutoPod features and FAQ: https://www.autopod.fm/ and https://www.autopod.fm/pricing
- Adobe CEP → UXP timeline: https://blog.developer.adobe.com/en/publish/2026/09/investing-in-the-future-of-creative-cloud-extensibility-uxp-comes-to-our-flagship-applications
- Premiere CEP superseded by UXP (25.6): https://github.com/Adobe-CEP/Samples/blob/master/PProPanel/ReadMe.md
- Resolve Workflow Integration plugins: https://resolvedevdoc.readthedocs.io/en/latest/UI_intro.html
- Resolve Free scripting limits: https://forum.blackmagicdesign.com/viewtopic.php?f=21&t=113252
