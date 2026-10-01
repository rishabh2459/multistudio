# Multicam Studio for DaVinci Resolve — Scripts menu (Free + Studio)

Resolve Free blocks external scripting, but scripts started from Resolve's own
**Workspace → Scripts** menu work in Free and Studio (D72). This folder is that
script: Python 3.6+, standard library only.

| File | What |
|---|---|
| `Multicam Studio.py` | launcher Resolve lists under *Workspace → Scripts → Edit* |
| `multicam_resolve/client.py` | Plugin API v1 client, `engine.json` discovery, `multicam://start` |
| `multicam_resolve/adapter.py` | read the open timeline, build the edit (`AppendToTimeline`), FCPXML import, markers |
| `multicam_resolve/flow.py` | connect → session → run → plan → apply (no UI) |
| `multicam_resolve/ui.py` | the small window (Fusion UIManager) |
| `multicam_resolve/install.py` | copy launcher + package into place / remove |

## Install (until the installer does it, PL9)

```bash
cd apps/plugins/resolve-script && python3 -m multicam_resolve.install
```

The launcher goes to Resolve's `Fusion/Scripts/Edit` folder; the package to
`<Multicam Studio data>/resolve-plugin/`, so updating the engine can update it.
Restart Resolve, open your timeline, then *Workspace → Scripts → Edit → Multicam Studio*.

## Spike (PL6) — check in Resolve 19 and 20, Free and Studio

- [ ] `AppendToTimeline` `endFrame`: last frame (`END_INCLUSIVE = True`) or one past?
- [ ] `recordFrame` absolute (timeline start 01:00:00:00 included)
- [ ] `TimelineItem.SetClipEnabled(False)` exists (stacked method)
- [ ] `ImportTimelineFromFile(fcpxml)` keeps markers and transforms
- [ ] UIManager `ui.Timer` + `disp.On.Tick.Timeout` fire while the worker thread runs
- [ ] `GetLeftOffset()` is in timeline frames for same-rate clips

Tests: `uv run pytest tests/plugins` (fake Resolve + a real headless engine).
