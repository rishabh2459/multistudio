"""Phase 3: real renders checked frame by frame and sample by sample. Needs ffmpeg."""

import threading
from fractions import Fraction
from pathlib import Path

import numpy as np
import pytest

from multicam_engine.cli import main
from multicam_engine.media.probe import probe
from multicam_engine.models import Clip, CutList, OutputSettings, Project, Segment
from multicam_engine.models.cutlist import AudioConfig, AudioMode
from multicam_engine.models.project import SyncResult
from multicam_engine.models.time import Rational
from multicam_engine.render import (
    OutputPreset,
    RenderCancelledError,
    RenderProgress,
    make_proxy,
    render,
)
from multicam_engine.render.run import count_video_frames

from ..frame_codes import (
    BLACK,
    click_onsets,
    clicks,
    read_audio,
    read_indices,
    write_indexed_video,
)

FPS = Rational(num=30000, den=1001)
F = Fraction(30000, 1001)
TINY = OutputPreset("test", "64x32 test output", 64, 32, "h264", 1500, 128)


def _project(
    a_path: Path, b_path: Path, *, b_offset_s: int = 2, b_drift: float = 0.0
) -> tuple[Project, Clip, Clip]:
    a, b = Clip(path=str(a_path)), Clip(path=str(b_path))
    a.sync = SyncResult(reference_clip_id=a.id, offset_samples=0, sample_rate=48000, confidence=1)
    b.sync = SyncResult(reference_clip_id=a.id, offset_samples=48000 * b_offset_s,
                        sample_rate=48000, drift_ppm=b_drift, confidence=1)  # fmt: skip
    project = Project(name="t", output=OutputSettings(fps=FPS, width=64, height=32),
                      clips=[a, b], reference_clip_id=a.id)  # fmt: skip
    return project, a, b


def _cutlist(project: Project, bounds: list[int], clips: list[Clip], **kw: object) -> CutList:
    segs = [Segment(start_frame=s, end_frame=e, clip_id=c.id)
            for s, e, c in zip(bounds, bounds[1:], clips, strict=False)]  # fmt: skip
    return CutList(project_id=project.id, fps=FPS, segments=segs, **kw)  # type: ignore[arg-type]


def test_every_cut_lands_on_the_exact_frame(ffmpeg: str, tmp_path: Path) -> None:
    """Many cuts (incl. 1-frame shots), drift 500 ppm, rendered in several chunks."""
    write_indexed_video(ffmpeg, tmp_path / "a.mp4", 900)
    write_indexed_video(ffmpeg, tmp_path / "b.mp4", 900)
    project, a, b = _project(tmp_path / "a.mp4", tmp_path / "b.mp4", b_drift=500.0)
    bounds = [0, 37, 100, 101, 250, 400, 420, 780]
    order = [a, b, a, b, a, b, a]
    result = render(project, _cutlist(project, bounds, order), tmp_path / "out.mp4",
                    preset=TINY, chunk_seconds=5, max_pieces_per_chunk=3)  # fmt: skip
    got = read_indices(ffmpeg, tmp_path / "out.mp4")

    expected: list[int] = []
    speed = 1 + Fraction(500, 10**6)
    for s, e, clip in zip(bounds, bounds[1:], order, strict=False):
        for n in range(s, e):
            t = Fraction(n) / F
            pts = t if clip is a else t * speed + 2
            expected.append(round(pts * F))
    assert len(got) == 780 == result.frames
    assert got == expected
    assert count_video_frames(tmp_path / "out.mp4") == 780
    assert not [w for w in result.warnings if "frames" in w]


