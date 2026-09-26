"""CMX3600 EDL writer: the camera cuts as a video-only edit decision list.

An EDL has one frame rate and no file paths: sources are matched by reel name
and source timecode (the camera's embedded start timecode + offset), so the
``* FROM CLIP NAME`` comment carries the file name for tools that match on it.
Audio is not included (use FCPXML or Premiere XML for a timeline with sound).
"""

from __future__ import annotations

from multicam_engine.export._util import reel_names, to_frames
from multicam_engine.export.timecode import frames_to_timecode, timecode_rate
from multicam_engine.export.timeline import NleTimeline


def to_edl(tl: NleTimeline) -> str:
    rate = timecode_rate(tl.fps)
    reels = dict(zip(tl.sources, reel_names([s.name for s in tl.sources.values()]), strict=True))
    title = "".join(ch for ch in tl.name if ch.isprintable())[:70] or "Multicam Studio"
    lines = [f"TITLE: {title}", f"FCM: {'DROP FRAME' if rate.drop else 'NON-DROP FRAME'}", ""]
    for number, ev in enumerate(tl.video, start=1):
        src = tl.sources[ev.clip_id]
        # Source timecode in timeline-rate frames (EDLs have a single rate).
        src_in = to_frames(src.start_seconds + ev.source_in, tl.fps)
        src_out = src_in + ev.frames
        times = " ".join(frames_to_timecode(f, rate) for f in (src_in, src_out, ev.start, ev.end))
        lines.append(f"{number:03d}  {reels[ev.clip_id]:<8} V     C        {times}")
        lines.append(f"* FROM CLIP NAME: {src.name}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
