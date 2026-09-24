from fractions import Fraction
from pathlib import Path
from uuid import UUID

import pytest

from multicam_engine.media.ffmpeg import FFmpegError
from multicam_engine.media.probe import ProbeResult
from multicam_engine.models import Clip, CutList, OutputSettings, Project, Segment
from multicam_engine.models.cutlist import AudioConfig, AudioMode, Reframe
from multicam_engine.models.project import MediaInfo, SyncResult
from multicam_engine.models.time import FPS_25, FPS_29_97, Rational
from multicam_engine.render.encoders import codec_of, encoder_args
from multicam_engine.render.graph import chunk_command, piece_filter
from multicam_engine.render.plan import (
    RenderPlanError,
    build_plan,
    chunk_pieces,
    clip_timing,
)

F = Fraction(30000, 1001)


def _probe(
    path: str, seconds: str, fps: Rational = FPS_29_97, audio_start: str = "0"
) -> ProbeResult:
    media = MediaInfo(fps=fps, is_vfr=False, duration_frames=100, width=1920, height=1080,
                      video_codec="h264", audio_codec="aac", audio_sample_rate=48000,
                      audio_channels=2)  # fmt: skip
    return ProbeResult(
        path=Path(path), media=media, video_stream_index=0, audio_stream_index=1,
        duration=Fraction(seconds), video_start=Fraction(0), audio_start=Fraction(audio_start),
        rotation=0,
    )  # fmt: skip


def _setup(
    b_offset_samples: int = 96_000, b_drift: float = 0.0, b_seconds: str = "60"
) -> tuple[Project, Clip, Clip, dict[UUID, ProbeResult]]:
    a = Clip(path="/f/a.mp4")
    b = Clip(path="/f/b.mp4")
    a.sync = SyncResult(reference_clip_id=a.id, offset_samples=0, sample_rate=48000, confidence=1)
    b.sync = SyncResult(reference_clip_id=a.id, offset_samples=b_offset_samples,
                        sample_rate=48000, drift_ppm=b_drift, confidence=0.9)  # fmt: skip
    project = Project(
        name="t", output=OutputSettings(fps=FPS_29_97, width=1920, height=1080),
        clips=[a, b], reference_clip_id=a.id,
    )  # fmt: skip
    probes = {a.id: _probe(a.path, "60"), b.id: _probe(b.path, b_seconds)}
    return project, a, b, probes


def _cutlist(project: Project, parts: list[tuple[Clip, int]], **kw: object) -> CutList:
    segs, start = [], 0
    for clip, n in parts:
        segs.append(Segment(start_frame=start, end_frame=start + n, clip_id=clip.id))
        start += n
    return CutList(project_id=project.id, fps=FPS_29_97, segments=segs, **kw)  # type: ignore[arg-type]


def test_clip_timing_maps_reference_time_to_clip_pts() -> None:
    _project, _a, b, probes = _setup(b_offset_samples=48_000 * 2, b_drift=100.0)
    t = clip_timing(b, probes[b.id])
    assert t.offset == 2 and t.speed == Fraction(1_000_100, 1_000_000)
    assert t.pts_at(Fraction(0)) == 2
    assert t.pts_at(Fraction(1000)) == Fraction(1000) * t.speed + 2  # +0.1 s after 1000 s
    shifted = clip_timing(b, _probe(b.path, "60", audio_start="0.021333"))
    assert shifted.pts_at(Fraction(0)) == 2 + Fraction("0.021333")


def test_pieces_follow_the_cutlist_exactly() -> None:
    project, a, b, probes = _setup(b_offset_samples=96_000, b_drift=500.0)
    cl = _cutlist(project, [(a, 100), (b, 50), (a, 30)])
    plan = build_plan(project, cl, probes)
    assert [p.frames for p in plan.pieces] == [100, 50, 30]
    assert [p.start_frame for p in plan.pieces] == [0, 100, 150]
    assert plan.total_frames == 180 and plan.duration == Fraction(180) / F
    p = plan.pieces[1]
    assert p.source_pts == Fraction(100) / F * Fraction(10005, 10000) + 2
    assert p.speed == Fraction(10005, 10000)
    assert p.head_black == p.tail_black == 0 and not p.is_black
    assert plan.pieces[0].source_pts == 0
    assert (plan.width, plan.height) == (1920, 1080)


