# Parity TODO — AutoPod + PodFast in one Adobe plugin

> **Goal:** one Premiere Pro panel (Multicam Studio) that does everything
> [AutoPod](https://www.autopod.fm/) does (multicam editor, social clips, jump cuts) **and**
> everything [PodFast](https://aescripts.com/podfast/) does (speech enhance, transcript,
> vocal remover / splitter, timeline round-trip) — but **local and offline** (no Adobe
> Podcast / VocalRemover.org upload, principles P1–P4).
>
> **Checked:** 4 Oct 2026 · **Owner:** Rishabh · Companion to `docs/PLUGIN_PLAN.md` (PL0–PL10).
> Phases here are **P0–P8** and map onto PL phases (column "PL").
>
> **How to keep this file honest:** every feature has an ID (AP-*, PF-*, OUR-*). The script
> `scripts/parity_check.py` checks the code for each ID and writes `docs/PARITY_REPORT.md`.
> When you finish a task: tick it here, run `python3 scripts/parity_check.py --write
> --save-baseline`, commit both. In CI run `--check-baseline` so nothing silently goes back.

---

## 0. Where we stand (static check, 4 Oct 2026 — after the P2/P3/P4 code)

| Source | DONE | HOST (code done, test in NLE) | PARTIAL | MISSING |
|---|---|---|---|---|
| AutoPod (21 features) | 12 | 9 | 0 | 0 |
| PodFast (14 features) | 0 | 0 | 3 | 11 |
| Our extras (7) | 3 | 1 | 2 | 1 |

**Short version:**
- **AutoPod → every feature is now in the code.** Multicam editor (all methods; stacked in
  ONE undo step), social clips (4 aspects, speaker framing, watermark, end page, bin, Media
  Encoder queue), jump cuts (dB cutoff like AutoPod + speech mode, padding, review list,
  ripple on every track). 9 of them still need one test inside Premiere (P0 checklist).
- **Multicam in Premiere** = stacked edit + a ready "Multicam Source" sequence. Adobe has no
  API to build multicam sequences or switch angles (confirmed by Adobe) and its XML import
  drops multiclips, so this is the most a plugin can do; Final Cut / Resolve get a real one.
- **PodFast → still to build (P5/P6).** Bins and In/Out reading exist; enhance, loudness,
  stems, round-trip, transcript are next.

PodFast is an **audio** tool, AutoPod is an **edit** tool. Combined, the panel gets 4 tabs:
**Auto Edit · Jump Cuts · Social · Audio & Transcript**.

---

## 1. How to run and test for free

You don't need to buy anything to test most of it.

| What | Free option | What it proves |
|---|---|---|
| Engine + plan logic | **No NLE needed.** `uv run multicam-api --headless` + `scripts/plugin_demo.py` + `scripts/parity_check.py --live` | Sync, switching, EditPlan, XML exports, presets |
| Plugin UI + flow | **No NLE needed.** `pnpm -r test` (plugin-core `FakeHost`, Premiere mock DOM, Resolve fake) | Panel flow, apply logic, error paths |
| Resolve plugin | **DaVinci Resolve (free edition)** — our `resolve-script` is made for Free | Real apply on a real timeline, XML import |
| Exported XML | Import our FCPXML / xmeml into **Resolve Free** (File → Import → Timeline) | Exports are correct without Premiere |
| Premiere panel | **Premiere Pro 7-day free trial** + **UXP Developer Tool** (free in Creative Cloud) | The real target. Do the spike checklist in one sitting, then cancel |
| Final Cut | **Final Cut Pro free trial** (Apple, Mac only) | FCPXML multicam import |
| PodFast-type audio | `ffmpeg` (already bundled) — `arnndn`, `afftdn`, `loudnorm` filters | Enhance/loudness work before any UI |

### 1.1 Step by step (Mac)

```bash
cd ~/Documents/Projects/multicam-studio

# 0) code-only parity check (no install needed, any python3)
python3 scripts/parity_check.py            # matrix in the terminal
python3 scripts/parity_check.py --write    # -> docs/PARITY_REPORT.md

# 1) engine tests
uv sync && make check                      # ruff, mypy, pytest, schemas
pnpm install && pnpm -r test               # plugin-core, premiere-uxp, resolve-wi

# 2) start the engine and run a real auto-edit (demo media or your T1 footage)
uv run python scripts/make_demo_media.py   # -> samples/demo/
uv run multicam-api --headless &           # writes engine.json
python3 scripts/parity_check.py --live \
   --media samples/demo/cam1.mp4 samples/demo/cam2.mp4 --wide samples/demo/wide.mp4
# real footage:
python3 scripts/parity_check.py --live \
   --media samples/T1/host.mov samples/T1/guest.mov --wide samples/T1/wide.mov --write

# 3) Resolve Free: install our script, open a timeline, Workspace → Scripts → Multicam Studio
(cd apps/plugins/resolve-script && python3 -m multicam_resolve.install)

# 4) Premiere trial (only when 1–3 pass, so the 7 days are not wasted)
pnpm --filter @multicam/premiere-uxp build
#   UXP Developer Tool → Add Plugin → apps/plugins/premiere-uxp/manifest.json → Load
#   Premiere → Window → UXP Plugins → Multicam Studio → tick the spike checklist (P0)
```

> Tip: run steps 1–3 for a few days first. Start the Premiere trial only when you can do the
> whole spike checklist + P2 manual tests in one week.

---

## 2. Feature map (what each tool does → where it goes in our plugin)

### 2.1 AutoPod

| ID | AutoPod feature | Our implementation | Status | Phase |
|---|---|---|---|---|
| AP-M1 | 10 cameras + 10 mics | `MAX_CAMERAS/MAX_SPEAKERS = 10` | DONE | — |
| AP-M2 | Solo / two / three / four / wide shots | `ShotType` | DONE | — |
| AP-M3 | Any common camera configuration | cover-set rewards (D74/D78) | DONE | — |
| AP-M4 | "More wide shots" | `wide_frequency` + panel slider | DONE | — |
| AP-M5 | Presets | built-ins + user presets, JSON import/export | DONE | — |
| AP-M6 | Output: standard cuts | `cuts` plan + native beta apply | HOST | P0, P2 |
| AP-M7 | Output: enable/disable | stacked by xmeml import, clips arrive disabled: **1 undo step** (D93) | HOST | P2 ✓ |
| AP-M8 | Output: multi-cam | stacked edit + "Multicam Source" sequence in one xmeml (D94; Adobe has no multicam API) | HOST | P2 ✓ |
| AP-M9 | Premiere panel | UXP panel | HOST | P0 |
| AP-M10 | DaVinci Resolve | script (Free) + WI (Studio) | HOST | P0 |
| AP-S1 | In/out → social sequence | `POST /social` + panel reads In/Out marks | HOST | P3 ✓ |
| AP-S2 | 1920×1080 / 1080×1350 / 1080×1920 | + 1:1 1080×1080 | DONE | P3 ✓ |
| AP-S3 | Auto-reframe | face-tracked framing per aspect → Motion keys (xmeml Basic Motion, D95) | HOST | P3 ✓ |
| AP-S4 | Watermark | corner, size, opacity, margin; own track | DONE | P3 ✓ |
| AP-S5 | End page | still or video, fitted, with its audio | DONE | P3 ✓ |
| AP-S6 | Folder + batch export | `Multicam Studio/Social` bin + `EncoderManager` AME queue | HOST | P3 ✓ |
| AP-J1 | Jump cuts on silence | `engine/jumpcut` + job `jumpcut` | DONE | P4 ✓ |
| AP-J2 | dB cutoff per mic | global + per-mic cutoff; VAD mode for noisy rooms (D97) | DONE | P4 ✓ |
| AP-J3 | Padding / min silence | `pad_s`, `min_silence_s`, `min_removal_s` | DONE | P4 ✓ |
| AP-J4 | Ripple delete in Premiere | engine ripples every track → "… - Jump Cuts" sequence (D96) | HOST | P4 ✓ |
| AP-J5 | Preview before apply | review list (approve / reject each, all) | DONE | P4 ✓ |

### 2.2 PodFast (v1.0.52, Premiere 26.2+)

PodFast sends audio to **Adobe Podcast** (enhance, transcript) and **VocalRemover.org**
(remover, splitter) and brings the result back. We do the same jobs **locally** in the engine.

| ID | PodFast feature | Our local replacement | Status | Phase |
|---|---|---|---|---|
| PF-1 | Enhance Speech (denoise, clean dialogue) | ffmpeg `arnndn` (RNNoise model) / `afftdn` now; DeepFilterNet ONNX later (licence gate) | MISSING | P5 |
| PF-2 | Set levels | `loudnorm` 2-pass to −16 LUFS (podcast) / −14 (YouTube), true-peak −1 dB | MISSING | P5 |
| PF-3 | Mono / stereo export presets | `channels: mono|stereo` in the audio job | MISSING | P5 |
| PF-4 | Vocal Remover (voice vs music) | Demucs (MIT) / HTDemucs ONNX, 2-stem | MISSING | P5 |
| PF-5 | Splitter (vocals, drums, bass, other) | same model, 4-stem | MISSING | P5 |
| PF-6 | Auto timeline replacement (free track under original / replace) | adapter: import → place on first free audio track at same time, or replace | MISSING | P5 |
| PF-7 | Custom label for processed clips | name suffix + Premiere color label | MISSING | P5 |
| PF-8 | Auto rename + own bin | bins done (`Multicam Studio`, `/Social`); renaming processed audio in P5 | PARTIAL | P5 |
| PF-9 | Work-area handling | In/Out reading exists (social); use it for audio tools | PARTIAL | P5 |
| PF-10 | Configurable keyboard shortcuts | UXP manifest `commands` + settings | MISSING | P5 |
| PF-11 | Transcribe | whisper.cpp / faster-whisper, Hindi/English/Hinglish | MISSING | P6 |
| PF-12 | SRT subtitles aligned to clip | `export?format=srt|vtt` | MISSING | P6 |
| PF-13 | Transcript into Premiere | caption track from SRT (import) | MISSING | P6 |
| PF-14 | (bonus) filler words | `Removal(kind=filler)` from word timings | PARTIAL | P6 |

---

## 3. Phases

Rules for every phase:
- Engine does the work, plugin stays thin (Rule A). New work = new **EditPlan / AudioJob**
  fields + engine code + tests, then adapter glue.
- Each phase ends with: tests green (`make check`, `pnpm -r test`), `parity_check.py
  --write --save-baseline`, a row in `docs/DECISIONS.md` for any choice, commit.
- Model licences must allow closed-source commercial use (main plan §5) — check **before** coding.

### P0 — Prove what is already built (≈ 1 week, PL0/PL4/PL6/PL7) — *do first*

- [ ] Apply pending Mac work (`apply-plugin-work.sh`), commit the 4 uncommitted files
      (`resolve-script/plan.py`, `ui.py`, `plugin-core/setup.ts`, `test_resolve_script.py`), push
- [ ] Add `scripts/parity_check.py --check-baseline` to CI (edit `ci.yml` on the Mac)
- [ ] `parity_check.py --live` on demo media and on T1 → all multicam rows PASS; save report
- [ ] Resolve Free: run resolve-script spike (endFrame inclusive?, `SetClipEnabled`, UI timer) → DECISIONS
- [ ] Import our FCPXML + xmeml in Resolve Free → cuts match the EditPlan
- [ ] Premiere trial: PL4 spike checklist (`apps/plugins/premiere-uxp/README.md`) on Mac → DECISIONS
- [ ] Final Cut trial: import `fcpxml_multicam` → angles switch, still editable
- [ ] Premiere: the new checklist items (stacked one undo, multicam source, Basic Motion
      units, social sizes/watermark/AME, jump-cut sync) in `apps/plugins/premiere-uxp/README.md`
- [ ] `make schemas` on the Mac (new API models), commit `schemas/` + `packages/types`
- [ ] Record results in `docs/BENCHMARKS.md` (S4 plan time, S5 apply time, S6 re-cut)

**Done when:** AP-M6, AP-M9, AP-M10, OUR-4 move from HOST to DONE.

### P1 — Multicam editor polish (≈ 3 days)

Already DONE in code; only keep it working.
- [ ] Golden EditPlans for T1 (and T2 when recorded) in `tests/golden/` → any switching change shows a diff
- [ ] Panel: show the 10-camera limit and a clear error past it
- [ ] Preset export/import buttons in the Premiere panel (API exists)

### P2 — Output methods in Premiere = AutoPod parity (≈ 1 week, PL5)

- [x] `stacked_enable` in **one** undo step — via xmeml import (clips arrive disabled);
      the bin is made at Connect so the apply itself is one step (D93) — AP-M7
- [x] `multicam`: Adobe has no API (UXP/ExtendScript/C++) and XML import drops multiclips →
      one xmeml with the stacked edit + "Multicam Source" sequence, panel explains (D94) — AP-M8
- [x] Reframe/punch-ins reach Premiere as Motion keyframes in the xmeml (D95)
- [ ] Re-apply = new version sequence ("Ep — v8"), never touches the user's own sequences
- [ ] Measure native vs XML apply on 600 cuts; pick default per method (target ≤ 5 s)
- [ ] Turn native `cuts` on by default once the spike passes (remove the localStorage switch)

**Done when:** AP-M6/7/8 DONE and one undo removes the whole apply (S11).

### P3 — Social Clip Creator (≈ 1.5 weeks, PL5)

Engine (`engine/editplan/social.py`, `ripple.py`, `transform.py`):
- [x] `build_social_plans(plan, in_frame, out_frame, aspects, options)` → one EditPlan per
      aspect: 16:9 = 1920×1080, 4:5 = 1080×1350, 9:16 = 1080×1920, 1:1 = 1080×1080
- [x] Framing per aspect from the face-tracked reframes (9:16 vertical, 16:9 horizontal,
      4:5/1:1 follow the vertical path at the widest crop) → Motion keys per shot
- [x] Watermark (corner, size, opacity, margin) on its own track; end page (still or video,
      fitted, with audio) appended; optional jump cuts inside the clip
- [x] `POST /social` (501 removed) → plans + one xmeml per aspect + suggested render path
- [x] Tests: sizes, framing, watermark maths, end page, ripple inside the clip, XML output
- [ ] S9 check on T1: face fully inside the 9:16 crop ≥ 98 % of frames

Premiere adapter + panel:
- [x] Reads the sequence In/Out → Social section: aspect checkboxes, watermark + end page
      pickers, corner, end-page length, "cut the approved pauses"
- [x] All clips imported in ONE call into bin `Multicam Studio/Social`
- [x] Batch export: `EncoderManager.exportSequence(QUEUE_TO_AME)` per clip (+ preset), start queue
- [ ] Confirm in Premiere (spike checklist): sizes, keyframes, watermark, AME queue
- [ ] Side-by-side with Premiere's auto-reframe on T1

**Done when:** AP-S1…S6 DONE; side-by-side with Premiere auto-reframe on T1 is saved.

### P4 — Jump Cut Editor (≈ 1 week, PL5)

Engine (`engine/jumpcut/`):
- [x] `silent_frames` (db: every mic below the cutoff, per-mic overrides, 50 ms smoothing;
      vad: speaker labels) → `find_silences` (min pause, padding, min cut) → `removals_for`
      (rounded inwards: no speech frame is ever cut)
- [x] A silence counts only when **all** mics are quiet
- [x] The analysis now stores per-mic loudness (`energy_db`); old analyses are re-measured once
- [x] Job `jumpcut` → new cutlist version; `POST /jumpcuts`, `GET/PATCH /removals`,
      `editplan?ripple=true`, `export?ripple=true`
- [x] Ripple in the engine on every track at the same frames (`apply_removals`): sources
      move exactly, markers inside cuts drop, sync kept
- [x] Tests: frames, padding, min pause, multi-mic rule, merge with fillers, ripple maths

Premiere adapter + panel:
- [x] Jump cuts section: mode, dB cutoff, shortest pause, padding, "Find pauses"; list with
      a checkbox per pause, approve/reject all, total time saved
- [x] Apply: one xmeml import of the rippled edit as "<name> - Jump Cuts" (D96)
- [ ] Short audio crossfade at each cut (option)
- [ ] Works on any normal sequence (today: on the auto-edit session's clips)
- [ ] Confirm in Premiere: sync after every cut (markers at claps)

**Done when:** AP-J1…J5 DONE; audio stays in sync after ripple (check with markers at claps).

### P5 — Audio tools = PodFast parity, local (≈ 2 weeks)

Engine (`engine/audiofx/`, new) — one job type `AudioJob {clip, ops[], channels, out}`:
- [ ] `enhance`: ffmpeg `highpass=80, afftdn` + `arnndn` (bundle an RNNoise `.rnnn` model,
      BSD) with strength 0–100 → later DeepFilterNet ONNX after licence check
- [ ] `loudness`: 2-pass `loudnorm` (I=−16, TP=−1, LRA=11) presets Podcast / YouTube / custom
- [ ] `channels`: mono / stereo output (PF-3)
- [ ] `separate`: Demucs/HTDemucs ONNX, 2-stem (remover) and 4-stem (splitter); run on CPU in
      chunks, cache by input hash; show time estimate (it is slow)
- [ ] Endpoint `POST /sessions/{id}/audio` + SSE progress; output WAV 48 kHz 24-bit next to project
- [ ] Tests: SNR goes up on noisy synth, LUFS within ±0.5, stems sum ≈ original

Premiere adapter + panel ("Audio" tab):
- [ ] Select clip(s) or use sequence in/out (PF-9) → choose Enhance / Level / Remover / Splitter
- [ ] Round-trip (PF-6): import result, rename `<name> [Enhanced]`, bin `Multicam Studio/Audio`
      (PF-8), place on the first free audio track under the original **or** replace it (setting)
- [ ] Mute the original when placed below (setting); color label (PF-7)
- [ ] Shortcuts (PF-10): manifest `commands` for Enhance / Transcribe / Auto Edit
- [ ] Settings page: label text, behaviour (replace / below / bin only), mono/stereo default

**Done when:** PF-1…PF-10 DONE, all offline (pull the network cable test).

### P6 — Transcript, captions, fillers (≈ 2 weeks, main Phases 9–10 / PL8)

- [ ] `engine/transcribe/`: whisper.cpp (MIT) or faster-whisper; models small/medium; word
      timestamps; languages hi / en / auto (Hinglish) — test on T7
- [ ] Per-speaker transcript (we know who speaks from the mics → better than PodFast)
- [ ] Exports: SRT, VTT, plain text, JSON words (`export?format=srt|vtt|txt`)
- [ ] Premiere: import SRT as caption track on the sequence (PF-13); Resolve: subtitle track
- [ ] Filler removal (PF-14): um/uh/hmm + Hindi fillers (matlab, basically, yaani…) →
      `Removal(kind=FILLER)` → reuses the P4 review list and ripple apply
- [ ] Speaker-coloured captions / lower-third names from `Speaker.name`

**Done when:** PF-11…PF-14 DONE; caption timing within 0.2 s on T1.

### P7 — Beyond both tools (≈ 3 weeks, PL8)

- [ ] Single-mic mode (OUR-5): diarization + visual ASD → `SpeakerActivity`
- [ ] Reaction shots during long monologues
- [ ] Highlight finder → suggested social clips (feeds P3)
- [ ] Learn my style (OUR-6): use stored feedback → "My style" preset

### P8 — Ship and maintain (≈ 2 weeks, PL9–PL10)

- [ ] Signed `.ccx`, installer, Ed25519 licence (OUR-7)
- [ ] QA matrix before each release: `parity_check.py --live` on T1/T2 + Premiere manual list
- [ ] Watch competitors monthly: re-read autopod.fm and aescripts.com/podfast, add new
      features as new IDs here **and** in `FEATURES` in `parity_check.py`

---

## 4. Maintenance routine

| When | Do |
|---|---|
| Every PR | CI runs `python3 scripts/parity_check.py --check-baseline` (fails if any ID goes backwards) |
| Finishing a task | tick here → `--write --save-baseline` → commit `PARITY_REPORT.md` + `parity_baseline.json` |
| Every release | `--live` on demo + T1 media, Premiere/Resolve manual checklist, attach report |
| Monthly | competitor check (section P8) |

Adding a feature: add a row in section 2, a task in its phase, and a `Feature(...)` entry in
`scripts/parity_check.py` with the code evidence that proves it (file, function, setting).

## 5. Sources (checked 4 Oct 2026)

- AutoPod features: https://www.autopod.fm/
- PodFast product page + version history (v1.0.52, 8 Sep 2026): https://aescripts.com/podfast/
- Premiere Pro trial (7 days): https://www.adobe.com/products/premiere/free-trial-download.html
- Final Cut Pro trial: https://www.apple.com/final-cut-pro/trial/
