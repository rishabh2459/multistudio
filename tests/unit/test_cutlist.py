import pytest
from pydantic import ValidationError

from multicam_engine.models import AudioConfig, AudioMode, CutList, Removal, RemovalKind, Segment
from multicam_engine.models.time import FPS_25

from .factories import make_cutlist, make_project, random_id


def test_valid_cutlist() -> None:
    project = make_project()
    cl = make_cutlist(project, [0, 100, 250, 400])
    assert cl.duration_frames == 400
    cl.check_against(project)
    assert CutList.model_validate_json(cl.model_dump_json()) == cl


def test_segment_end_must_be_after_start() -> None:
    with pytest.raises(ValidationError, match="end_frame"):
        Segment(start_frame=10, end_frame=10, clip_id=random_id())


def test_gap_rejected() -> None:
    project = make_project()
    ids = [c.id for c in project.clips]
    with pytest.raises(ValidationError, match="gap"):
        CutList(
            project_id=project.id,
            fps=project.output.fps,
            segments=[
                Segment(start_frame=0, end_frame=100, clip_id=ids[0]),
                Segment(start_frame=110, end_frame=200, clip_id=ids[1]),
            ],
        )


def test_overlap_rejected() -> None:
    project = make_project()
    ids = [c.id for c in project.clips]
    with pytest.raises(ValidationError, match="overlap"):
        CutList(
            project_id=project.id,
            fps=project.output.fps,
            segments=[
                Segment(start_frame=0, end_frame=100, clip_id=ids[0]),
                Segment(start_frame=90, end_frame=200, clip_id=ids[1]),
            ],
        )


def test_must_start_at_zero() -> None:
    project = make_project()
    with pytest.raises(ValidationError, match="expected 0"):
        CutList(
            project_id=project.id,
            fps=project.output.fps,
            segments=[Segment(start_frame=5, end_frame=100, clip_id=project.clips[0].id)],
        )


def test_empty_cutlist_rejected() -> None:
    with pytest.raises(ValidationError):
        CutList(project_id=random_id(), fps=FPS_25, segments=[])


def test_segment_at_uses_half_open_ranges() -> None:
    project = make_project()
    cl = make_cutlist(project, [0, 100, 250])
    assert cl.segment_at(0) is cl.segments[0]
    assert cl.segment_at(99) is cl.segments[0]
    assert cl.segment_at(100) is cl.segments[1]
    assert cl.segment_at(249) is cl.segments[1]
    with pytest.raises(IndexError):
        cl.segment_at(250)
    with pytest.raises(IndexError):
        cl.segment_at(-1)


def test_removals_must_not_overlap() -> None:
    project = make_project()
    cl = make_cutlist(project, [0, 300])
    with pytest.raises(ValidationError, match="removal 1"):
        cl.removals = [
            Removal(start_frame=10, end_frame=20, kind=RemovalKind.FILLER),
            Removal(start_frame=15, end_frame=30, kind=RemovalKind.SILENCE),
        ]


def test_removal_past_end_rejected() -> None:
    project = make_project()
    with pytest.raises(ValidationError, match="past end"):
        CutList(
            project_id=project.id,
            fps=project.output.fps,
            segments=[Segment(start_frame=0, end_frame=100, clip_id=project.clips[0].id)],
            removals=[Removal(start_frame=90, end_frame=120, kind=RemovalKind.FILLER)],
        )


def test_single_audio_mode_requires_clip() -> None:
    with pytest.raises(ValidationError, match="single_clip_id"):
        AudioConfig(mode=AudioMode.SINGLE)


def test_check_against_detects_unknown_clip() -> None:
    project = make_project()
    cl = make_cutlist(project, [0, 50, 100], clip_ids=[project.clips[0].id, random_id()])
    with pytest.raises(ValueError, match="unknown clip ids"):
        cl.check_against(project)


def test_check_against_detects_fps_mismatch() -> None:
    project = make_project()
    cl = make_cutlist(project, [0, 100])
    cl.fps = FPS_25
    with pytest.raises(ValueError, match="fps"):
        cl.check_against(project)


def test_check_against_detects_other_project() -> None:
    cl = make_cutlist(make_project(), [0, 100])
    with pytest.raises(ValueError, match="different project"):
        cl.check_against(make_project())
