# Benchmarks

Real-footage numbers for the plugin plan's scorecard (`PLUGIN_PLAN.md` Section 10).
Re-run with:

```bash
uv run python scripts/bench_pipeline.py samples/T1/host.mov:speaker samples/T1/guest.mov:speaker samples/T1/wide.mov:wide --json bench.json
# or on extracted tracks (no video decode):
uv run python scripts/bench_pipeline.py host.wav:speaker guest.wav:speaker wide.wav:wide --fps 30
```

## T1 — 3 iPhones (host, guest, wide), 69 min, HEVC 1080p30 VFR, camera mics only

Measured 2026-09-29 on the cloud workspace (2 vCPU, x86_64), from the 16 kHz WAVs in
`samples/T1/_audio` (so "decode" is WAV reading; decoding AAC from the `.mov` files on
the Mac adds roughly 5–15 s per camera and runs in parallel since PL1).

| Step | PL0 baseline | After PL1 | Target (7.1) |
|---|---|---|---|
| Decode (all mics, parallel) | 3.4 s | 3.0 s | ≤ 25 s |
| Sync (3 clips) | 12.2 s | 10.7 s | ≤ 5 s (skipped when `already_synced`) |
| Analyze (Silero VAD + energy) | 9.5 s | 7.6 s | ≤ 20 s |
| Decide, per preset | 0.54–0.61 s | 0.83–0.89 s (incl. PUNCHY with variety) | ≤ 1 s |
| **Plan total** | **≈ 26 s** | **≈ 22 s** | **≤ 60 s** |

Cuts per preset (PL1): calm 179 · balanced 321 · dynamic 621 · punchy 1038
(mean shot 23.0 / 12.9 / 6.7 / 4.0 s).

### Sync

| Clip | Offset | Drift | Windows on the line | Confidence before → after D79 |
|---|---|---|---|---|
| guest | +29.667 s | +5.7 ppm | 21 / 28 | 0.33 → 0.77 |
| wide | +16.681 s | −5.6 ppm | 25 / 28 | 0.36 → 0.88 |

The offsets lie on straight lines within ~1 ms over the whole hour (the rejected
windows are 2–3 ms off: room reflections). Before D79 both clips raised a "low sync
confidence" warning although the alignment is right; the PSR of single windows is only
6–12 in this room.

### Who is speaking — finding

The host and guest camera mics hear both people almost equally: the level difference
(host mic − guest mic) during speech is **unimodal around −1 dB** (std ≈ 8 dB, no
second mode), and 29 % of the time is labelled cross-talk. Local time-delay (GCC-PHAT
on 0.5 s windows) shows several clusters but none that maps cleanly to one person.

Consequences:

* Analysis now warns about this (D82) instead of silently cutting to the wide.
* AutoPod requires a separate mic per speaker for the same reason. Our answer for
  camera-mic-only recordings is PL8 (visual active-speaker detection from the face
  tracks we already compute, fused with audio).
* **Accuracy (S1/S2) cannot be scored yet**: T1 has no labels. Next: label T1 in
  Audacity (`make gt-audio REC=samples/T1`, `docs/TEST_FOOTAGE.md`) and record a
  second episode with lav / podcast mics.

## Still to measure (PL0 checklist)

- [ ] T1 labels → S1 (cut timing vs human) and S2 (wrong-camera share)
- [ ] Same episodes edited by a human and by the AutoPod trial (comparison set)
- [ ] Timings from the `.mov` files on the Mac (M-series) and one Windows laptop
- [ ] 2-cam, 4-cam, noisy room, single-mic and Hinglish recordings (`TEST_FOOTAGE.md`)
