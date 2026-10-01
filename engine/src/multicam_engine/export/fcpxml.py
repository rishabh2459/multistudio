"""FCPXML 1.9 writer (Final Cut Pro 10.5+, DaVinci Resolve 17+).

Layout: one gap spans the whole timeline in the primary storyline; the camera
cuts are connected clips on lane 1 (video only) and each camera's audio is a
connected track on lanes -1, -2, ... (audio only). Timeline positions are exact
multiples of the frame duration; source starts are on the source's frame grid
(video) or sample grid (audio).
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from fractions import Fraction
from uuid import UUID

from multicam_engine.export._util import file_url, round_to, to_frames
from multicam_engine.export.timeline import NleTimeline, Source

FCPXML_VERSION = "1.9"


def rational(value: Fraction) -> str:
    value = Fraction(value)
    if value.denominator == 1:
        return f"{value.numerator}s"
    return f"{value.numerator}/{value.denominator}s"


def frame_time(frames: int, fps: Fraction) -> str:
    """Timeline time written the way Final Cut does: frames x frame duration,
    e.g. ``300300/30000s`` at 29.97 fps (never reduced)."""
    return f"{frames * fps.denominator}/{fps.numerator}s"


def _format_name(fps: Fraction, height: int) -> str:
    rates = {
        Fraction(24000, 1001): "2398",
        Fraction(24): "24",
        Fraction(25): "25",
        Fraction(30000, 1001): "2997",
        Fraction(30): "30",
        Fraction(50): "50",
        Fraction(60000, 1001): "5994",
        Fraction(60): "60",
    }
    rate = rates.get(fps)
    return f"FFVideoFormat{height}p{rate}" if rate else "FFVideoFormatRateUndefined"


def to_fcpxml(tl: NleTimeline) -> str:
    root = ET.Element("fcpxml", version=FCPXML_VERSION)
    resources = ET.SubElement(root, "resources")
    formats: dict[tuple[Fraction, int, int], str] = {}

    def format_id(fps: Fraction, width: int, height: int) -> str:
        key = (fps, width, height)
        if key not in formats:
            formats[key] = f"r{len(formats) + 1}"
            ET.SubElement(
                resources,
                "format",
                id=formats[key],
                name=_format_name(fps, height),
                frameDuration=rational(1 / fps),
                width=str(width),
                height=str(height),
            )
        return formats[key]

    seq_format = format_id(tl.fps, tl.width, tl.height)
    assets: dict[UUID, str] = {}
    for i, src in enumerate(tl.sources.values(), start=1):
        assets[src.clip_id] = f"a{i}"
        attrs = {
            "id": f"a{i}",
            "name": src.name,
            "start": frame_time(src.start_tc_frames if src.has_timecode else 0, src.fps),
            "duration": rational(round_to(src.duration, 1 / src.fps)),
        }
        if src.has_video:
            attrs.update(
                hasVideo="1",
                format=format_id(src.fps, src.width, src.height),
                videoSources="1",
            )
        if src.has_audio:
            attrs.update(
                hasAudio="1",
                audioSources="1",
                audioChannels=str(src.audio_channels),
                audioRate=str(src.sample_rate),
            )
        asset = ET.SubElement(resources, "asset", attrs)
        ET.SubElement(asset, "media-rep", kind="original-media", src=file_url(src.path))

    library = ET.SubElement(root, "library")
    event = ET.SubElement(library, "event", name="Multicam Studio")
    project = ET.SubElement(event, "project", name=tl.name)
    duration = frame_time(tl.duration_frames, tl.fps)
    drop = tl.fps in (Fraction(30000, 1001), Fraction(60000, 1001))
    sequence = ET.SubElement(
        project,
        "sequence",
        format=seq_format,
        duration=duration,
        tcStart="0s",
        tcFormat="DF" if drop else "NDF",
        audioLayout="stereo",
        audioRate="48k",
    )
    spine = ET.SubElement(sequence, "spine")
    gap = ET.SubElement(spine, "gap", name="Gap", offset="0s", start="0s", duration=duration)

    def video_start(src: Source, source_in: Fraction) -> str:
        tc = src.start_tc_frames if src.has_timecode else 0
        return frame_time(tc + to_frames(source_in, src.fps), src.fps)

    def audio_start(src: Source, source_in: Fraction) -> str:
        return rational(src.start_seconds + round_to(source_in, Fraction(1, src.sample_rate)))

    # Cut on lane 1, or (stacked) one lane per camera with the non-live pieces disabled.
    layers = tl.stacked or [[(ev, True) for ev in tl.video]]
    for lane, pieces in enumerate(layers, start=1):
        for ev, enabled in pieces:
            src = tl.sources[ev.clip_id]
            clip = ET.SubElement(
                gap,
                "asset-clip",
                ref=assets[ev.clip_id],
                lane=str(lane),
                name=src.label,
                offset=frame_time(ev.start, tl.fps),
                duration=frame_time(ev.frames, tl.fps),
                start=video_start(src, ev.source_in),
                srcEnable="video",
            )
            if not enabled:
                clip.set("enabled", "0")
    for marker in tl.markers:
        ET.SubElement(
            gap,
            "marker",
            start=frame_time(marker.frame, tl.fps),
            duration=frame_time(1, tl.fps),
            value=marker.note,
        )
    for lane, (clip_id, events) in enumerate(tl.audio.items(), start=1):
        src = tl.sources[clip_id]
        for ev in events:
            ET.SubElement(
                gap,
                "asset-clip",
                ref=assets[clip_id],
                lane=str(-lane),
                name=f"{src.label} (audio)",
                offset=frame_time(ev.start, tl.fps),
                duration=frame_time(ev.frames, tl.fps),
                start=audio_start(src, ev.source_in),
                srcEnable="audio",
            )

    ET.indent(root)
    body = ET.tostring(root, encoding="unicode")
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE fcpxml>\n{body}\n'
