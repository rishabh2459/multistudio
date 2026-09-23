"""Sync pipeline: align every clip to a reference clip using audio only.

Per clip (against the reference):

1. **Usable-audio check** - silent or near-silent audio gives a warning and a
   zero-confidence result instead of a crash.
2. **Coarse** - GCC-PHAT over the whole recording at 1 kHz finds candidate
   offsets (top 3 peaks), so clips may start late, end early or only partly overlap.
3. **Fine + drift** - for each candidate, GCC-PHAT in windows across the overlap
   at the full analysis rate, then a robust line fit gives offset and drift.
4. **Confidence** - peak sharpness x window agreement; the best candidate wins.
   Low confidence produces a warning so the UI can ask the user to check.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path
from typing import Literal
from uuid import UUID

import numpy as np
from pydantic import Field
from scipy import signal as sp_signal

from multicam_engine import __version__
from multicam_engine.media.audio import SYNC_SAMPLE_RATE, NoAudioError, load_audio
from multicam_engine.models._base import StrictModel
from multicam_engine.models.project import SyncResult
from multicam_engine.sync.confidence import sync_confidence
from multicam_engine.sync.drift import (
    DriftFit,
    WindowMeasurement,
    fit_drift,
    measure_windows,
    overlap_range,
)
from multicam_engine.sync.gcc_phat import FloatArray, find_peaks, gcc_phat_curve

#: Offsets are reported at 48 kHz (20 us steps) regardless of the analysis rate.
REPORT_SAMPLE_RATE = 48_000


@dataclass(frozen=True)
class SyncParams:
    coarse_rate: int = 1_000
    coarse_candidates: int = 3
    window_s: float = 20.0
    window_spacing_s: float = 150.0
    min_windows: int = 5
    max_windows: int = 30
    search_margin_s: float = 0.1
    refine_search_s: float = 0.02
    max_drift_ppm: float = 500.0
    inlier_tolerance_ms: float = 1.0
    min_window_psr: float = 6.0
    silence_dbfs: float = -55.0
    #: A clip needs at least this much audio above ``silence_dbfs`` to be usable.
    min_active_s: float = 2.0
    min_overlap_s: float = 10.0
    low_confidence: float = 0.5
    #: Frequencies below this never vote (rumble, mains hum at 50/60 Hz).
    low_cut_hz: float = 80.0


@dataclass(frozen=True)
class PairSync:
    """Result of syncing one signal against the reference (analysis sample rate)."""

    offset_at_zero: float  # samples at sample_rate: offset at reference position 0
    slope: float
    confidence: float
    sample_rate: int
    overlap_s: float
    windows_used: int
    windows_total: int
    warnings: tuple[str, ...] = ()
    measurements: tuple[WindowMeasurement, ...] = field(default=(), repr=False)

    @property
    def drift_ppm(self) -> float:
        return self.slope * 1e6

    @property
    def offset_seconds(self) -> float:
        return self.offset_at_zero / self.sample_rate


# ------------------------------------------------------------------ helpers
def active_seconds(x: FloatArray, sample_rate: int, silence_dbfs: float) -> float:
    """Seconds of audio (in 100 ms frames) louder than ``silence_dbfs``."""
    frame = max(1, sample_rate // 10)
    n = len(x) // frame
    if n == 0:
        return 0.0
    frames = np.asarray(x[: n * frame], dtype=np.float64).reshape(n, frame)
    rms = np.sqrt(np.mean(np.square(frames), axis=1))
    threshold = 10.0 ** (silence_dbfs / 20.0)
    return float(np.count_nonzero(rms > threshold)) * frame / sample_rate


def _resample(x: FloatArray, from_rate: int, to_rate: int) -> FloatArray:
    if from_rate == to_rate:
        return x
    g = math.gcd(from_rate, to_rate)
    out: FloatArray = np.asarray(
        sp_signal.resample_poly(np.asarray(x, dtype=np.float64), to_rate // g, from_rate // g),
        dtype=np.float64,
    )
    return out


def _failed(sample_rate: int, *warnings: str, overlap_s: float = 0.0) -> PairSync:
    return PairSync(
        offset_at_zero=0.0,
        slope=0.0,
        confidence=0.0,
        sample_rate=sample_rate,
        overlap_s=overlap_s,
        windows_used=0,
        windows_total=0,
        warnings=warnings,
    )


# ---------------------------------------------------------------- core algorithm
def sync_signals(
    ref: FloatArray,
    sig: FloatArray,
    sample_rate: int,
    params: SyncParams | None = None,
) -> PairSync:
    """Align ``sig`` to ``ref``. Pure function on arrays; never raises on bad audio."""
    p = params or SyncParams()
    sr = sample_rate

    for name, x in (("reference", ref), ("clip", sig)):
        if active_seconds(x, sr, p.silence_dbfs) < p.min_active_s:
            return _failed(
                sr, f"{name} audio is silent or too quiet to sync; align this clip manually"
            )

    # 1) coarse: whole recording at a low rate, several candidate peaks
    ref_c = _resample(ref, sr, p.coarse_rate)
    sig_c = _resample(sig, sr, p.coarse_rate)
    min_ov = int(p.min_overlap_s * p.coarse_rate)
    lag_range = (-(len(ref_c) - min_ov), len(sig_c) - min_ov)
    if lag_range[0] > lag_range[1]:
        lag_range = (-(len(ref_c) - 1), len(sig_c) - 1)  # both clips are very short
    nyquist_c = p.coarse_rate / 2
    coarse_band = (min(0.5, p.low_cut_hz / nyquist_c), 0.9)
    lags, values = gcc_phat_curve(ref_c, sig_c, lag_range=lag_range, band=coarse_band)
    candidates = find_peaks(
        lags, values, count=p.coarse_candidates, exclusion=max(2, p.coarse_rate // 20)
    )
    scale = sr / p.coarse_rate

    # 2) fine + drift for each candidate; keep the most confident
    best: tuple[float, float, DriftFit | None, list[WindowMeasurement]] | None = None
    tolerance = p.inlier_tolerance_ms * 1e-3 * sr
    measure = partial(
        measure_windows,
        ref,
        sig,
        sample_rate=sr,
        window_s=p.window_s,
        spacing_s=p.window_spacing_s,
        min_windows=p.min_windows,
        max_windows=p.max_windows,
        silence_dbfs=p.silence_dbfs,
    )
    # The coarse offset is an average over the clip; with drift the offset at the ends
    # differs by up to max_drift * duration / 2, so the first pass searches that far.
    wide_search = p.search_margin_s + p.max_drift_ppm * 1e-6 * max(len(ref), len(sig)) / sr
    # Inside a first-pass window, drift smears the peak by up to max_drift * window.
    loose_tolerance = tolerance + p.max_drift_ppm * 1e-6 * p.window_s * sr
    for cand in candidates:
        coarse_offset = cand.lag * scale
        # Pass 1: wide search around the coarse offset, loose agreement.
        windows = measure(offset_at_zero=coarse_offset, search_s=wide_search)
        fit = fit_drift(windows, inlier_tolerance=loose_tolerance, min_psr=p.min_window_psr)
        # Pass 2: read the clip along the fitted line (no drift smear), strict agreement.
        if fit is not None:
            windows = measure(
                offset_at_zero=fit.offset_at_zero, slope=fit.slope, search_s=p.refine_search_s
            )
            fit = fit_drift(windows, inlier_tolerance=tolerance, min_psr=p.min_window_psr)
        conf = sync_confidence(windows, fit)
        if best is None or conf > best[1]:
            best = (coarse_offset, conf, fit, windows)
        if conf >= 0.95:
            break  # clear winner; skip weaker candidates

    if best is None:
        return _failed(sr, "no alignment found; align this clip manually")
    coarse_offset, conf, fit, windows = best
    offset0 = fit.offset_at_zero if fit else coarse_offset
    slope = fit.slope if fit else 0.0
    start, end = overlap_range(len(ref), len(sig), offset0)
    overlap_s = (end - start) / sr

    warnings: list[str] = []
    if overlap_s < p.min_overlap_s:
        warnings.append(
            f"clips overlap for only {overlap_s:.1f} s (need {p.min_overlap_s:.0f} s); "
            "check that they are from the same recording"
        )
    if abs(slope) * 1e6 > p.max_drift_ppm:
        warnings.append(f"implausible clock drift ({slope * 1e6:+.0f} ppm)")
        conf = min(conf, p.low_confidence / 2)
    if conf < p.low_confidence:
        warnings.append(f"low sync confidence ({conf:.2f}); please check this clip's alignment")

    return PairSync(
        offset_at_zero=offset0,
        slope=slope,
        confidence=conf,
        sample_rate=sr,
        overlap_s=round(overlap_s, 3),
        windows_used=len(fit.inliers) if fit else 0,
        windows_total=sum(m.offset is not None for m in windows),
        warnings=tuple(warnings),
        measurements=tuple(windows),
    )


# ------------------------------------------------------------------ report
class ClipSyncReport(StrictModel):
    file: str
    is_reference: bool
    offset_samples: int = Field(description="At sample_rate; project sign convention")
    sample_rate: int = Field(gt=0)
    drift_ppm: float
    confidence: float = Field(ge=0.0, le=1.0)
    overlap_s: float = Field(ge=0.0)
    windows_used: int = Field(ge=0)
    windows_total: int = Field(ge=0)
    warnings: list[str] = Field(default_factory=list)

    @property
    def offset_seconds(self) -> float:
        return self.offset_samples / self.sample_rate

    def to_sync_result(self, reference_clip_id: UUID) -> SyncResult:
        return SyncResult(
            reference_clip_id=reference_clip_id,
            offset_samples=self.offset_samples,
            sample_rate=self.sample_rate,
            drift_ppm=self.drift_ppm,
            confidence=self.confidence,
        )


class SyncReport(StrictModel):
    """Output of ``multicam sync`` (sync.json)."""

    schema_version: Literal[1] = 1
    engine_version: str = __version__
    analysis_sample_rate: int = Field(gt=0)
    reference_file: str
    clips: list[ClipSyncReport] = Field(min_length=1)

    def clip(self, file: str) -> ClipSyncReport:
        for c in self.clips:
            if c.file == file or Path(c.file).name == file:
                return c
        raise KeyError(file)

    @property
    def has_warnings(self) -> bool:
        return any(c.warnings for c in self.clips)


def _clip_report(path: Path, pair: PairSync) -> ClipSyncReport:
    return ClipSyncReport(
        file=str(path),
        is_reference=False,
        offset_samples=round(pair.offset_at_zero * REPORT_SAMPLE_RATE / pair.sample_rate),
        sample_rate=REPORT_SAMPLE_RATE,
        drift_ppm=round(pair.drift_ppm, 3),
        confidence=pair.confidence,
        overlap_s=pair.overlap_s,
        windows_used=pair.windows_used,
        windows_total=pair.windows_total,
        warnings=list(pair.warnings),
    )


def sync_files(
    paths: Sequence[str | Path],
    *,
    reference: str | Path | None = None,
    sample_rate: int = SYNC_SAMPLE_RATE,
    cache_dir: Path | None = None,
    params: SyncParams | None = None,
    on_progress: Callable[[str], None] | None = None,
) -> SyncReport:
    """Sync media files against a reference (default: the first file).

    Missing files raise ``FileNotFoundError``; clips without usable audio are
    reported with a warning and zero confidence.
    """
    files = [Path(p) for p in paths]
    if len(files) < 2:
        raise ValueError("need at least two clips to sync")
    for f in files:
        if not f.is_file():
            raise FileNotFoundError(f)
    ref_path = Path(reference) if reference is not None else files[0]
    if not ref_path.is_file():
        raise FileNotFoundError(ref_path)
    same = ref_path.resolve()
    files = [f for f in files if f.resolve() != same]  # reference is handled separately
    notify = on_progress or (lambda _msg: None)

    notify(f"decoding audio: {ref_path.name}")
    ref_audio: FloatArray | None
    ref_problem: str | None = None
    try:
        ref_audio = load_audio(ref_path, sample_rate, cache_dir)
    except NoAudioError:
        ref_audio, ref_problem = None, "reference clip has no audio; pick another reference"

    reports: list[ClipSyncReport] = [
        ClipSyncReport(
            file=str(ref_path),
            is_reference=True,
            offset_samples=0,
            sample_rate=REPORT_SAMPLE_RATE,
            drift_ppm=0.0,
            confidence=0.0 if ref_problem else 1.0,
            overlap_s=round(len(ref_audio) / sample_rate, 3) if ref_audio is not None else 0.0,
            windows_used=0,
            windows_total=0,
            warnings=[ref_problem] if ref_problem else [],
        )
    ]
    for path in files:
        if ref_audio is None:
            pair = _failed(sample_rate, "cannot sync: reference clip has no audio")
        else:
            notify(f"decoding audio: {path.name}")
            try:
                clip_audio = load_audio(path, sample_rate, cache_dir)
            except NoAudioError:
                pair = _failed(sample_rate, "clip has no audio stream; align it manually")
            else:
                notify(f"syncing: {path.name}")
                pair = sync_signals(ref_audio, clip_audio, sample_rate, params)
        reports.append(_clip_report(path, pair))

    return SyncReport(analysis_sample_rate=sample_rate, reference_file=str(ref_path), clips=reports)
