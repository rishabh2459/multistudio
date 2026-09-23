"""Full sync on generated multicam video files (AAC audio, like real cameras). Needs ffmpeg."""

import json
from pathlib import Path

import pytest

from multicam_engine.benchmark.ground_truth import GroundTruth, GTClip
from multicam_engine.benchmark.sync_accuracy import evaluate_recording
from multicam_engine.cli import main
from multicam_engine.sync import REPORT_SAMPLE_RATE, SyncReport, sync_files

from ..media_factory import write_clip
from ..synth import SimClip, camera_pair

SR = 8000


def _recording(ffmpeg: str, folder: Path, *, offset_s: float, drift_ppm: float) -> SimClip:
    folder.mkdir(parents=True, exist_ok=True)
    ref, clip = camera_pair(offset_s=offset_s, drift_ppm=drift_ppm, duration_s=75, seed=11)
    write_clip(ffmpeg, folder / "cam1.mp4", ref, SR)
    write_clip(ffmpeg, folder / "cam2.mp4", clip.audio, SR, fps="25", vfr=True)
    return clip


def _true_ms(clip: SimClip, ref_ms: int) -> int:
    return round(ref_ms + clip.true_offset_at(ref_ms * SR / 1000) / SR * 1000)


def test_sync_files_recovers_offset_and_drift(ffmpeg: str, tmp_path: Path) -> None:
    clip = _recording(ffmpeg, tmp_path, offset_s=3.25, drift_ppm=150)
    report = sync_files([tmp_path / "cam1.mp4", tmp_path / "cam2.mp4"], cache_dir=None)
    assert report.reference_file.endswith("cam1.mp4")
    ref_entry, cam2 = report.clips
    assert ref_entry.is_reference and ref_entry.offset_samples == 0
    assert cam2.sample_rate == REPORT_SAMPLE_RATE
    true_offset_ms = clip.true_offset_at(0) / SR * 1000
    assert cam2.offset_seconds * 1000 == pytest.approx(true_offset_ms, abs=2.0)
    assert cam2.drift_ppm == pytest.approx(150, abs=10)
    assert cam2.confidence > 0.8
    assert cam2.warnings == []


def test_explicit_reference_and_negative_offset(ffmpeg: str, tmp_path: Path) -> None:
    clip = _recording(ffmpeg, tmp_path, offset_s=2.0, drift_ppm=0)
    # Use cam2 as reference: cam1 now started LATER than the reference -> negative.
    report = sync_files(
        [tmp_path / "cam1.mp4", tmp_path / "cam2.mp4"], reference=tmp_path / "cam2.mp4"
    )
    cam1 = report.clip("cam1.mp4")
    assert cam1.offset_seconds * 1000 == pytest.approx(-clip.true_offset_at(0) / SR * 1000, abs=2.0)


def test_clip_without_audio_gets_warning(ffmpeg: str, tmp_path: Path) -> None:
    _recording(ffmpeg, tmp_path, offset_s=1.0, drift_ppm=0)
    silent = write_clip(ffmpeg, tmp_path / "wide.mp4", None, SR, duration_s=5)
    report = sync_files([tmp_path / "cam1.mp4", tmp_path / "cam2.mp4", silent])
    wide = report.clip("wide.mp4")
    assert wide.confidence == 0.0
    assert any("no audio" in w for w in wide.warnings)
    assert report.clip("cam2.mp4").confidence > 0.8
    assert report.has_warnings


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        sync_files([tmp_path / "a.mp4", tmp_path / "b.mp4"])
    with pytest.raises(ValueError, match="two clips"):
        sync_files([tmp_path / "a.mp4"])


def test_cli_sync_writes_valid_report(
    ffmpeg: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _recording(ffmpeg, tmp_path, offset_s=-1.5, drift_ppm=60)
    out = tmp_path / "sync.json"
    code = main(
        ["sync", str(tmp_path / "cam1.mp4"), str(tmp_path / "cam2.mp4"),
         "--out", str(out), "--cache-dir", str(tmp_path / "cache")]
    )  # fmt: skip
    assert code == 0
    report = SyncReport.model_validate_json(out.read_text(encoding="utf-8"))
    assert len(report.clips) == 2
    assert "offset" in capsys.readouterr().out
    assert main(["validate", "sync", str(out)]) == 0
    assert main(["probe", str(tmp_path / "cam2.mp4")]) == 0
    assert "VFR" in capsys.readouterr().out
    assert main(["probe", "--json", str(tmp_path / "cam1.mp4")]) == 0
    assert json.loads(capsys.readouterr().out)["is_vfr"] is False


def test_accuracy_benchmark_on_synthetic_recording(ffmpeg: str, tmp_path: Path) -> None:
    rec = tmp_path / "T1"
    clip = _recording(ffmpeg, rec, offset_s=2.2, drift_ppm=200)
    ref_start, ref_end = 1000, 73000
    gt = GroundTruth(
        recording_id="T1",
        reference_file="cam1.mp4",
        clips=[
            GTClip(file="cam1.mp4", speaker_label="Host", clap_start_ms=ref_start,
                   clap_end_ms=ref_end),
            GTClip(file="cam2.mp4", speaker_label="Guest",
                   clap_start_ms=_true_ms(clip, ref_start), clap_end_ms=_true_ms(clip, ref_end)),
        ],
    )  # fmt: skip
    (rec / "ground_truth.json").write_text(gt.model_dump_json(indent=2), encoding="utf-8")

    acc = evaluate_recording(rec)
    assert acc.passed
    (cam2,) = acc.clips
    assert abs(cam2.start_error_ms) < 3 and cam2.end_error_ms is not None
    assert abs(cam2.end_error_ms) < 3
    assert cam2.frame_ms == pytest.approx(40.0)  # cam2 is 25 fps
    assert main(["gt", "eval-sync", str(rec)]) == 0
