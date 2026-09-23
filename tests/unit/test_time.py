from fractions import Fraction

import pytest

from multicam_engine.models.time import (
    FPS_25,
    FPS_29_97,
    Rational,
    Rounding,
    frames_to_samples,
    frames_to_seconds,
    samples_to_frames,
    seconds_to_frames,
    seconds_to_samples,
)


class TestRational:
    @pytest.mark.parametrize(
        ("text", "num", "den"),
        [
            ("30000/1001", 30000, 1001),
            ("25/1", 25, 1),
            ("25", 25, 1),
            (" 60000/2002 ", 30000, 1001),
        ],
    )
    def test_parse(self, text: str, num: int, den: int) -> None:
        r = Rational.parse(text)
        assert (r.num, r.den) == (num, den)

    @pytest.mark.parametrize("text", ["0/0", "0/1", "-25/1", "abc", "25/x", ""])
    def test_parse_rejects_invalid(self, text: str) -> None:
        with pytest.raises(ValueError, match=r"."):
            Rational.parse(text)

    def test_reduced_forms_are_equal(self) -> None:
        assert Rational(num=60000, den=2002) == FPS_29_97

    def test_is_frozen(self) -> None:
        with pytest.raises(ValueError, match="frozen"):
            FPS_25.__setattr__("num", 30)

    def test_json_round_trip(self) -> None:
        assert Rational.model_validate_json(FPS_29_97.model_dump_json()) == FPS_29_97


class TestConversions:
    def test_frames_to_seconds_is_exact(self) -> None:
        assert frames_to_seconds(30000, FPS_29_97) == Fraction(1001)

    def test_one_hour_at_29_97_has_no_drift(self) -> None:
        # Float math would accumulate error here; exact math must round-trip every frame.
        for frame in range(0, 107_892, 997):
            assert seconds_to_frames(frames_to_seconds(frame, FPS_29_97), FPS_29_97) == frame

    @pytest.mark.parametrize(
        ("rounding", "expected"),
        [(Rounding.FLOOR, 12), (Rounding.CEIL, 13), (Rounding.NEAREST, 13)],
    )
    def test_rounding_modes(self, rounding: Rounding, expected: int) -> None:
        # 0.5 s at 25 fps = exactly 12.5 frames
        assert seconds_to_frames(Fraction(1, 2), FPS_25, rounding) == expected

    def test_nearest_rounds_half_up_not_to_even(self) -> None:
        # Python's round() would give 12 (banker's rounding); we want deterministic 13.
        assert seconds_to_frames(Fraction(1, 2), FPS_25) == 13
        assert seconds_to_frames(Fraction(21, 50), FPS_25) == 11  # 10.5 -> 11, not 10

    def test_samples_frames_round_trip(self) -> None:
        assert frames_to_samples(25, FPS_25, 48_000) == 48_000
        assert samples_to_frames(48_000, 48_000, FPS_25) == 25
        assert samples_to_frames(1_601_600, 48_000, FPS_29_97) == 1000  # 1000 NTSC frames

    def test_seconds_to_samples(self) -> None:
        assert seconds_to_samples(Fraction(1001, 1000), 48_000) == 48_048

    def test_floats_are_rejected(self) -> None:
        with pytest.raises(TypeError, match="floats are not allowed"):
            seconds_to_frames(0.5, FPS_25)  # type: ignore[arg-type]

    def test_bool_is_rejected(self) -> None:
        with pytest.raises(TypeError):
            frames_to_seconds(True, FPS_25)

    def test_non_positive_sample_rate(self) -> None:
        with pytest.raises(ValueError, match="sample_rate"):
            seconds_to_samples(1, 0)