def test_vfr_phone_footage_becomes_constant_frame_rate(ffmpeg: str, tmp_path: Path) -> None:
    write_indexed_video(ffmpeg, tmp_path / "a.mp4", 600)
    write_indexed_video(ffmpeg, tmp_path / "phone.mp4", 600, rate="30", vfr=True)
    project, a, b = _project(tmp_path / "a.mp4", tmp_path / "phone.mp4", b_offset_s=1)
    render(project, _cutlist(project, [0, 30, 330], [a, b]), tmp_path / "out.mp4", preset=TINY)
    got = read_indices(ffmpeg, tmp_path / "out.mp4")[30:]
    assert len(got) == 300
    for j, idx in enumerate(got):
        t = (Fraction(30 + j) / F + 1) * 30  # phone frame number shown at this moment
        assert abs(idx - float(t)) <= 1.6, (j, idx, float(t))  # dropped frames -> neighbour
    assert got == sorted(got)


def test_black_where_the_camera_was_not_recording(ffmpeg: str, tmp_path: Path) -> None:
    write_indexed_video(ffmpeg, tmp_path / "a.mp4", 300)
    write_indexed_video(ffmpeg, tmp_path / "b.mp4", 60)  # b: only 2 s long
    project, a, b = _project(tmp_path / "a.mp4", tmp_path / "b.mp4", b_offset_s=-1)
    # b started 1 s after the reference and stops 2 s later (t = 1 s .. 3 s)
    result = render(project, _cutlist(project, [0, 150, 180], [b, a]), tmp_path / "out.mp4",
                    preset=TINY)  # fmt: skip
    got = read_indices(ffmpeg, tmp_path / "out.mp4")
    assert len(got) == 180
    assert set(got[:29]) == {BLACK}  # before b started
    assert got[31] == 1 and got[80] == 50  # b's own frames
    assert set(got[92:150]) == {BLACK}  # after b stopped
    assert got[150:] == list(range(150, 180))
    assert any("outside the recording" in w for w in result.warnings)


def test_master_audio_is_continuous_and_in_sync(ffmpeg: str, tmp_path: Path) -> None:
    """Clicks in b's audio must come out exactly where the sync line puts them."""
    sr = 48_000
    write_indexed_video(ffmpeg, tmp_path / "a.mp4", 450, audio=clicks([], 15.0))
    b_clicks = [3.0, 6.5, 11.0, 14.0]
    write_indexed_video(ffmpeg, tmp_path / "b.mp4", 450, audio=clicks(b_clicks, 15.0))
    drift = 300.0
    project, a, b = _project(tmp_path / "a.mp4", tmp_path / "b.mp4", b_offset_s=2, b_drift=drift)
    cl = _cutlist(project, [0, 100, 200, 360], [a, b, a],
                  audio=AudioConfig(mode=AudioMode.SINGLE, single_clip_id=b.id))  # fmt: skip
    render(project, cl, tmp_path / "out.mp4", preset=TINY)
    audio = read_audio(ffmpeg, tmp_path / "out.mp4", sr)
    assert abs(len(audio) - round(360 / F * sr)) < 2048  # whole timeline, one track
    speed = 1 + drift * 1e-6
    expected = [(c - 2) / speed for c in b_clicks if 0 <= (c - 2) / speed < 360 / F - 0.01]
    found = click_onsets(audio, sr)
    assert len(found) == len(expected)
    for f_s, e_s in zip(found, expected, strict=True):
        assert abs(f_s - e_s) < 0.002, (f_s, e_s)  # within 2 ms


def test_audio_mix_with_gains(ffmpeg: str, tmp_path: Path) -> None:
    write_indexed_video(ffmpeg, tmp_path / "a.mp4", 150, audio=clicks([1.0], 5.0))
    write_indexed_video(ffmpeg, tmp_path / "b.mp4", 150, audio=clicks([4.0], 5.0))
    project, a, b = _project(tmp_path / "a.mp4", tmp_path / "b.mp4", b_offset_s=2)
    cl = _cutlist(project, [0, 90], [a],
                  audio=AudioConfig(gains_db={a.id: 0.0, b.id: -6.0}))  # fmt: skip
    render(project, cl, tmp_path / "out.mp4", preset=TINY)
    audio = read_audio(ffmpeg, tmp_path / "out.mp4")
    onsets = click_onsets(audio, threshold=0.15)
    assert [round(t, 2) for t in onsets] == [1.0, 2.0]  # a's click, then b's (4 s - 2 s)
    peak_a = np.abs(audio[int(0.99 * 48000) : int(1.02 * 48000)]).max()
    peak_b = np.abs(audio[int(1.99 * 48000) : int(2.02 * 48000)]).max()
    assert peak_b / peak_a == pytest.approx(0.5, abs=0.08)  # -6 dB


