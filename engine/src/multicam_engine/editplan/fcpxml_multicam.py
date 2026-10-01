"""FCPXML with a real multicam clip (PL7): Final Cut opens an editable multicam edit.

Layout::

    resources
      format(s), asset per source file
      media "<name> Multicam"
        multicam  (timeline = the plan's sequence frames, tcStart 0)
          mc-angle per camera / mic: [gap] + asset-clip at the source's sync position
    library / event / project / sequence / spine
      mc-clip per live shot: video from the live camera's angle, audio from every
      audio angle (mix) -> each cut is an angle switch the editor can change

Angle storylines are contiguous, so a source that starts after frame 0 is preceded
by a gap. Times are exact frame multiples (timeline) or on the source's frame grid.
Clock drift is not modelled inside angles (FCP has no per-angle speed); the plan
warns when a source drifts.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from fractions import Fraction
from uuid import UUID

from multicam_engine.editplan.model import EditPlan, PlanMedia
from multicam_engine.export._util import file_url
from multicam_engine.export.fcpxml import FCPXML_VERSION, _format_name, frame_time, rational

DROP_RATES = (Fraction(30000, 1001), Fraction(60000, 1001))


def _fps(media: PlanMedia) -> Fraction:
    return media.fps.to_fraction()


def _angle_id(index: int) -> str:
    return f"A{index}"


def to_fcpxml_multicam(plan: EditPlan) -> str:
    seq_fps = plan.sequence.fps.to_fraction()
    total = plan.sequence.duration_frames
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

    seq_format = format_id(seq_fps, plan.sequence.width, plan.sequence.height)

    # Angles: cameras first (by angle number), then sound-only sources used for audio.
    cameras = sorted((m for m in plan.media if m.angle is not None), key=lambda m: m.angle or 0)
    audio_ids = {t.clip_id for t in plan.audio_tracks}
    mics = [m for m in plan.media if m.angle is None and m.clip_id in audio_ids]
    angle_media = [*cameras, *mics]
    angle_of: dict[UUID, str] = {m.clip_id: _angle_id(i) for i, m in enumerate(angle_media, 1)}

    assets: dict[UUID, str] = {}
    for i, m in enumerate(angle_media, start=1):
        assets[m.clip_id] = f"a{i}"
        fps = _fps(m)
        attrs = {
            "id": assets[m.clip_id],
            "name": m.name,
            "start": frame_time(m.start_timecode_frames if m.has_timecode else 0, fps),
            "duration": frame_time(max(1, m.duration_frames), fps),
        }
        if m.width > 0:
            attrs.update(hasVideo="1", format=format_id(fps, m.width, m.height), videoSources="1")
        if m.has_audio:
            attrs.update(
                hasAudio="1",
                audioSources="1",
                audioChannels=str(max(1, m.audio_channels)),
                audioRate=str(m.sample_rate),
            )
        asset = ET.SubElement(resources, "asset", attrs)
        ET.SubElement(asset, "media-rep", kind="original-media", src=file_url(m.path))

    drop = seq_fps in DROP_RATES
    media_el = ET.SubElement(resources, "media", id="mc1", name=f"{plan.sequence.name} Multicam")
    multicam = ET.SubElement(
        media_el, "multicam", format=seq_format, tcStart="0s", tcFormat="DF" if drop else "NDF"
    )
    for m in angle_media:
        angle = ET.SubElement(
            multicam, "mc-angle", name=m.label or m.name, angleID=angle_of[m.clip_id]
        )
        _angle_content(angle, m, assets[m.clip_id], seq_fps, total)

    library = ET.SubElement(root, "library")
    event = ET.SubElement(library, "event", name="Multicam Studio")
    project = ET.SubElement(event, "project", name=plan.sequence.name)
    sequence = ET.SubElement(
        project,
        "sequence",
        format=seq_format,
        duration=frame_time(total, seq_fps),
        tcStart="0s",
        tcFormat="DF" if drop else "NDF",
        audioLayout="stereo",
        audioRate="48k",
    )
    spine = ET.SubElement(sequence, "spine")
    markers = sorted(plan.markers, key=lambda mk: mk.frame)
    audio_angles = [angle_of[cid] for cid in sorted(audio_ids, key=str) if cid in angle_of]
    position = 0
    for ev in plan.video_events:
        if ev.start > position:  # frames no camera recorded: the spine must stay contiguous
            ET.SubElement(
                spine,
                "gap",
                name="Gap",
                offset=frame_time(position, seq_fps),
                start="0s",
                duration=frame_time(ev.start - position, seq_fps),
            )
        position = ev.end
        clip = ET.SubElement(
            spine,
            "mc-clip",
            ref="mc1",
            name=plan.media_by_id()[ev.clip_id].label or "Multicam",
            offset=frame_time(ev.start, seq_fps),
            start=frame_time(ev.start, seq_fps),  # multicam time == sequence time
            duration=frame_time(ev.frames, seq_fps),
        )
        for mk in markers:
            if ev.start <= mk.frame < ev.end:
                ET.SubElement(
                    clip,
                    "marker",
                    start=frame_time(mk.frame, seq_fps),
                    duration=frame_time(mk.duration, seq_fps),
                    value=mk.note or "Check this cut",
                )
        live = angle_of[ev.clip_id]
        if live in audio_angles:
            ET.SubElement(clip, "mc-source", angleID=live, srcEnable="all")
        else:
            ET.SubElement(clip, "mc-source", angleID=live, srcEnable="video")
        for aid in audio_angles:
            if aid != live:
                ET.SubElement(clip, "mc-source", angleID=aid, srcEnable="audio")

    ET.indent(root)
    body = ET.tostring(root, encoding="unicode")
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE fcpxml>\n{body}\n'


def _angle_content(
    angle: ET.Element, m: PlanMedia, asset: str, seq_fps: Fraction, total: int
) -> None:
    """[gap] + the source placed so sequence frame F shows source time (F - record_start)."""
    src_fps = _fps(m)
    record = m.record_start_frame
    offset = max(0, record)  # where the source becomes visible
    lead = offset - record  # sequence frames of the source before frame 0 (trimmed)
    # Source length in sequence frames (rounded down: never past the media's end).
    length = int(Fraction(m.duration_frames) / src_fps * seq_fps)
    duration = min(length - lead, total - offset)
    if duration <= 0:
        return  # the source does not overlap the edit
    if offset > 0:
        ET.SubElement(
            angle, "gap", name="Gap", offset="0s", start="0s", duration=frame_time(offset, seq_fps)
        )
    tc = m.start_timecode_frames if m.has_timecode else 0
    first_src_frame = round(Fraction(lead) / seq_fps * src_fps)
    attrs = {
        "ref": asset,
        "name": m.name,
        "offset": frame_time(offset, seq_fps),
        "start": frame_time(tc + first_src_frame, src_fps),
        "duration": frame_time(duration, seq_fps),
    }
    if m.width <= 0:
        attrs["srcEnable"] = "audio"
    ET.SubElement(angle, "asset-clip", attrs)
