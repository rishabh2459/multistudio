from datetime import datetime

import pytest
from pydantic import ValidationError

from multicam_engine.models import Clip, OutputSettings, Project
from multicam_engine.models.time import FPS_25

from .factories import make_project, random_id


def test_valid_project_round_trips_through_json() -> None:
    project = make_project(3)
    assert Project.model_validate_json(project.model_dump_json()) == project


def test_duplicate_clip_ids_rejected() -> None:
    clip = Clip(path="/a.mp4")
    with pytest.raises(ValidationError, match="unique"):
        Project(
            name="x",
            output=OutputSettings(fps=FPS_25, width=1920, height=1080),
            clips=[clip, clip],
        )


def test_unknown_reference_clip_rejected() -> None:
    with pytest.raises(ValidationError, match="reference_clip_id"):
        Project(
            name="x",
            output=OutputSettings(fps=FPS_25, width=1920, height=1080),
            clips=[Clip(path="/a.mp4")],
            reference_clip_id=random_id(),
        )


@pytest.mark.parametrize(("w", "h"), [(1921, 1080), (1920, 1081)])
def test_odd_dimensions_rejected(w: int, h: int) -> None:
    with pytest.raises(ValidationError, match="even"):
        OutputSettings(fps=FPS_25, width=w, height=h)


def test_naive_datetime_rejected() -> None:
    with pytest.raises(ValidationError):
        Project(
            name="x",
            output=OutputSettings(fps=FPS_25, width=1920, height=1080),
            # Intentionally naive datetime: must be rejected.
            created_at=datetime(2026, 1, 1),  # noqa: DTZ001
        )


def test_unknown_fields_rejected() -> None:
    data = make_project().model_dump(mode="json")
    data["surprise"] = 1
    with pytest.raises(ValidationError, match="surprise"):
        Project.model_validate(data)


def test_clip_lookup() -> None:
    project = make_project()
    assert project.clip(project.clips[1].id) is project.clips[1]
    with pytest.raises(KeyError):
        project.clip(random_id())
