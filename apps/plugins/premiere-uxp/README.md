# Multicam Studio for Premiere Pro (UXP)

Panel for Premiere Pro 25.6+ (UXP only, no CEP: D71). It reads the open sequence,
sends the clips to the local engine, shows the plan, and builds the edit as a new
sequence (PLUGIN_PLAN PL4).

## Try it (development)

```bash
pnpm install
pnpm --filter @multicam/premiere-uxp build      # -> dist/index.js
uv run multicam-api --headless                 # or just open the desktop app
```

1. Install **UXP Developer Tool** (Creative Cloud → All apps).
2. *Add Plugin* → pick `apps/plugins/premiere-uxp/manifest.json` → *Load*.
3. Premiere → *Window → UXP Plugins → Multicam Studio*.
4. Open a sequence with one camera per video track (synced or just dropped at
   frame 0; separate mic files on audio tracks), press **Connect**, check the
   roles, **Auto Edit**, **Apply to timeline**.

`pnpm --filter @multicam/premiere-uxp package` writes an unsigned `.ccx` to
`release/` (signed Creative Cloud package: PL9).

## How it applies

Everything the panel imports lands in the bin **Multicam Studio** (made once, at
Connect, so an apply is a single undo step).

| Method / tool | Path | Undo |
|---|---|---|
| any | engine writes xmeml → `project.importFiles` → new sequence, markers included | 1 step |
| `stacked_enable` | always xmeml: clips arrive already enabled/disabled (D93) | 1 step |
| `multicam` | xmeml with the stacked edit **+ "<name> - Multicam Source"** (every camera as one synced clip). Premiere has no multicam API (Adobe): nest the source and use *Multi-Camera > Enable* to switch by hand (D94) | 1 step |
| `cuts` (native, beta) | per event: clip in/out + `createOverwriteItemAction`, one transaction | 1 step |
| reframe / punch-ins | Motion keyframes in the xmeml ("Basic Motion", D95) | — |
| Jump cuts | engine ripples the approved pauses out of every track → xmeml → new sequence "<name> - Jump Cuts" (D96) | 1 step |
| Social clips | one xmeml per aspect, all imported in one call into `Multicam Studio/Social`; optional `EncoderManager.exportSequence(QUEUE_TO_AME)` per clip | 1 step |

Native `cuts` is off until the spike below passes; turn it on for testing in the
panel's console: `localStorage.setItem('multicam.nativeApply', '1')`.

## Test for free

1. Everything without Premiere: `pnpm -r test` (mock DOM) and
   `python3 scripts/parity_check.py --live --media …` against a running engine.
2. Premiere Pro's 7-day trial + the free UXP Developer Tool for the checklist below
   (do 1. first so the trial days go to the checklist only).

## PL4 spike checklist (Mac + Windows, Premiere 25.6 and latest 26.x)

- [ ] `fetch('http://127.0.0.1:47811/...')` works with the manifest's network entry
      (if only `localhost` works: switch `endpointOf` to `localhost`, K2)
- [ ] engine on a port other than 47811 is reachable (`"domains": "all"`)
- [ ] `localFileSystem: fullAccess` + `getEntryWithUrl('file:/…/engine.json')` reads the file
- [ ] `shell.openExternal('multicam://start')` launches the engine (launchProcess scheme)
- [ ] `importFiles([…xml])` creates the sequence; markers come through
- [ ] native `cuts`: `createSetInOutPointsAction` + `createOverwriteItemAction(item, t, v, -1)`
      places video only (is `-1` "no audio track"?)
- [ ] `createSetDisabledAction` on the new items
- [ ] React 19 renders in the UXP panel; `sp-picker` `change` and `sp-slider` events fire
- [ ] Undo after apply removes the whole sequence
- [ ] Stacked apply: one import, disabled clips on the camera tracks, ONE undo removes it
- [ ] Multicam apply: both sequences arrive; nesting "… - Multicam Source" + *Multi-Camera >
      Enable* shows every angle in sync
- [ ] Reframe: a punched-in shot keeps the speaker framed — check Motion > Scale/Position and
      that the keyframes sit at the right times (xmeml `center` = offset / frame size, `when`
      in media frames from `in`; if Premiere reads them differently, fix `export/xmeml.py`)
- [ ] Social: mark In/Out on the auto-edit sequence → 9:16 / 4:5 / 1:1 / 16:9 sequences in
      `Multicam Studio/Social` at 1080×1920 / 1080×1350 / 1080×1080 / 1920×1080, framed
- [ ] Social: watermark sits in the chosen corner at the chosen opacity; end page is appended
- [ ] Social: "Queue renders" puts every clip in Adobe Media Encoder (with and without a preset)
- [ ] Jump cuts: find pauses (dB and speech mode), untick one, apply → "… - Jump Cuts"
      sequence, picture and every mic still in sync after each cut
- [ ] File pickers (watermark, end page) open and return the path

Write the results into `docs/DECISIONS.md`.