def test_progress_and_cancel(ffmpeg: str, tmp_path: Path) -> None:
    write_indexed_video(ffmpeg, tmp_path / "a.mp4", 300, audio=clicks([1.0], 10.0))
    write_indexed_video(ffmpeg, tmp_path / "b.mp4", 300)
    project, a, b = _project(tmp_path / "a.mp4", tmp_path / "b.mp4")
    cl = _cutlist(project, [0, 100, 200, 250], [a, b, a],
                  audio=AudioConfig(gains_db={a.id: 0.0}))  # fmt: skip
    seen: list[RenderProgress] = []
    render(project, cl, tmp_path / "out.mp4", preset=TINY, on_progress=seen.append,
           chunk_seconds=2)  # fmt: skip
    fractions = [p.fraction for p in seen]
    assert fractions == sorted(fractions) and fractions[-1] == 1.0
    assert {p.stage for p in seen} >= {"audio", "video", "join", "done"}

    cancel = threading.Event()

    def stop_in_video(p: RenderProgress) -> None:
        if p.stage == "video":
            cancel.set()

    with pytest.raises(RenderCancelledError):
        render(project, cl, tmp_path / "cancelled.mp4", preset=TINY, on_progress=stop_in_video,
               cancel=cancel, chunk_seconds=2)  # fmt: skip
    assert not (tmp_path / "cancelled.mp4").exists()
    assert not list(tmp_path.glob(".cancelled.render-*"))  # temp files cleaned up


def test_proxy_keeps_timing(ffmpeg: str, tmp_path: Path) -> None:
    src = write_indexed_video(ffmpeg, tmp_path / "cam.mp4", 120, audio=clicks([1.0], 4.0))
    proxy = make_proxy(src, tmp_path / "proxies", height=16)
    info = probe(proxy)
    assert info.media.height == 16 and info.media.duration_frames == 120
    assert count_video_frames(proxy) == 120
    assert make_proxy(src, tmp_path / "proxies", height=16) == proxy  # reused


def test_cli_render_encoders_proxy(
    ffmpeg: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_indexed_video(ffmpeg, tmp_path / "a.mp4", 120, audio=clicks([1.0], 4.0))
    write_indexed_video(ffmpeg, tmp_path / "b.mp4", 120, audio=clicks([2.0], 4.0))
    project, a, b = _project(tmp_path / "a.mp4", tmp_path / "b.mp4", b_offset_s=0)
    cl = _cutlist(project, [0, 50, 100], [a, b], audio=AudioConfig(gains_db={a.id: 0.0}))
    (tmp_path / "project.json").write_text(project.model_dump_json(), encoding="utf-8")
    (tmp_path / "cutlist.json").write_text(cl.model_dump_json(), encoding="utf-8")
    out = tmp_path / "ep.mp4"
    code = main(["render", "--project", str(tmp_path / "project.json"),
                 "--cutlist", str(tmp_path / "cutlist.json"), "--out", str(out),
                 "--preset", "draft", "--audio-from", "b.mp4"])  # fmt: skip
    assert code == 0
    info = probe(out)
    assert (info.media.width, info.media.height) == (1280, 720)
    assert info.media.duration_frames == 100
    assert "wrote" in capsys.readouterr().out
    bad = ["render", "--project", str(tmp_path / "project.json"),
           "--cutlist", str(tmp_path / "cutlist.json"), "--out", str(out),
           "--audio-from", "x.mp4"]  # fmt: skip
    assert main(bad) == 1
    assert main(["encoders"]) == 0
    assert "H.264" in capsys.readouterr().out
    assert main(["proxy", str(tmp_path / "a.mp4"), "--out-dir", str(tmp_path / "px")]) == 0
