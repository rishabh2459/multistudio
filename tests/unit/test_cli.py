import json
from pathlib import Path

import pytest

from multicam_engine.cli import main

from .factories import make_project


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert "multicam" in capsys.readouterr().out


def test_validate_ok_and_fail(tmp_path: Path) -> None:
    good = tmp_path / "project.json"
    good.write_text(make_project().model_dump_json(), encoding="utf-8")
    assert main(["validate", "project", str(good)]) == 0

    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"name": ""}), encoding="utf-8")
    assert main(["validate", "project", str(bad)]) == 1

    assert main(["validate", "project", str(tmp_path / "missing.json")]) == 1


def _write_recording(root: Path) -> Path:
    rec = root / "T1"
    rec.mkdir()
    (rec / "meta.json").write_text(
        json.dumps(
            {
                "recording_id": "T1",
                "reference_file": "cam1.mp4",
                "clips": [
                    {"file": "cam1.mp4", "speaker_label": "Host"},
                    {"file": "cam2.mp4", "speaker_label": "Guest"},
                ],
            }
        ),
        encoding="utf-8",
    )
    (rec / "labels.txt").write_text(
        "1.0\t1.0\tclap_start@cam1.mp4\n2.5\t2.5\tclap_start@cam2.mp4\n4.0\t6.0\tHost\n",
        encoding="utf-8",
    )
    return rec


def test_gt_build_then_check(tmp_path: Path) -> None:
    rec = _write_recording(tmp_path)
    assert main(["gt", "build", str(rec)]) == 0
    gt = json.loads((rec / "ground_truth.json").read_text(encoding="utf-8"))
    assert gt["clips"][1]["clap_start_ms"] == 2500

    # Media files missing -> check fails
    assert main(["gt", "check", str(tmp_path)]) == 1
    (rec / "cam1.mp4").touch()
    (rec / "cam2.mp4").touch()
    assert main(["gt", "check", str(tmp_path)]) == 0


def test_gt_build_reports_errors(tmp_path: Path) -> None:
    rec = _write_recording(tmp_path)
    (rec / "labels.txt").write_text("1.0\t1.0\tclap_start@cam1.mp4\n", encoding="utf-8")
    assert main(["gt", "build", str(rec)]) == 1
    assert not (rec / "ground_truth.json").exists()
