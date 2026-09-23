"""Phase 1 accuracy benchmark on REAL test footage (samples/*/ground_truth.json).

Run with: make test-accuracy
Target (docs/TEST_FOOTAGE.md §6): sync error < 1 frame at the start AND the end
of every recording, including 60+ minute ones (T6).
"""

from pathlib import Path

import pytest

from multicam_engine.benchmark.audacity import GROUND_TRUTH_FILE
from multicam_engine.benchmark.sync_accuracy import evaluate_recording

SAMPLES = Path(__file__).resolve().parents[2] / "samples"
RECORDINGS = sorted(p.parent for p in SAMPLES.glob(f"*/{GROUND_TRUTH_FILE}"))

pytestmark = pytest.mark.accuracy


@pytest.mark.skipif(not RECORDINGS, reason="no test footage in samples/ yet")
@pytest.mark.parametrize("recording", RECORDINGS, ids=[p.name for p in RECORDINGS])
def test_sync_within_one_frame(recording: Path, ffmpeg: str) -> None:
    acc = evaluate_recording(recording)
    for clip in acc.clips:
        print(
            f"{acc.recording_id} {clip.file}: start {clip.start_error_ms:+.2f} ms, "
            f"end {clip.end_error_ms} ms, drift {clip.measured_drift_ppm:+.1f} ppm "
            f"(true {clip.true_drift_ppm}), confidence {clip.confidence:.2f}"
        )
        assert clip.within_one_frame, f"{clip.file}: error {clip.worst_error_ms:.1f} ms"
