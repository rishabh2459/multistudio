"""Score a ``SyncReport`` against a recording's hand-labelled ground truth.

For every clip we predict where its start clap (and end clap, if labelled)
should be, using the sync result, and compare with where it really is:

    predicted_clip_position = ref_clap + offset_at_zero + drift * ref_clap

Errors are in milliseconds; "within one frame" uses the clip's frame rate.
"""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path

from pydantic import Field

from multicam_engine.benchmark.audacity import GROUND_TRUTH_FILE
from multicam_engine.benchmark.ground_truth import GroundTruth
from multicam_engine.media.probe import probe
from multicam_engine.models._base import StrictModel
from multicam_engine.sync.engine import SyncReport, sync_files


class ClipSyncError(StrictModel):
    file: str
    start_error_ms: float
    end_error_ms: float | None
    true_drift_ppm: float | None
    measured_drift_ppm: float
    confidence: float
    frame_ms: float = Field(gt=0)

    @property
    def worst_error_ms(self) -> float:
        errors = [abs(self.start_error_ms)]
        if self.end_error_ms is not None:
            errors.append(abs(self.end_error_ms))
        return max(errors)

    @property
    def within_one_frame(self) -> bool:
        return self.worst_error_ms < self.frame_ms


class SyncAccuracy(StrictModel):
    recording_id: str
    clips: list[ClipSyncError]

    @property
    def passed(self) -> bool:
        return all(c.within_one_frame for c in self.clips)


def score_sync(
    gt: GroundTruth,
    report: SyncReport,
    frame_ms: dict[str, float] | None = None,
) -> SyncAccuracy:
    """Compare. ``frame_ms`` maps clip file name -> frame duration (default 30 fps)."""
    ref = gt.reference
    results: list[ClipSyncError] = []
    for clip in gt.clips:
        if clip.file == gt.reference_file:
            continue
        measured = report.clip(clip.file)
        rate = Fraction(measured.sample_rate)
        offset0_ms = float(Fraction(measured.offset_samples) / rate * 1000)
        k = measured.drift_ppm * 1e-6

        def predict(ref_ms: int, offset0_ms: float = offset0_ms, k: float = k) -> float:
            return ref_ms + offset0_ms + k * ref_ms

        start_err = predict(ref.clap_start_ms) - clip.clap_start_ms
        end_err = None
        if clip.clap_end_ms is not None and ref.clap_end_ms is not None:
            end_err = predict(ref.clap_end_ms) - clip.clap_end_ms
        results.append(
            ClipSyncError(
                file=clip.file,
                start_error_ms=round(start_err, 3),
                end_error_ms=None if end_err is None else round(end_err, 3),
                true_drift_ppm=gt.true_drift_ppm(clip.file),
                measured_drift_ppm=measured.drift_ppm,
                confidence=measured.confidence,
                frame_ms=(frame_ms or {}).get(clip.file, 1000 / 30),
            )
        )
    return SyncAccuracy(recording_id=gt.recording_id, clips=results)


def evaluate_recording(recording_dir: Path, cache_dir: Path | None = None) -> SyncAccuracy:
    """Run sync on a test recording folder and score it (needs ffmpeg)."""
    gt = GroundTruth.model_validate_json(
        (recording_dir / GROUND_TRUTH_FILE).read_text(encoding="utf-8")
    )
    paths = [recording_dir / c.file for c in gt.clips]
    report = sync_files(paths, reference=recording_dir / gt.reference_file, cache_dir=cache_dir)
    frame_ms = {
        c.file: float(1000 / probe(recording_dir / c.file).media.fps.to_fraction())
        for c in gt.clips
    }
    return score_sync(gt, report, frame_ms)
