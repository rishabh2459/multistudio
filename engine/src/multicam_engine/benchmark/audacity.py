"""Build ground truth from an Audacity label export.

Label conventions (see docs/TEST_FOOTAGE.md):

* ``clap_start@<file>`` — point label at the start clap, in that clip's own track
* ``clap_end@<file>``   — point label at the end clap (enables drift measurement)
* ``annotated_range``   — region label: the window where speech is fully labeled
* ``<speaker_label>``   — region label on the reference track: that person speaking

Audacity writes ``start<TAB>end<TAB>text`` with seconds as decimals. We parse
with ``Decimal`` (never float) and round half-up to integer milliseconds.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path

from pydantic import Field, ValidationError

from multicam_engine.benchmark.ground_truth import GroundTruth, GTClip, MsRange, SpeechTurn
from multicam_engine.models._base import StrictModel
from multicam_engine.models.project import ClipRole

META_FILE = "meta.json"
LABELS_FILE = "labels.txt"
GROUND_TRUTH_FILE = "ground_truth.json"


class GroundTruthBuildError(ValueError):
    """Raised with a human-readable message pointing at the problem."""


class MetaClip(StrictModel):
    file: str = Field(min_length=1)
    role: ClipRole = ClipRole.SPEAKER
    speaker_label: str | None = None


class RecordingMeta(StrictModel):
    """Hand-written ``meta.json`` in each recording folder."""

    recording_id: str = Field(pattern=r"^T\d+$")
    description: str = ""
    reference_file: str
    clips: list[MetaClip] = Field(min_length=2)


def _seconds_to_ms(text: str, line_no: int) -> int:
    try:
        value = Decimal(text.strip())
    except InvalidOperation as exc:
        raise GroundTruthBuildError(f"line {line_no}: invalid time {text!r}") from exc
    if not value.is_finite() or value < 0:
        raise GroundTruthBuildError(f"line {line_no}: invalid time {text!r}")
    return int((value * 1000).to_integral_value(rounding=ROUND_HALF_UP))


def build_ground_truth(meta: RecordingMeta, labels_text: str) -> GroundTruth:
    files = {c.file for c in meta.clips}
    speaker_labels = {c.speaker_label for c in meta.clips if c.speaker_label}
    clap_start: dict[str, int] = {}
    clap_end: dict[str, int] = {}
    speech: list[SpeechTurn] = []
    annotated: MsRange | None = None

    for line_no, raw in enumerate(labels_text.splitlines(), start=1):
        if not raw.strip() or raw.startswith("\\"):  # blank / spectral-selection lines
            continue
        parts = raw.split("\t")
        if len(parts) != 3:
            raise GroundTruthBuildError(
                f"line {line_no}: expected 'start<TAB>end<TAB>label', got {raw!r}"
            )
        start = _seconds_to_ms(parts[0], line_no)
        end = _seconds_to_ms(parts[1], line_no)
        label = parts[2].strip()
        if not label:
            raise GroundTruthBuildError(f"line {line_no}: empty label")

        if "@" in label:
            kind, _, file = label.partition("@")
            if kind not in ("clap_start", "clap_end"):
                raise GroundTruthBuildError(f"line {line_no}: unknown marker {kind!r}")
            if file not in files:
                raise GroundTruthBuildError(
                    f"line {line_no}: {file!r} is not listed in {META_FILE} "
                    f"(known: {sorted(files)})"
                )
            target = clap_start if kind == "clap_start" else clap_end
            if file in target:
                raise GroundTruthBuildError(f"line {line_no}: duplicate {kind} for {file}")
            target[file] = start
        elif label == "annotated_range":
            if annotated is not None:
                raise GroundTruthBuildError(f"line {line_no}: duplicate annotated_range")
            if end <= start:
                raise GroundTruthBuildError(f"line {line_no}: annotated_range must be a region")
            annotated = MsRange(start_ms=start, end_ms=end)
        elif label in speaker_labels:
            if end <= start:
                raise GroundTruthBuildError(
                    f"line {line_no}: speech label {label!r} must be a region, not a point"
                )
            speech.append(SpeechTurn(speaker_label=label, start_ms=start, end_ms=end))
        else:
            raise GroundTruthBuildError(
                f"line {line_no}: unknown label {label!r}. Expected clap_start@<file>, "
                f"clap_end@<file>, annotated_range, or a speaker: {sorted(speaker_labels)}"
            )

    missing = sorted(files - clap_start.keys())
    if missing:
        raise GroundTruthBuildError(f"missing clap_start label for: {missing}")

    speech.sort(key=lambda t: (t.start_ms, t.speaker_label))
    try:
        return GroundTruth(
            recording_id=meta.recording_id,
            description=meta.description,
            reference_file=meta.reference_file,
            clips=[
                GTClip(
                    file=c.file,
                    role=c.role,
                    speaker_label=c.speaker_label,
                    clap_start_ms=clap_start[c.file],
                    clap_end_ms=clap_end.get(c.file),
                )
                for c in meta.clips
            ],
            speech=speech,
            annotated_range=annotated,
        )
    except ValidationError as exc:
        raise GroundTruthBuildError(str(exc)) from exc


def build_from_folder(recording_dir: Path) -> GroundTruth:
    meta_path = recording_dir / META_FILE
    labels_path = recording_dir / LABELS_FILE
    for p in (meta_path, labels_path):
        if not p.is_file():
            raise GroundTruthBuildError(f"not found: {p}")
    try:
        meta = RecordingMeta.model_validate_json(meta_path.read_text(encoding="utf-8"))
    except ValidationError as exc:
        raise GroundTruthBuildError(f"{meta_path}: {exc}") from exc
    return build_ground_truth(meta, labels_path.read_text(encoding="utf-8"))
