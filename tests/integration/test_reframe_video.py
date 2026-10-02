"""Auto framing on real video: a (public-domain) face moves across the frame;
the detector finds it, the 9:16 crop follows it, and the rendered vertical
video keeps the face near the centre. Needs ffmpeg and the face model."""

import subprocess
from pathlib import Path

import numpy as np
import numpy.typing as npt
import pytest

from multicam_engine.media.ffmpeg import find_tool
from multicam_engine.media.probe import probe
from multicam_engine.models import CutList, OutputSettings, Project, Segment
from multicam_engine.models.project import Clip
from multicam_engine.models.time import Rational
from multicam_engine.reframe import (
    FaceTracks,
    ReframeSettings,
    YuNetDetector,
    auto_reframe,
    clip_geometry,
    detect_faces,
)
from multicam_engine.reframe.sample import sample_frames
from multicam_engine.render import OutputPreset, render

DATA = Path(__file__).resolve().parents[1] / "data"
FPS = Rational(num=30, den=1)
W, H, SECONDS = 1280, 720, 8
VERTICAL = OutputPreset("vtest", "360x640 test output", 360, 640, "h264", 3000, 96)


FACE_SIZE = 256  # astronaut.jpg is 256 x 256


def _face_image() -> npt.NDArray[np.uint8]:
    """The portrait as BGR pixels, decoded with ffmpeg (no imaging library needed)."""
    raw = subprocess.run(
        [find_tool("ffmpeg"), "-v", "error", "-i", str(DATA / "astronaut.jpg"),
         "-vf", f"scale={FACE_SIZE}:{FACE_SIZE}", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
        check=True, capture_output=True,
    ).stdout  # fmt: skip
    return np.frombuffer(raw, np.uint8).reshape(FACE_SIZE, FACE_SIZE, 3).copy()


def face_x(frame: int) -> int:
    """Left edge of the 256 px portrait at a frame: slides 100 -> 900 px."""
    return 100 + round(800 * frame / (SECONDS * 30 - 1))


def _moving_face_video(ffmpeg: str, path: Path) -> Path:
    portrait = _face_image()
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
           "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}", "-framerate", "30",
           "-i", "pipe:0", "-c:v", "mpeg4", "-q:v", "3", "-g", "15", "-pix_fmt", "yuv420p",
           str(path)]  # fmt: skip
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    assert proc.stdin is not None
    for i in range(SECONDS * 30):
        frame = np.full((H, W, 3), 40, dtype=np.uint8)
        x = face_x(i)
        frame[200:456, x : x + 256] = portrait
        proc.stdin.write(frame.tobytes())
    proc.stdin.close()
    assert proc.wait() == 0
    return path


def test_detector_finds_the_astronaut(face_model: Path) -> None:
    faces = YuNetDetector(face_model).detect(_face_image())
    assert len(faces) == 1
    f = faces[0]
    assert f.score > 0.8
    assert 0.3 < f.cx < 0.55 and 0.15 < f.cy < 0.4 and 0.1 < f.h < 0.4
    assert YuNetDetector(face_model).detect(np.full((360, 640, 3), 40, np.uint8)) == []


def test_sampling_detection_and_vertical_render(
    ffmpeg: str, face_model: Path, tmp_path: Path
) -> None:
    video = _moving_face_video(ffmpeg, tmp_path / "cam.mp4")
    info = probe(video)
    samples = list(sample_frames(video, every_s=0.5, info=info))
    assert 12 <= len(samples) <= 18
    assert [s.t for s in samples] == sorted(s.t for s in samples)
    assert samples[0].image.shape == (360, 640, 3)

    detections = detect_faces(video, YuNetDetector(face_model), every_s=0.5, info=info)
    seen = [d for d in detections if d.faces]
    assert len(seen) >= len(detections) - 1
    for d in seen:  # the face centre follows the portrait (face is ~112 px into it)
        expected = (face_x(round(d.t * 30)) + 112) / W
        assert d.faces[0].cx == pytest.approx(expected, abs=0.04)

    clip = Clip(path=str(video))
    project = Project(name="v", output=OutputSettings(fps=FPS, width=W, height=H),
                      clips=[clip], reference_clip_id=clip.id)  # fmt: skip
    whole = Segment(clip_id=clip.id, start_frame=0, end_frame=SECONDS * 30)
    cut = CutList(project_id=project.id, fps=FPS, segments=[whole])
    geom = clip_geometry(clip, info)
    framed, report = auto_reframe(
        project, cut, {clip.id: FaceTracks.build(detections, geom)}, {clip.id: geom},
        ReframeSettings(punch="off"),
    )  # fmt: skip
    vertical = framed.segments[0].reframe_vertical
    assert vertical is not None and vertical.path and report.framed == 1
    assert vertical.center_at(200)[0] > vertical.center_at(20)[0] + 0.3  # it pans

    out = tmp_path / "vertical.mp4"
    render(project, framed, out, preset=VERTICAL)
    rendered = probe(out)
    assert (rendered.media.width, rendered.media.height) == (360, 640)
    detector = YuNetDetector(face_model)
    offsets = []
    for s in sample_frames(out, every_s=1.0, info=rendered):
        faces = detector.detect(s.image)
        if faces and 0.5 < s.t < SECONDS - 0.5:
            offsets.append(abs(faces[0].cx - 0.5))
    assert len(offsets) >= 3  # the render has a keyframe every 2 s
    assert max(offsets) < 0.2  # the face stays near the middle of the tall frame
