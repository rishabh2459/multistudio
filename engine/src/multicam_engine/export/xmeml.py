"""Final Cut Pro 7 XML ("xmeml" v5) writer: imported by Adobe Premiere Pro and
DaVinci Resolve.

Timeline positions (start/end) are frames at the sequence rate; source in/out
are frames at each clip's own rate. Video track 1 holds the camera cuts; each
camera's audio is on its own stereo track.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from fractions import Fraction
from uuid import UUID

from multicam_engine.export._util import file_url, to_frames
from multicam_engine.export.timecode import frames_to_timecode, timecode_rate
from multicam_engine.export.timeline import Event, NleTimeline, Source


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


def to_xmeml(tl: NleTimeline) -> str:
    root = ET.Element("xmeml", version="5")
    seq = _sub(root, "sequence", id="sequence-1")
    _sub(seq, "name", tl.name)
    _sub(seq, "duration", tl.duration_frames)
    _rate(seq, tl.fps)
    _timecode(seq, tl.fps, 0)
    media = _sub(seq, "media")

    written: set[UUID] = set()
    counter = {"clip": 0}

    def file_element(parent: ET.Element, src: Source) -> None:
        file_id = f"file-{list(tl.sources).index(src.clip_id) + 1}"
        if src.clip_id in written:  # later references are empty
            _sub(parent, "file", id=file_id)
            return
        written.add(src.clip_id)
        f = _sub(parent, "file", id=file_id)
        _sub(f, "name", src.name)
        _sub(f, "pathurl", file_url(src.path, localhost=True))
        _rate(f, src.fps)
        _sub(f, "duration", to_frames(src.duration, src.fps))
        _timecode(f, src.fps, src.start_tc_frames)
        fm = _sub(f, "media")
        _video_characteristics(_sub(fm, "video"), src.fps, src.width, src.height)
        if src.has_audio:
            audio = _sub(fm, "audio")
            asc = _sub(audio, "samplecharacteristics")
            _sub(asc, "depth", 16)
            _sub(asc, "samplerate", src.sample_rate)
            _sub(audio, "channelcount", src.audio_channels)

    def clipitem(track: ET.Element, ev: Event, kind: str, trackindex: int) -> None:
        src = tl.sources[ev.clip_id]
        counter["clip"] += 1
        item = _sub(track, "clipitem", id=f"clipitem-{counter['clip']}")
        _sub(item, "name", src.label if kind == "video" else f"{src.label} (audio)")
        _sub(item, "enabled", "TRUE")
        _sub(item, "duration", to_frames(src.duration, src.fps))
        _rate(item, src.fps)
        _sub(item, "start", ev.start)
        _sub(item, "end", ev.end)
        source_in = to_frames(ev.source_in, src.fps)
        source_len = to_frames(Fraction(ev.frames) / tl.fps, src.fps)
        _sub(item, "in", source_in)
        _sub(item, "out", source_in + source_len)
        file_element(item, src)
        st = _sub(item, "sourcetrack")
        _sub(st, "mediatype", kind)
        _sub(st, "trackindex", trackindex)

    video = _sub(media, "video")
    vfmt = _sub(video, "format")
    _video_characteristics(vfmt, tl.fps, tl.width, tl.height)
    vtrack = _sub(video, "track")
    for ev in tl.video:
        clipitem(vtrack, ev, "video", 1)

    audio = _sub(media, "audio")
    _sub(audio, "numOutputChannels", 2)
    afmt = _sub(audio, "format")
    asc = _sub(afmt, "samplecharacteristics")
    _sub(asc, "depth", 16)
    _sub(asc, "samplerate", 48000)
    for events in tl.audio.values():
        atrack = _sub(audio, "track")
        for ev in events:
            clipitem(atrack, ev, "audio", 1)

    ET.indent(root)
    body = ET.tostring(root, encoding="unicode")
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE xmeml>\n{body}\n'
