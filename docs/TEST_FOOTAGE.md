# Test Footage & Ground Truth

Precision is measured, not guessed. Every accuracy claim in this project is
checked against real recordings with hand-made **ground truth**.

## 1. What to record

| ID | Setup | Length | What it tests |
|----|-------|--------|---------------|
| T1 | 2 cams, 2 speakers, quiet room | ~5 min | Baseline |
| T2 | 3 cams (2 speakers + 1 wide) | ~10 min | Wide-shot logic |
| T3 | iPhone + Mac webcam (phone = VFR) | ~5 min | Variable frame rate |
| T4 | 2 cams, fan/AC running, some street noise | ~5 min | VAD robustness |
| T5 | 2 cams, lots of interruptions and talking over each other | ~5 min | Hysteresis, mic bleed |
| T6 | 2+ different devices | **60+ min** | Clock drift |
| T7 | Hindi + Hinglish conversation | ~10 min | Captions, fillers (later phases) |
| T8 | Low light | ~5 min | Face detection fallback (later phases) |

Start with **T1, T3, T5 and T6** — they are needed for Phases 1–2. The rest can come later.

## 2. Recording rules

1. **Clap at the start AND at the end.** One sharp hand clap, clearly visible and
   audible to every camera. The end clap is what lets us measure clock drift.
2. Each person sits in front of "their" camera; each camera records its own audio.
   Phone + laptop is enough — don't use a shared external recorder for these tests.
3. Start all cameras, wait ~2 s, clap. At the end: clap, wait ~2 s, stop cameras.
   Start the cameras at slightly different times on purpose (sync must handle it).
4. Don't edit or re-encode the files. Copy the originals as they come off the device.
5. Name files simply: `cam1.mp4`, `cam2.mov`, `wide.mp4` (no spaces).

## 3. Write `meta.json`

```json
{
  "recording_id": "T1",
  "description": "2 cams, quiet room, iPhone 15 + MacBook webcam",
  "reference_file": "cam1.mp4",
  "clips": [
    { "file": "cam1.mp4", "role": "speaker", "speaker_label": "Host" },
    { "file": "cam2.mov", "role": "speaker", "speaker_label": "Guest" }
  ]
}
```

`role` is `speaker`, `wide` or `broll`. A wide camera has no `speaker_label`.

## 4. Label in Audacity (free)

1. Extract WAVs: `make gt-audio REC=samples/T1` → creates `samples/T1/_audio/*.wav`.
2. Open Audacity → **File → Import → Audio** → select all WAVs. Each becomes a track
   starting at 0 s, so positions in a track equal positions in that file.
3. Add labels with **Edit → Labels → Add Label at Selection** (⌘B):

   | Label text | Type | Where |
   |------------|------|-------|
   | `clap_start@cam1.mp4` | point | on the start clap's sharp onset, in cam1's track |
   | `clap_end@cam1.mp4` | point | on the end clap's onset, in cam1's track |
   | *(same for every clip)* | | |
   | `Host` / `Guest` | region | stretches where that person speaks (reference track) |
   | `annotated_range` | region | the window you fully labeled with speech regions |

   Tips: zoom in hard on each clap (⌘1) and place the point on the first sharp
   rise of the waveform — this gives ~1 ms accuracy. For long recordings (T6)
   you don't need to label all speech: label a representative 5–10 minute
   window and mark it with `annotated_range`.
4. Export: **File → Export Other → Export Labels…** (menu name may vary slightly by
   Audacity version) → save as `samples/T1/labels.txt`.

## 5. Build and check

```bash
make gt-build REC=samples/T1   # writes samples/T1/ground_truth.json + prints offsets/drift
make gt-check                  # validates every recording under samples/
```

## 6. Accuracy targets

| Metric | Target | Phase |
|--------|--------|-------|
| Sync offset error (start of recording) | < 1 frame (≈ 33 ms at 30 fps), aim < 5 ms | 1 |
| Sync error at end of 60-min recording (after drift correction) | < 1 frame | 1 |
| Speaker accuracy (speech time on correct camera, inside `annotated_range`) | ≥ 95% | 2 |
| Shots shorter than preset minimum | 0 | 2 |

Sign convention for offsets (same everywhere in the code): **positive offset =
that clip started recording earlier than the reference clip.**
