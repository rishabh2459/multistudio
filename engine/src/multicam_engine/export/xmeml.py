"""Final Cut Pro 7 XML ("xmeml" v5) writer: imported by Adobe Premiere Pro and
DaVinci Resolve.

Timeline positions (start/end) are frames at the sequence rate; source in/out
are frames at each clip's own rate. Video track 1 holds the camera cuts (or one
track per camera when stacked); overlay tracks (watermarks) sit above; each
camera's audio is on its own track.

Motion: an event with transform keys gets a "Basic Motion" filter (Premiere maps
it to Motion). ``scale`` is percent; ``center`` is the clip centre's offset from
the sequence centre as a fraction of the sequence width / height. Keyframe
``when`` values count frames of the clip's media (the same clock as ``in``/``out``).

Several sequences (e.g. an edit and its multicam source) are written into one
file inside a ``project``; files are defined once and referenced by id after.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from fractions import Fraction
from uuid import UUID

from multicam_engine.export._util import file_url, to_frames
from multicam_engine.export.timecode import frames_to_timecode, timecode_rate
from multicam_engine.export.timeline import Event, NleTimeline, Source, TransformKey


def _sub(parent: ET.Element, tag: str, text: object = None, **attrs: str) -> ET.Element:
    el = ET.SubElement(parent, tag, attrs)
    if text is not None:
        el.text = str(text)
    return el


def _rate(parent: ET.Element, fps: Fraction) -> None:
    rate = _sub(parent, "rate")
    _sub(rate, "timebase", round(fps))
    _sub(rate, "ntsc", "TRUE" if fps.denominator == 1001 else "FALSE")


def _timecode(parent: ET.Element, fps: Fraction, frames: int) -> None:
    tc_rate = timecode_rate(fps)
    tc = _sub(parent, "timecode")
    _rate(tc, fps)
    _sub(tc, "string", frames_to_timecode(frames, tc_rate))
    _sub(tc, "frame", frames)
    _sub(tc, "displayformat", "DF" if tc_rate.drop else "NDF")


def _video_characteristics(parent: ET.Element, fps: Fraction, width: int, height: int) -> None:
    sc = _sub(parent, "samplecharacteristics")
    _rate(sc, fps)
    _sub(sc, "width", width)
    _sub(sc, "height", height)
    _sub(sc, "anamorphic", "FALSE")
    _sub(sc, "pixelaspectratio", "square")
    _sub(sc, "fielddominance", "none")


def _num(value: float) -> str:
    text = f"{value:.6f}".rstrip("0").rstrip(".")
    return "0" if text in ("", "-0") else text


class _Writer:
    """Shared state across the sequences of one file (file and clip ids)."""

    def __init__(self, sources: dict[UUID, Source]) -> None:
        self.sources = sources
        self.order = list(sources)
        self.written: set[UUID] = set()
        self.clips = 0

    # ------------------------------------------------------------- files
    def file_element(self, parent: ET.Element, src: Source) -> None:
        file_id = f"file-{self.order.index(src.clip_id) + 1}"
        if src.clip_id in self.written:  # later references are empty
            _sub(parent, "file", id=file_id)
            return
        self.written.add(src.clip_id)
        f = _sub(parent, "file", id=file_id)
        _sub(f, "name", src.name)
        _sub(f, "pathurl", file_url(src.path, localhost=True))
        _rate(f, src.fps)
        _sub(f, "duration", to_frames(src.duration, src.fps))
        _timecode(f, src.fps, src.start_tc_frames)
        fm = _sub(f, "media")
        if src.has_video:
            _video_characteristics(_sub(fm, "video"), src.fps, src.width, src.height)
        if src.has_audio:
            audio = _sub(fm, "audio")
            asc = _sub(audio, "samplecharacteristics")
            _sub(asc, "depth", 16)
            _sub(asc, "samplerate", src.sample_rate)
            _sub(audio, "channelcount", src.audio_channels)

    # ------------------------------------------------------------- filters
    def motion(
        self, item: ET.Element, tl: NleTimeline, ev: Event, src: Source, source_in: int
    ) -> None:
        keys = ev.transform
        if not keys:
            return
        effect = _sub(_sub(item, "filter"), "effect")
        _sub(effect, "name", "Basic Motion")
        _sub(effect, "effectid", "basic")
        _sub(effect, "effectcategory", "motion")
        _sub(effect, "effecttype", "motion")
        _sub(effect, "mediatype", "video")

        def when(key: TransformKey) -> int:
            # media frames, same clock as <in>: in + (key - start) at the clip's rate
            return source_in + to_frames(Fraction(key.frame - ev.start) / tl.fps, src.fps)

        def center(parent: ET.Element, key: TransformKey) -> None:
            value = _sub(parent, "value")
            _sub(value, "horiz", _num((key.x - tl.width / 2) / tl.width))
            _sub(value, "vert", _num((key.y - tl.height / 2) / tl.height))

        scale = _sub(effect, "parameter", authoringApp="PremierePro")
        _sub(scale, "parameterid", "scale")
        _sub(scale, "name", "Scale")
        _sub(scale, "valuemin", 0)
        _sub(scale, "valuemax", 1000)
        _sub(scale, "value", _num(keys[0].scale))
        pos = _sub(effect, "parameter", authoringApp="PremierePro")
        _sub(pos, "parameterid", "center")
        _sub(pos, "name", "Center")
        center(pos, keys[0])
        if len(keys) > 1:
            for key in keys:
                kf = _sub(scale, "keyframe")
                _sub(kf, "when", when(key))
                _sub(kf, "value", _num(key.scale))
            for key in keys:
                kf = _sub(pos, "keyframe")
                _sub(kf, "when", when(key))
                center(kf, key)

    @staticmethod
    def opacity(item: ET.Element, ev: Event) -> None:
        if ev.opacity is None:
            return
        effect = _sub(_sub(item, "filter"), "effect")
        _sub(effect, "name", "Opacity")
        _sub(effect, "effectid", "opacity")
        _sub(effect, "effectcategory", "motion")
        _sub(effect, "effecttype", "motion")
        _sub(effect, "mediatype", "video")
        param = _sub(effect, "parameter", authoringApp="PremierePro")
        _sub(param, "parameterid", "opacity")
        _sub(param, "name", "Opacity")
        _sub(param, "valuemin", 0)
        _sub(param, "valuemax", 100)
        _sub(param, "value", _num(ev.opacity * 100))

    # ------------------------------------------------------------- clips
    def clipitem(
        self,
        tl: NleTimeline,
        track: ET.Element,
        ev: Event,
        kind: str,
        prefix: str,
        enabled: bool = True,
    ) -> None:
        src = tl.sources[ev.clip_id]
        self.clips += 1
        item = _sub(track, "clipitem", id=f"{prefix}clipitem-{self.clips}")
        _sub(item, "name", src.label if kind == "video" else f"{src.label} (audio)")
        _sub(item, "enabled", "TRUE" if enabled else "FALSE")
        _sub(item, "duration", to_frames(src.duration, src.fps))
        _rate(item, src.fps)
        _sub(item, "start", ev.start)
        _sub(item, "end", ev.end)
        source_in = to_frames(ev.source_in, src.fps)
        source_len = to_frames(Fraction(ev.frames) / tl.fps, src.fps)
        _sub(item, "in", source_in)
        _sub(item, "out", source_in + source_len)
        self.file_element(item, src)
        st = _sub(item, "sourcetrack")
        _sub(st, "mediatype", kind)
        _sub(st, "trackindex", 1)
        if kind == "video":
            self.motion(item, tl, ev, src, source_in)
            self.opacity(item, ev)

    # ------------------------------------------------------------- sequence
    def sequence(self, parent: ET.Element, tl: NleTimeline, number: int) -> None:
        prefix = "" if number == 1 else f"s{number}-"
        seq = _sub(parent, "sequence", id=f"sequence-{number}")
        _sub(seq, "name", tl.name)
        _sub(seq, "duration", tl.duration_frames)
        _rate(seq, tl.fps)
        _timecode(seq, tl.fps, 0)
        for marker in tl.markers:
            m = _sub(seq, "marker")
            _sub(m, "name", marker.note[:60])
            _sub(m, "comment", marker.note)
            _sub(m, "in", marker.frame)
            _sub(m, "out", -1)
        media = _sub(seq, "media")

        video = _sub(media, "video")
        vfmt = _sub(video, "format")
        _video_characteristics(vfmt, tl.fps, tl.width, tl.height)
        if tl.stacked:  # one track per camera, only the live pieces enabled
            for pieces in tl.stacked:
                vtrack = _sub(video, "track")
                for ev, enabled in pieces:
                    self.clipitem(tl, vtrack, ev, "video", prefix, enabled)
        else:
            vtrack = _sub(video, "track")
            for ev in tl.video:
                self.clipitem(tl, vtrack, ev, "video", prefix)
        for overlay in tl.overlays:
            vtrack = _sub(video, "track")
            for ev in overlay:
                self.clipitem(tl, vtrack, ev, "video", prefix)

        audio = _sub(media, "audio")
        _sub(audio, "numOutputChannels", 2)
        afmt = _sub(audio, "format")
        asc = _sub(afmt, "samplecharacteristics")
        _sub(asc, "depth", 16)
        _sub(asc, "samplerate", 48000)
        for events in tl.audio.values():
            atrack = _sub(audio, "track")
            for ev in events:
                self.clipitem(tl, atrack, ev, "audio", prefix)


def to_xmeml(tl: NleTimeline, *, extra: list[NleTimeline] | None = None) -> str:
    """One sequence, or ``tl`` plus ``extra`` sequences in one project (same media)."""
    root = ET.Element("xmeml", version="5")
    timelines = [tl, *(extra or [])]
    sources: dict[UUID, Source] = {}
    for t in timelines:
        for cid, src in t.sources.items():
            sources.setdefault(cid, src)
    writer = _Writer(sources)
    if len(timelines) == 1:
        writer.sequence(root, tl, 1)
    else:
        project = _sub(root, "project")
        _sub(project, "name", tl.name)
        children = _sub(project, "children")
        for i, t in enumerate(timelines, start=1):
            writer.sequence(children, t, i)
    ET.indent(root)
    body = ET.tostring(root, encoding="unicode")
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE xmeml>\n{body}\n'
