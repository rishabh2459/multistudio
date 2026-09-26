"""NLE export: timeline mapping and the three file formats (no ffmpeg needed)."""

import re
import xml.etree.ElementTree as ET
from fractions import Fraction
from pathlib import Path
from uuid import uuid4

import pytest

from multicam_engine.export import NleFormat, build_nle_timeline, write_nle
from multicam_engine.export._util import file_url, reel_names
from multicam_engine.export.timeline import NleTimeline
from multicam_engine.media.probe import ProbeResult
from multicam_engine.models import CutList, OutputSettings
from multicam_engine.models.cutlist import AudioConfig, AudioMode, Segment
from multicam_engine.models.project import Clip, ClipRole, MediaInfo, Project, SyncResult
from multicam_engine.models.time import Rational

FPS = Rational(num=30000, den=1001)
F = Fraction(30000, 1001)


def _probe(path: str, seconds: float, fps: Rational = FPS, tc: str | None = None) -> ProbeResult:
    media = MediaInfo(
        fps=fps,
        is_vfr=False,
        duration_frames=round(seconds * fps.num / fps.den),
        width=1920,
        height=1080,
        video_codec="h264",
        audio_codec="aac",
        audio_sample_rate=48000,
        audio_channels=2,
        start_timecode=tc,
    )
    return ProbeResult(
        path=Path(path),
        media=media,
        video_stream_index=0,
        audio_stream_index=1,
        duration=Fraction(seconds).limit_denominator(1000),
        video_start=Fraction(0),
        audio_start=Fraction(0),
        rotation=0,
    )


def _sync(ref: Clip, seconds: float, drift_ppm: float = 0.0) -> SyncResult:
    return SyncResult(
        reference_clip_id=ref.id,
        offset_samples=round(seconds * 48000),
        sample_rate=48000,
        drift_ppm=drift_ppm,
        confidence=0.9,
    )


@pytest.fixture
def setup() -> tuple[Project, CutList, dict]:  # type: ignore[type-arg]
    host = Clip(path="/rec/Host Cam.mp4", role=ClipRole.SPEAKER, speaker_label="Host")
    guest = Clip(path="/rec/guest.mp4", role=ClipRole.SPEAKER, speaker_label="Guest")
    wide = Clip(path="/rec/wide.mov", role=ClipRole.WIDE)
    host.sync = _sync(host, 0.0)
    guest.sync = _sync(host, 1.0)  # started 1 s before the host camera
    wide.sync = _sync(host, -2.0, drift_ppm=100.0)  # started 2 s late, fast clock
    project = Project(
        name="Episode 7",
        output=OutputSettings(fps=FPS, width=1920, height=1080),
        clips=[host, guest, wide],
        reference_clip_id=host.id,
    )
    minute = 1798  # ~60 s at 29.97
    cut = CutList(
        project_id=project.id,
        fps=FPS,
        segments=[
            Segment(clip_id=wide.id, start_frame=0, end_frame=300),
            Segment(clip_id=host.id, start_frame=300, end_frame=minute),
            Segment(clip_id=guest.id, start_frame=minute, end_frame=minute * 10),
        ],
        audio=AudioConfig(gains_db={host.id: 0.0, guest.id: 0.0, wide.id: -6.0}),
    )
    probes = {
        host.id: _probe(host.path, 700, tc="01:00:00;00"),
        guest.id: _probe(guest.path, 700),
        wide.id: _probe(wide.path, 700, fps=Rational(num=25, den=1)),
    }
    return project, cut, probes


def _timeline(setup: tuple[Project, CutList, dict]) -> NleTimeline:  # type: ignore[type-arg]
    return build_nle_timeline(*setup)


def test_video_events_follow_the_cuts(setup) -> None:  # type: ignore[no-untyped-def]
    project = setup[0]
    host, guest, wide = project.clips
    tl = _timeline(setup)
    assert [e.clip_id for e in tl.video] == [wide.id, host.id, guest.id]
    first, second, third = tl.video
    # The wide camera started 2 s late: the first 2 s stay empty (black).
    assert first.start == round(2 * F) and first.end == 300
    assert 0 <= first.source_in < Fraction(1, 25)  # the wide camera's first frame
    assert (second.start, second.end) == (300, 1798)
    assert second.source_in == Fraction(300) / F  # reference camera: media time = timeline
    assert third.source_in == pytest.approx(float(Fraction(1798) / F + 1), abs=1e-9)
    assert any("not recorded" in w for w in tl.warnings)


def test_audio_is_one_clip_per_camera_unless_the_clock_drifts(setup) -> None:  # type: ignore[no-untyped-def]
    project = setup[0]
    host, guest, wide = project.clips
    tl = _timeline(setup)
    assert len(tl.audio[host.id]) == 1 and len(tl.audio[guest.id]) == 1
    assert tl.audio[guest.id][0].source_in == 1  # 1 s into the guest file at t = 0
    pieces = tl.audio[wide.id]
    # 100 ppm drifts a quarter frame (8.3 ms) in ~83 s: 10 minutes -> 8 pieces
    assert 7 <= len(pieces) <= 10
    assert [p.end for p in pieces[:-1]] == [p.start for p in pieces[1:]]  # no holes

    def exact(frame: int) -> Fraction:
        return Fraction(frame) / F * (1 + Fraction(100, 10**6)) - 2

    for ev in pieces:  # in sync at the start and still within 1/4 frame at the end
        assert abs(ev.source_in - exact(ev.start)) < Fraction(1, 10**6)
        drifted = ev.source_in + Fraction(ev.frames) / F - exact(ev.end)
        assert abs(drifted) <= Fraction(1, 4) / F
    assert any("drift" in w for w in tl.warnings)


