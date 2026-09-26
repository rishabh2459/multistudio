from fractions import Fraction

import pytest

from multicam_engine.export.timecode import (
    frames_to_timecode,
    timecode_rate,
    timecode_to_frames,
)

NTSC = Fraction(30000, 1001)


def test_non_drop_frame() -> None:
    rate = timecode_rate(Fraction(25))
    assert not rate.drop and rate.nominal == 25
    assert frames_to_timecode(0, rate) == "00:00:00:00"
    assert frames_to_timecode(25 * 3600 + 26, rate) == "01:00:01:01"
    assert timecode_to_frames("01:00:01:01", rate) == 25 * 3600 + 26


@pytest.mark.parametrize(
    ("frames", "label"),
    [
        (0, "00:00:00;00"),
        (1799, "00:00:59;29"),
        (1800, "00:01:00;02"),  # ;00 and ;01 are skipped
        (17981, "00:09:59;29"),
        (17982, "00:10:00;00"),  # every tenth minute keeps them
        (107892, "01:00:00;00"),  # one hour of 29.97 is 107892 frames
    ],
)
def test_drop_frame_labels(frames: int, label: str) -> None:
    rate = timecode_rate(NTSC)
    assert rate.drop
    assert frames_to_timecode(frames, rate) == label
    assert timecode_to_frames(label, rate) == frames


def test_drop_frame_round_trip_and_59_94() -> None:
    for fps in (NTSC, Fraction(60000, 1001)):
        rate = timecode_rate(fps)
        for frames in range(0, 200_000, 997):
            assert timecode_to_frames(frames_to_timecode(frames, rate), rate) == frames
    rate = timecode_rate(Fraction(60000, 1001))
    assert frames_to_timecode(3600, rate) == "00:01:00;04"


def test_options_and_errors() -> None:
    assert not timecode_rate(NTSC, drop=False).drop
    assert not timecode_rate(Fraction(25), drop=True).drop  # only NTSC rates drop
    with pytest.raises(ValueError):
        timecode_to_frames("1:00:00:00", timecode_rate(Fraction(25)))
    with pytest.raises(ValueError):
        timecode_to_frames("00:00:00:25", timecode_rate(Fraction(25)))
    with pytest.raises(ValueError):
        frames_to_timecode(-1, timecode_rate(Fraction(25)))