def test_clip_that_starts_late_gets_black_head() -> None:
    # b started 1 s AFTER the reference (offset -1 s): its first second is missing.
    project, a, b, probes = _setup(b_offset_samples=-48_000)
    cl = _cutlist(project, [(b, 60), (a, 10)])
    plan = build_plan(project, cl, probes)
    piece = plan.pieces[0]
    assert piece.head_black == 30  # frames 0..29 (t < ~1 s) are before b started
    assert piece.source_pts == Fraction(30) / F - 1  # first covered frame, ~0.001 s into b
    assert any("outside the recording" in w for w in plan.warnings)


def test_clip_that_ends_early_gets_black_tail_or_is_all_black() -> None:
    project, a, b, probes = _setup(b_offset_samples=0, b_seconds="2")
    cl = _cutlist(project, [(a, 30), (b, 60), (b, 30)])  # b ends at 2 s (frame ~60)
    plan = build_plan(project, cl, probes)
    assert plan.pieces[1].tail_black == 30  # frames 60..89: b's last frame is at ~1.97 s
    assert plan.pieces[2].is_black and plan.pieces[2].source_pts is None
    assert any("not recording" in w for w in plan.warnings)


def test_audio_tracks() -> None:
    project, a, b, probes = _setup()
    mix = build_plan(project, _cutlist(project, [(a, 10)], audio=AudioConfig(
        gains_db={a.id: 0.0, b.id: -6.0})), probes)  # fmt: skip
    gains = {t.clip_id: t.gain for t in mix.audio}
    assert gains[a.id] == 1.0 and gains[b.id] == pytest.approx(0.501, abs=1e-3)
    single = build_plan(project, _cutlist(project, [(a, 10)], audio=AudioConfig(
        mode=AudioMode.SINGLE, single_clip_id=b.id)), probes)  # fmt: skip
    assert [t.clip_id for t in single.audio] == [b.id]
    silent = build_plan(project, _cutlist(project, [(a, 10)]), probes)
    assert silent.audio == [] and any("silent" in w for w in silent.warnings)


def test_plan_errors() -> None:
    project, a, b, probes = _setup()
    cl = _cutlist(project, [(a, 10), (b, 10)])
    with pytest.raises(RenderPlanError, match="not probed"):
        build_plan(project, cl, {a.id: probes[a.id]})
    with pytest.raises(RenderPlanError, match="even"):
        build_plan(project, cl, probes, width=1919, height=1080)
    other = CutList(project_id=project.id, fps=FPS_25, segments=cl.segments)
    with pytest.raises(ValueError, match="fps"):
        build_plan(project, other, probes)


def test_chunking() -> None:
    project, a, b, probes = _setup()
    cl = _cutlist(project, [(a, 300), (b, 300), (a, 300), (b, 3000), (a, 30)])
    plan = build_plan(project, cl, probes, chunk_seconds=25, max_pieces_per_chunk=24)
    assert plan.chunks == [[0, 1], [2], [3], [4]]
    assert chunk_pieces(plan.pieces, F, 10_000, max_pieces=2) == [[0, 1], [2, 3], [4]]


# ------------------------------------------------------------------ graph
def test_piece_filter_chain() -> None:
    project, a, b, probes = _setup(b_offset_samples=96_000, b_drift=500.0)
    plan = build_plan(
        project, _cutlist(project, [(a, 100), (b, 50)]), probes, width=640, height=360
    )
    f = piece_filter(plan.pieces[1], "1:v:0", plan, "p1")
    assert f.startswith("[1:v:0]setpts='(PTS*TB-")
    assert f"/{float(plan.pieces[1].speed):.9f}/TB'" in f
    assert "fps=30000/1001:start_time=0:round=near" in f
    assert f.count("trim=end_frame=50") == 2
    assert "scale=640:360:force_original_aspect_ratio=decrease" in f
    assert "tpad=start=0:stop=0" in f and f.endswith("[p1]")


