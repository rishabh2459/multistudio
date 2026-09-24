from uuid import UUID

import pytest

from multicam_engine.benchmark.ground_truth import GroundTruth, GTClip, MsRange, SpeechTurn
from multicam_engine.benchmark.switch_accuracy import score_switching
from multicam_engine.models import Clip, ClipRole, CutList, OutputSettings, Project, Segment
from multicam_engine.models.time import FPS_25


def _setup() -> tuple[GroundTruth, Project, dict[str, UUID]]:
    host = Clip(path="/f/cam1.mp4", speaker_label="Host")
    guest = Clip(path="/f/cam2.mp4", speaker_label="Guest")
    wide = Clip(path="/f/wide.mp4", role=ClipRole.WIDE)
    project = Project(
        name="t",
        output=OutputSettings(fps=FPS_25, width=1920, height=1080),
        clips=[host, guest, wide],
    )
    gt = GroundTruth(
        recording_id="T1",
        reference_file="cam1.mp4",
        clips=[
            GTClip(file="cam1.mp4", speaker_label="Host", clap_start_ms=0),
            GTClip(file="cam2.mp4", speaker_label="Guest", clap_start_ms=0),
            GTClip(file="wide.mp4", role=ClipRole.WIDE, clap_start_ms=0),
        ],
        speech=[
            SpeechTurn(speaker_label="Host", start_ms=0, end_ms=4000),
            SpeechTurn(speaker_label="Guest", start_ms=4000, end_ms=8000),
            SpeechTurn(speaker_label="Host", start_ms=7000, end_ms=8000),  # overlap
        ],
    )
    return gt, project, {"host": host.id, "guest": guest.id, "wide": wide.id}


def _cutlist(project: Project, parts: list[tuple[UUID, int]]) -> CutList:
    segs, start = [], 0
    for clip, frames in parts:
        segs.append(Segment(start_frame=start, end_frame=start + frames, clip_id=clip))
        start += frames
    return CutList(project_id=project.id, fps=FPS_25, segments=segs)


def test_perfect_edit() -> None:
    gt, project, ids = _setup()
    cl = _cutlist(
        project, [(ids["host"], 100), (ids["guest"], 75), (ids["wide"], 25), (ids["host"], 50)]
    )
    acc = score_switching(gt, cl, project, min_shot_s=0.5)
    assert acc.accuracy == 1.0
    assert acc.speech_s == pytest.approx(8.0)
    assert acc.wide_share == pytest.approx(1 / 8)
    assert acc.segments == 4 and acc.short_shots == 0
    assert acc.passed


def test_late_cut_and_short_shots_are_counted() -> None:
    gt, project, ids = _setup()
    # Cut to the guest 1 s late; a 0.4 s flash of the wide shot.
    cl = _cutlist(project, [(ids["host"], 125), (ids["wide"], 10), (ids["guest"], 115)])
    acc = score_switching(gt, cl, project, min_shot_s=1.0)
    # Wrong: 4.0-5.4 s (host/wide while guest speaks alone) = 1.4 s of 8 s.
    assert acc.accuracy == pytest.approx(1 - 1.4 / 8, abs=1e-3)
    assert acc.short_shots == 1
    assert not acc.passed


def test_annotated_range_limits_scoring() -> None:
    gt, project, ids = _setup()
    gt = gt.model_copy(update={"annotated_range": MsRange(start_ms=0, end_ms=4000)})
    cl = _cutlist(project, [(ids["host"], 250)])  # host the whole time
    assert score_switching(gt, cl, project, min_shot_s=1.0).accuracy == 1.0
