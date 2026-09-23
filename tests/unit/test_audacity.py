import pytest

from multicam_engine.benchmark.audacity import (
    GroundTruthBuildError,
    MetaClip,
    RecordingMeta,
    build_ground_truth,
)
from multicam_engine.models import ClipRole

META = RecordingMeta(
    recording_id="T2",
    description="3 cams",
    reference_file="cam1.mp4",
    clips=[
        MetaClip(file="cam1.mp4", speaker_label="Host"),
        MetaClip(file="cam2.mp4", speaker_label="Guest"),
        MetaClip(file="wide.mp4", role=ClipRole.WIDE),
    ],
)

LABELS = "\n".join(
    [
        "1.250000\t1.250000\tclap_start@cam1.mp4",
        "3.000500\t3.000500\tclap_start@cam2.mp4",
        "0.800000\t0.800000\tclap_start@wide.mp4",
        "3601.250000\t3601.250000\tclap_end@cam1.mp4",
        "3603.000000\t3603.000000\tclap_end@cam2.mp4",
        "10.000000\t14.500000\tGuest",
        "5.000000\t9.000000\tHost",
        "\\\t1000.000000\t2000.000000",  # spectral line, must be ignored
        "0.000000\t600.000000\tannotated_range",
        "",
    ]
)


def test_builds_ground_truth() -> None:
    gt = build_ground_truth(META, LABELS)
    assert gt.recording_id == "T2"
    assert gt.true_offset_ms("cam2.mp4") == 1_751  # 3.0005 s rounds half-up to 3001 ms
    assert gt.true_offset_ms("wide.mp4") == -450
    assert gt.true_drift_ppm("wide.mp4") is None
    assert [t.speaker_label for t in gt.speech] == ["Host", "Guest"]  # sorted by time
    assert gt.annotated_range is not None
    assert (gt.annotated_range.start_ms, gt.annotated_range.end_ms) == (0, 600_000)


def test_missing_clap_is_reported() -> None:
    labels = "1.0\t1.0\tclap_start@cam1.mp4\n2.0\t2.0\tclap_start@cam2.mp4\n"
    with pytest.raises(GroundTruthBuildError, match=r"wide\.mp4"):
        build_ground_truth(META, labels)


@pytest.mark.parametrize(
    ("line", "message"),
    [
        ("1.0\t2.0\tNobody", "unknown label"),
        ("1.0\t1.0\tclap_middle@cam1.mp4", "unknown marker"),
        ("1.0\t1.0\tclap_start@cam9.mp4", "not listed"),
        ("abc\t1.0\tHost", "invalid time"),
        ("1.0 2.0 Host", "expected"),
        ("5.0\t5.0\tHost", "must be a region"),
        ("1.0\t2.0\t   ", "empty label"),
    ],
)
def test_bad_lines_are_reported_with_line_number(line: str, message: str) -> None:
    with pytest.raises(GroundTruthBuildError, match=message) as exc:
        build_ground_truth(META, line + "\n")
    assert "line 1" in str(exc.value)


def test_duplicate_clap_rejected() -> None:
    labels = "1.0\t1.0\tclap_start@cam1.mp4\n2.0\t2.0\tclap_start@cam1.mp4\n"
    with pytest.raises(GroundTruthBuildError, match="duplicate"):
        build_ground_truth(META, labels)