def test_black_piece_and_reframe() -> None:
    project, a, b, probes = _setup(b_offset_samples=0, b_seconds="1")
    cl = _cutlist(project, [(a, 60), (b, 45)])
    cl.segments[0].reframe = Reframe(cx=0.3, cy=0.5, scale=2.0)
    plan = build_plan(project, cl, probes, width=640, height=360)
    black = piece_filter(plan.pieces[1], None, plan, "p1")
    assert black.startswith("color=c=black:s=640x360:r=30000/1001,trim=end_frame=45")
    zoomed = piece_filter(plan.pieces[0], "0:v:0", plan, "p0")
    assert "crop=w=iw/2.000000:h=ih/2.000000" in zoomed and "0.300000*iw" in zoomed


def test_chunk_command_inputs_and_frame_count(tmp_path: Path) -> None:
    project, a, b, probes = _setup(b_offset_samples=96_000)
    plan = build_plan(project, _cutlist(project, [(a, 200), (b, 50), (a, 10)]), probes)
    args = chunk_command(plan, [0, 1, 2], tmp_path / "part.mkv", ["-c:v", "libx264"])
    assert args.count("-i") == 3 and "-copyts" in args
    seeks = [args[i + 1] for i, v in enumerate(args) if v == "-ss"]
    assert seeks[0] == "0.000000000"  # never seeks before the start
    assert float(seeks[1]) == pytest.approx(float(Fraction(200) / F + 2 - 3))
    assert args[args.index("-frames:v") + 1] == "260"
    graph = args[args.index("-filter_complex") + 1]
    assert graph.endswith("[p0][p1][p2]concat=n=3:v=1:a=0[vout]")


def test_encoder_arguments() -> None:
    assert encoder_args("h264_videotoolbox", 12000, 29.97)[:2] == ["-b:v", "12000k"]
    assert "-g" in encoder_args("h264_videotoolbox", 12000, 29.97)
    assert encoder_args("h264_nvenc", 8000, 30)[:2] == ["-preset", "p5"]
    assert "-crf" in encoder_args("libx264", 8000, 30)
    assert encoder_args("mpeg4", 8000, 25)[:2] == ["-q:v", "3"]
    assert encoder_args("h264_mf", 8000, 25)[-2:] == ["-hw_encoding", "1"]
    assert codec_of("hevc_videotoolbox") == "hevc" and codec_of("libx265") == "hevc"
    assert codec_of("libopenh264") == "h264"


def test_choose_encoder(monkeypatch: pytest.MonkeyPatch) -> None:
    import multicam_engine.render.encoders as enc

    enc.available_encoders.cache_clear()
    listing = (
        " V....D h264_nvenc   NVIDIA\n V....D libx264  x264\n A....D aac  AAC\n"
        " V....D mpeg4  MPEG-4\n"
    )
    monkeypatch.setattr(enc, "run_tool", lambda *_a, **_k: listing.encode())
    assert enc.listed_encoders() == {"h264_nvenc", "libx264", "mpeg4"}
    monkeypatch.setattr(enc, "encoder_works", lambda name: name != "h264_nvenc")  # no GPU
    assert enc.choose_encoder("h264") == ("libx264", "h264")
    assert enc.choose_encoder("hevc") == ("libx264", "h264")  # falls back to H.264
    assert enc.choose_encoder("h264", "mpeg4") == ("mpeg4", "h264")
    with pytest.raises(FFmpegError, match="not available"):
        enc.choose_encoder("h264", "h264_nvenc")
    enc.available_encoders.cache_clear()
