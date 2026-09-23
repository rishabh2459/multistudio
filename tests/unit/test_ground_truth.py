import pytest
from pydantic import ValidationError

from multicam_engine.benchmark import GroundTruth, GTClip, MsRange, SpeechTurn


def make_gt(**overrides: object) -> GroundTruth:
    data: dict[str, object] = {
        "recording_id": "T1",
        "reference_file": "cam1.mp4",
        "clips": [
            GTClip(
                file="cam1.mp4", speaker_label="Host", clap_start_ms=2_000, clap_end_ms=3_602_000
            ),
            # cam2 started 1.5 s earlier (clap appears later in its own file) and its
            # clock runs 100 ppm fast (3600 s span -> +360 ms).
            GTClip(
                file="cam2.mp4", speaker_label="Guest", clap_start_ms=3_500, clap_end_ms=3_603_860
            ),
        ],
        "speech": [SpeechTurn(speaker_label="Host", start_ms=5_000, end_ms=9_000)],
    }
    data.update(overrides)
    return GroundTruth.model_validate(data)


def test_offset_sign_convention() -> None:
    gt = make_gt()
    assert gt.true_offset_ms("cam1.mp4") == 0
    assert gt.true_offset_ms("cam2.mp4") == 1_500  # positive = started earlier


def test_drift_ppm() -> None:
    gt = make_gt()
    drift = gt.true_drift_ppm("cam2.mp4")
    assert drift == pytest.approx(100.0)
    assert gt.true_drift_ppm("cam1.mp4") == 0.0


def test_drift_unknown_without_end_clap() -> None:
    gt = make_gt(
        clips=[
            GTClip(file="cam1.mp4", speaker_label="Host", clap_start_ms=0),
            GTClip(file="cam2.mp4", speaker_label="Guest", clap_start_ms=10),
        ]
    )
    assert gt.true_drift_ppm("cam2.mp4") is None


def test_reference_must_be_a_clip() -> None:
    with pytest.raises(ValidationError, match="reference_file"):
        make_gt(reference_file="nope.mp4")


def test_speech_label_must_exist() -> None:
    with pytest.raises(ValidationError, match="Stranger"):
        make_gt(speech=[SpeechTurn(speaker_label="Stranger", start_ms=0, end_ms=10)])


def test_recording_id_format() -> None:
    with pytest.raises(ValidationError):
        make_gt(recording_id="episode1")


def test_end_clap_must_follow_start() -> None:
    with pytest.raises(ValidationError, match="clap_end_ms"):
        GTClip(file="a.mp4", clap_start_ms=100, clap_end_ms=50)


def test_ms_range_ordering() -> None:
    with pytest.raises(ValidationError):
        MsRange(start_ms=10, end_ms=10)
