# Exporting to editing software (Phase 7)

Export → **Open in editing software** writes one of these next to your renders
(or into your chosen output folder). They point at your **original** camera
files, so keep them where they are (or relink in the editor).

| Button | File | Opens in | Contains |
|---|---|---|---|
| Final Cut / DaVinci Resolve | `.fcpxml` (FCPXML 1.9) | Final Cut Pro 10.5+, DaVinci Resolve 17+ | camera cuts (video) + every camera's audio, synced |
| Premiere Pro | `.xml` (Final Cut Pro 7 XML) | Premiere Pro, DaVinci Resolve | same as above |
| EDL (cuts only) | `.edl` (CMX3600) | any conform tool | camera cuts only, by reel name + timecode |

How it lines up
* Timeline starts at 00:00:00:00 at the project frame rate (drop-frame at 29.97 / 59.94).
* Each shot uses the same source frame as Multicam Studio's own render.
* Audio: one track per camera. If a camera's clock drifts (long recordings), its
  audio is split into a few pieces so it never drifts more than ¼ frame.
* Camera timecode: when the files have embedded timecode, clips use it.
* Shots where a camera was not recording stay empty (black), like in the render.

## Checking an export (do this once per format, on real footage)

**DaVinci Resolve (free)**
1. File → Import → Timeline… → choose the `.fcpxml` (or the `.xml`).
2. Leave "Automatically import source clips into media pool" on.
3. Play across a few cuts: lips and voice must match on every camera, and each
   cut must land where it does in Multicam Studio's render (compare with the
   exported `.mp4`).
4. Solo each audio track (A1 = first camera …): all must be in sync with the picture.

**Premiere Pro**
1. File → Import → choose the `.xml`. A new sequence and bin appear.
2. Same checks as above. If Premiere asks for media, point it at the original files.

**Final Cut Pro**
1. File → Import → XML… → choose the `.fcpxml`.
2. Same checks.

Report problems with the file and a screenshot; note the camera frame rates.
