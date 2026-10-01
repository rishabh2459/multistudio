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

| Method | Default path | Undo |
|---|---|---|
| any | engine writes xmeml → `project.importFiles` → new sequence, markers included | 1 step |
| `cuts` (native, beta) | per event: clip in/out + `createOverwriteItemAction`, one transaction | 1 step |
| `stacked_enable` (native, beta) | place every camera piece, then `createSetDisabledAction` | 2 steps |

Native apply is off until the spike below passes; turn it on for testing in the
panel's console: `localStorage.setItem('multicam.nativeApply', '1')`.

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

Write the results into `docs/DECISIONS.md`.
