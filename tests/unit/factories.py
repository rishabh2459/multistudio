"""Small builders for valid test objects."""

from uuid import UUID, uuid4

from multicam_engine.models import (
    Clip,
    ClipRole,
    CutList,
    OutputSettings,
    Project,
    Segment,
)
from multicam_engine.models.time import FPS_29_97


def make_project(n_clips: int = 2) -> Project:
    clips = [
        Clip(path=f"/footage/cam{i + 1}.mp4", role=ClipRole.SPEAKER, speaker_label=f"P{i + 1}")
        for i in range(n_clips)
    ]
    return Project(
        name="Test episode",
        output=OutputSettings(fps=FPS_29_97, width=1920, height=1080),
        clips=clips,
        reference_clip_id=clips[0].id,
    )


def make_cutlist(
    project: Project, bounds: list[int], clip_ids: list[UUID] | None = None
) -> CutList:
    """bounds=[0, 100, 250] -> segments [0,100) and [100,250)."""
    ids = clip_ids or [project.clips[i % len(project.clips)].id for i in range(len(bounds) - 1)]
    segments = [
        Segment(start_frame=a, end_frame=b, clip_id=cid)
        for a, b, cid in zip(bounds[:-1], bounds[1:], ids, strict=True)
    ]
    return CutList(project_id=project.id, fps=project.output.fps, segments=segments)


def random_id() -> UUID:
    return uuid4()
