"""NLE export against real files: embedded timecode is read, and every exported
video cut points at the same source frame the render shows. Needs ffmpeg."""

import subprocess
import xml.etree.ElementTree as ET
from fractions import Fraction
from pathlib import Path

from multicam_engine.export import NleFormat, build_nle_timeline, write_nle
from multicam_engine.media.probe import probe
from multicam_engine.models import Clip, CutList, OutputSettings, Project, Segment
from multicam_engine.models.project import SyncResult
from multicam_engine.models.time import Rational
from multicam_engine.render import OutputPreset, render

from ..frame_codes import read_indices, write_indexed_video

FPS = Rational(num=30000, den=1001)
F = Fraction(30000, 1001)
TINY = OutputPreset("test", "64x32 test output", 64, 32, "h264", 1500, 128)


def _with_timecode(ffmpeg: str, src: Path, dst: Path, tc: str) -> Path:
    subprocess.run(
        [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-i", str(src),
         "-c", "copy", "-timecode", tc, str(dst)],
        check=True,
    )  # fmt: skip
    return dst


def test_exported_cuts_match_the_render(ffmpeg: str, tmp_path: Path) -> None:
    write_indexed_video(ffmpeg, tmp_path / "a0.mp4", 900)
    write_indexed_video(ffmpeg, tmp_path / "b0.mp4", 900)
    a_path = _with_timecode(ffmpeg, tmp_path / "a0.mp4", tmp_path / "a.mov", "01:00:00;00")
    b_path = tmp_path / "b0.mp4"
    pa, pb = probe(a_path), probe(b_path)
    assert pa.media.start_timecode == "01:00:00;00"
    assert pb.media.start_timecode is None

    a, b = Clip(path=str(a_path)), Clip(path=str(b_path))
    a.sync = SyncResult(reference_clip_id=a.id, offset_samples=0, sample_rate=48000, confidence=1)
    b.sync = SyncResult(reference_clip_id=a.id, offset_samples=96000, sample_rate=48000,
                        drift_ppm=300.0, confidence=1)  # fmt: skip
    project = Project(name="t", output=OutputSettings(fps=FPS, width=64, height=32),
                      clips=[a, b], reference_clip_id=a.id)  # fmt: skip
    # (shots of 3+ frames: a lone frame between two cuts is too blurred by the
    # lossy test encode to read its frame number back reliably)
    bounds, order = [0, 40, 130, 133, 400, 700], [a, b, a, b, a]
    cut = CutList(project_id=project.id, fps=FPS, segments=[
        Segment(start_frame=s, end_frame=e, clip_id=c.id)
        for s, e, c in zip(bounds, bounds[1:], order, strict=False)])  # fmt: skip

    render(project, cut, tmp_path / "out.mp4", preset=TINY)
    rendered = read_indices(ffmpeg, tmp_path / "out.mp4")
    tl = build_nle_timeline(project, cut, {a.id: pa, b.id: pb})
    assert len(tl.video) == 5
    for ev in tl.video:
        src_frame = round(ev.source_in * tl.sources[ev.clip_id].fps)
        assert src_frame == rendered[ev.start], (ev, rendered[ev.start])

    fcpxml = write_nle(tl, NleFormat.FCPXML)
    root = ET.fromstring(fcpxml.split("\n", 2)[2])
    starts = [c.get("start") for c in root.iter("asset-clip") if c.get("srcEnable") == "video"]
    # the reference camera's clips start at its embedded 01:00:00;00 (107892 frames)
    assert starts[0] == f"{107892 * 1001}/30000s"
    for text in (write_nle(tl, NleFormat.XMEML), write_nle(tl, NleFormat.EDL)):
        assert a_path.name in text
