"""Premiere "multicam" as far as Premiere allows it (xmeml).

Premiere has no API to build a multicam sequence or switch angles (UXP or
ExtendScript, confirmed by Adobe), and its FCP7-XML import drops ``multiclip``
elements. So the multicam method for Premiere writes ONE xmeml with two sequences:

1. ``<name>`` — the edit: every camera on its own track, the live pieces enabled
   (the stacked layout: same cuts, one undo step, fully editable);
2. ``<name> - Multicam Source`` — every camera as ONE synced clip on its own track
   plus every mic: drop it into a sequence and use Multi-Camera > Enable to switch
   angles by hand in Premiere's multicam monitor.

Final Cut and Resolve get a real multicam clip instead (``fcpxml_multicam``).
"""

from __future__ import annotations

from multicam_engine.editplan.build import piece_seconds, plan_to_timeline
from multicam_engine.editplan.model import EditPlan, TrackPiece
from multicam_engine.export.timeline import Event, NleTimeline
from multicam_engine.export.xmeml import to_xmeml

SOURCE_SUFFIX = " - Multicam Source"


def _merged(pieces: list[TrackPiece]) -> list[Event]:
    """Contiguous pieces of one camera joined into single clips."""
    out: list[Event] = []
    for p in pieces:
        if out and out[-1].end == p.start:
            last = out[-1]
            out[-1] = Event(last.clip_id, last.start, p.end, last.source_in)
        else:
            out.append(Event(p.clip_id, p.start, p.end, piece_seconds(p)))
    return out


def multicam_source_timeline(plan: EditPlan) -> NleTimeline:
    """Every camera as one synced clip on its own track, plus every mic."""
    tl = plan_to_timeline(plan, stacked=False)
    tl.name = plan.sequence.name + SOURCE_SUFFIX
    tl.markers = []
    tl.overlays = []
    tl.stacked = [
        [(ev, True) for ev in _merged(track.pieces)]
        for track in sorted(plan.video_tracks, key=lambda t: t.index)
        if track.pieces
    ]
    return tl


def to_xmeml_multicam(plan: EditPlan) -> str:
    """The stacked edit and its multicam source sequence in one xmeml."""
    edit = plan_to_timeline(plan, stacked=True)
    return to_xmeml(edit, extra=[multicam_source_timeline(plan)])