def test_single_audio_mode(setup) -> None:  # type: ignore[no-untyped-def]
    project, cut, probes = setup
    host = project.clips[0]
    single = cut.model_copy(
        update={"audio": AudioConfig(mode=AudioMode.SINGLE, single_clip_id=host.id)}
    )
    tl = build_nle_timeline(project, single, probes)
    assert list(tl.audio) == [host.id]


def test_fcpxml(setup) -> None:  # type: ignore[no-untyped-def]
    text = write_nle(_timeline(setup), NleFormat.FCPXML)
    assert text.startswith('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE fcpxml>')
    root = ET.fromstring(text.split("\n", 2)[2])
    assert root.tag == "fcpxml" and root.get("version") == "1.9"
    seq = root.find("./library/event/project/sequence")
    assert seq is not None and seq.get("tcFormat") == "DF"
    assert seq.get("duration") == f"{17980 * 1001}/30000s"
    assets = {a.get("id"): a for a in root.iter("asset")}
    host_asset = next(a for a in assets.values() if a.get("name") == "Host Cam.mp4")
    assert host_asset.get("start") == f"{107892 * 1001}/30000s"  # 01:00:00;00 (drop-frame)
    rep = host_asset.find("media-rep")
    assert rep is not None and rep.get("src") == "file:///rec/Host%20Cam.mp4"
    clips = root.findall(".//gap/asset-clip")
    video = [c for c in clips if c.get("srcEnable") == "video"]
    audio = [c for c in clips if c.get("srcEnable") == "audio"]
    assert len(video) == 3 and {c.get("lane") for c in video} == {"1"}
    assert {c.get("lane") for c in audio} == {"-1", "-2", "-3"}
    host_clip = next(c for c in video if c.get("ref") == host_asset.get("id"))
    assert host_clip.get("offset") == f"{300 * 1001}/30000s"
    # host media at timeline frame 300 = 300 frames after its 01:00:00;00 start
    assert host_clip.get("start") == f"{(107892 + 300) * 1001}/30000s"
    for c in clips:  # timeline positions are on the frame grid
        offset = Fraction(c.get("offset", "").rstrip("s"))
        assert (offset / Fraction(1001, 30000)).denominator == 1


def test_premiere_xml(setup) -> None:  # type: ignore[no-untyped-def]
    text = write_nle(_timeline(setup), NleFormat.XMEML)
    root = ET.fromstring(text.split("\n", 2)[2])
    assert root.tag == "xmeml" and root.get("version") == "5"
    seq = root.find("sequence")
    assert seq is not None and seq.findtext("duration") == "17980"
    assert seq.findtext("rate/timebase") == "30" and seq.findtext("rate/ntsc") == "TRUE"
    vclips = root.findall("./sequence/media/video/track/clipitem")
    assert [c.findtext("start") for c in vclips] == ["60", "300", "1798"]
    assert vclips[1].findtext("in") == "300" and vclips[1].findtext("out") == "1798"
    wide = vclips[0]
    assert wide.findtext("rate/timebase") == "25"  # source rate for in/out
    atracks = root.findall("./sequence/media/audio/track")
    assert len(atracks) == 3
    files = [f for f in root.iter("file") if f.find("pathurl") is not None]
    assert len(files) == 3  # full file element only on first use
    urls = {f.findtext("pathurl") for f in files}
    assert "file://localhost/rec/Host%20Cam.mp4" in urls
    host_file = next(f for f in files if f.findtext("name") == "Host Cam.mp4")
    assert host_file.findtext("timecode/string") == "01:00:00;00"


def test_edl(setup) -> None:  # type: ignore[no-untyped-def]
    text = write_nle(_timeline(setup), NleFormat.EDL)
    lines = text.splitlines()
    assert lines[0] == "TITLE: Episode 7" and lines[1] == "FCM: DROP FRAME"
    events = [line for line in lines if re.match(r"^\d{3}  ", line)]
    assert len(events) == 3
    pattern = r"^(\d{3})  (\S{1,8}) +V     C        (\S{11}) (\S{11}) (\S{11}) (\S{11})$"
    parsed = [re.match(pattern, e) for e in events]
    assert all(parsed)
    host = parsed[1]
    assert host is not None
    assert host.group(2) == "HOST_CAM"
    assert host.group(3) == "01:00:10;00"  # 01:00:00;00 + 300 frames
    assert (host.group(5), host.group(6)) == ("00:00:10;00", "00:00:59;28")
    assert "* FROM CLIP NAME: Host Cam.mp4" in lines


def test_helpers() -> None:
    assert reel_names(["cam 1.mp4", "cam 1.mov", "A very long name.mp4", "é.mp4"]) == [
        "CAM_1",
        "CAM_12",
        "A_VERY_L",
        "REEL",
    ]
    assert file_url("C:\\Footage\\cam 1.mp4") == "file:///C:/Footage/cam%201.mp4"
    assert file_url("/a/b#c.mp4", localhost=True) == "file://localhost/a/b%23c.mp4"


def test_unknown_clip_is_refused(setup) -> None:  # type: ignore[no-untyped-def]
    project, cut, probes = setup
    probes = dict(probes)
    probes.pop(project.clips[0].id)
    with pytest.raises(ValueError, match="not probed"):
        build_nle_timeline(project, cut, probes)
    other = cut.model_copy(update={"project_id": uuid4()})
    with pytest.raises(ValueError):
        build_nle_timeline(project, other, dict(setup[2]))
