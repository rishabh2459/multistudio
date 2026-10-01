# Multicam Studio for Final Cut Pro (FCPXML, no install)

Final Cut gets the edit as an FCPXML file (D73): an editable **multicam clip** with
one angle per camera (and per separate mic), and the auto edit as angle switches.

## Export

- **Standalone app:** *Export → Final Cut Pro (multicam clip)* (`fcpxml_multicam`).
- **Plugins / API:** `GET /api/plugin/v1/sessions/{id}/export?format=fcpxml&method=multicam`
  (or `format=fcpxml_multicam`).

## Import in Final Cut Pro 11

*File → Import → XML…* → pick the `.fcpxml`. Final Cut creates an event
"Multicam Studio" with the multicam clip and a project with the edit. Every cut
is an angle switch: open the Angle Viewer to change any of them, or *Open in Angle
Editor* to adjust sync. Low-confidence cuts carry a marker.

## What the file contains

| Element | Meaning |
|---|---|
| `media/multicam` | timeline = the edit's frames, `tcStart 0`, DF/NDF from the rate |
| `mc-angle` | one per camera / sound-only mic: `[gap] + asset-clip` at its sync position |
| `spine/mc-clip` | one per shot: video from the live angle, audio from every audio angle (mix) |
| `spine/gap` | frames no camera recorded |
| `mc-clip/marker` | "check this cut" notes |

Limits: clock drift is not modelled inside angles (Final Cut has no per-angle
speed); the plan warns about drifting sources. Reframing (keyframes) is not in the
multicam variant yet.

## Test on a Mac (PL7 "done when")

- [ ] Import in Final Cut 11.x: media relinks, angles in sync, angle switches editable
- [ ] Same edit as the Premiere import of the same session
- [ ] DaVinci Resolve also imports it (`ImportTimelineFromFile`)
