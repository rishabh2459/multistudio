"""ffprobe JSON -> ProbeResult, without running ffprobe."""

from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest

from multicam_engine.media.probe import ProbeError, nominal_fps, parse_probe, timestamps_vary

PATH = Path("/footage/cam1.mov")


def _data(**video: Any) -> dict[str, Any]:
    v: dict[str, Any] = {
        "index": 0,
        "codec_type": "video",
        "codec_name": "hevc",
        "width": 3840,
        "height": 2160,
        "r_frame_rate": "30000/1001",
        "avg_frame_rate": "30000/1001",
        "duration": "60.060000",
        "start_time": "0.000000",
    }
    v.update(video)
    audio = {
        "index": 1,
        "codec_type": "audio",
        "codec_name": "aac",
        "sample_rate": "48000",
        "channels": 2,
        "start_time": "0.021333",
    }
    return {"streams": [v, audio], "format": {"duration": "60.1"}}


def test_basic_fields() -> None:
    r = parse_probe(_data(), PATH)
    m = r.media
    assert (m.fps.num, m.fps.den) == (30000, 1001)
    assert m.duration_frames == 1800  # 60.06 s * 29.97 fps
    assert (m.width, m.height, m.video_codec) == (3840, 2160, "hevc")
    assert (m.audio_codec, m.audio_sample_rate, m.audio_channels) == ("aac", 48000, 2)
    assert r.duration == Fraction("60.06")
    assert r.audio_start == Fraction("0.021333")
    assert (r.video_stream_index, r.audio_stream_index) == (0, 1)
    assert not m.is_vfr


def test_iphone_style_vfr_from_rates() -> None:
    r = parse_probe(_data(r_frame_rate="30/1", avg_frame_rate="18000/601"), PATH)
    assert r.media.fps.to_fraction() == 30
    assert r.media.is_vfr


def test_packet_timestamps_override_rate_heuristic() -> None:
    cfr_pts = list(range(0, 3000 * 60, 3000))
    vfr_pts = [p for i, p in enumerate(cfr_pts) if i % 5 != 0]
    data = _data(r_frame_rate="30/1", avg_frame_rate="18000/601")
    assert not parse_probe(data, PATH, video_pts=cfr_pts).media.is_vfr
    assert parse_probe(_data(), PATH, video_pts=vfr_pts).media.is_vfr


def test_rotation_swaps_dimensions() -> None:
    rotated = _data(side_data_list=[{"side_data_type": "Display Matrix", "rotation": -90}])
    r = parse_probe(rotated, PATH)
    assert (r.media.width, r.media.height) == (2160, 3840)
    assert r.rotation == 270
    assert parse_probe(_data(tags={"rotate": "180"}), PATH).media.width == 3840


def test_attached_picture_is_not_the_video() -> None:
    data = _data()
    cover = {"index": 2, "codec_type": "video", "disposition": {"attached_pic": 1}}
    data["streams"].insert(0, cover)
    assert parse_probe(data, PATH).video_stream_index == 0


def test_missing_audio_is_allowed() -> None:
    data = _data()
    data["streams"] = data["streams"][:1]
    r = parse_probe(data, PATH)
    assert r.audio_stream_index is None and r.media.audio_codec is None
    assert r.media.audio_channels == 0


def test_duration_falls_back_to_container() -> None:
    assert parse_probe(_data(duration="N/A"), PATH).duration == Fraction("60.1")


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"codec_type": "audio"}, "no video stream"),
        ({"width": 0}, "dimensions"),
        ({"r_frame_rate": "0/0", "avg_frame_rate": "0/0"}, "frame rate"),
    ],
)
def test_errors(change: dict[str, Any], message: str) -> None:
    data = _data(**change)
    data["format"] = {}
    with pytest.raises(ProbeError, match=message):
        parse_probe(data, PATH)


@pytest.mark.parametrize(
    ("r", "avg", "expected"),
    [
        (Fraction(30000, 1001), Fraction(30000, 1001), Fraction(30000, 1001)),
        (Fraction(90000), Fraction(2997, 100), Fraction(30000, 1001)),  # snapped
        (None, Fraction(25), Fraction(25)),
        (Fraction(1000000), Fraction(123, 10), Fraction(123, 10)),  # odd but kept
    ],
)
def test_nominal_fps(r: Fraction | None, avg: Fraction | None, expected: Fraction) -> None:
    assert nominal_fps(r, avg) == expected


def test_timestamps_vary() -> None:
    assert not timestamps_vary(list(range(0, 100 * 512, 512)))
    assert not timestamps_vary([0, 1001, 2002, 3004, 4004, 5005])  # 1-tick rounding
    shuffled = [0, 2, 1, 4, 3, 5]  # B-frame order, still regular
    assert not timestamps_vary([p * 100 for p in shuffled])
    assert timestamps_vary([0, 100, 200, 350, 400, 480, 600, 640, 800, 900])
    assert not timestamps_vary([0])
