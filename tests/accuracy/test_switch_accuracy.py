"""Phase 2 accuracy benchmark on REAL test footage (samples/*/ground_truth.json).

Run with: make test-accuracy
Target (docs/TEST_FOOTAGE.md §6): >= 95 % of speech time on the correct camera
(balanced preset), and no shot shorter than the preset minimum.
"""

from pathlib import Path

import pytest

from multicam_engine.benchmark.audacity import GROUND_TRUTH_FILE
from multicam_engine.benchmark.ground_truth import GroundTruth
from multicam_engine.benchmark.switch_accuracy import TARGET_ACCURACY, evaluate_switching

SAMPLES = Path(__file__).resolve().parents[2] / "samples"
RECORDINGS = [
    p.parent
    for p in sorted(SAMPLES.glob(f"*/{GROUND_TRUTH_FILE}"))
    if GroundTruth.model_validate_json(p.read_text(encoding="utf-8")).speech
]

pytestmark = pytest.mark.accuracy


@pytest.mark.skipif(not RECORDINGS, reason="no test footage with speech labels in samples/ yet")
@pytest.mark.parametrize("recording", RECORDINGS, ids=[p.name for p in RECORDINGS])
def test_speaker_accuracy(recording: Path, ffmpeg: str) -> None:
    acc = evaluate_switching(recording)
    print(
        f"{acc.recording_id}: accuracy {acc.accuracy:.1%}, {acc.segments} shots "
        f"(avg {acc.mean_shot_s:.1f} s), short shots {acc.short_shots}, wide {acc.wide_share:.0%}"
    )
    assert acc.accuracy >= TARGET_ACCURACY
    assert acc.short_shots == 0
