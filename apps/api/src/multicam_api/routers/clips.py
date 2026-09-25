"""Clips: add a camera file (probed immediately), update roles, relink, remove."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Response, status

from multicam_api.db.models import ClipRow
from multicam_api.routers._common import (
    UNPROCESSABLE,
    SessionDep,
    clip_or_404,
    project_or_404,
)
from multicam_api.schemas import ClipCreate, ClipOut, ClipUpdate
from multicam_api.services.projects import file_stat, follow_reference
from multicam_api.views import clip_out
from multicam_engine.media.ffmpeg import FFmpegNotFoundError
from multicam_engine.media.probe import ProbeError, probe
from multicam_engine.models.project import ClipRole, MediaInfo

router = APIRouter(prefix="/api", tags=["clips"])

RELINK_DURATION_TOLERANCE_S = 1.0


def _probe(path: Path) -> MediaInfo:
    try:
        return probe(path).media
    except ProbeError as exc:
        raise HTTPException(UNPROCESSABLE, str(exc)) from exc
    except FFmpegNotFoundError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc


def _resolve(path_text: str) -> Path:
    path = Path(path_text).expanduser()
    if not path.is_absolute():
        raise HTTPException(UNPROCESSABLE, "path must be absolute")
    if not path.is_file():
        raise HTTPException(UNPROCESSABLE, f"file not found: {path}")
    return path


@router.get("/projects/{project_id}/clips", response_model=list[ClipOut])
def list_clips(project_id: UUID, session: SessionDep) -> list[ClipOut]:
    project = project_or_404(session, project_id)
    return [clip_out(c, project.reference_clip_id) for c in project.clips]


@router.post(
    "/projects/{project_id}/clips", response_model=ClipOut, status_code=status.HTTP_201_CREATED
)
def add_clip(project_id: UUID, body: ClipCreate, session: SessionDep) -> ClipOut:
    project = project_or_404(session, project_id)
    path = _resolve(body.path)
    if any(Path(c.path) == path for c in project.clips):
        raise HTTPException(status.HTTP_409_CONFLICT, f"{path.name} is already in this project")
    media = _probe(path)
    stat = file_stat(str(path))
    label = body.speaker_label
    if body.role is ClipRole.SPEAKER and not label:
        label = path.stem
    row = ClipRow(
        id=str(uuid4()),
        project_id=project.id,
        position=max((c.position for c in project.clips), default=-1) + 1,
        path=str(path),
        role=body.role.value,
        speaker_label=label if body.role is ClipRole.SPEAKER else None,
        media=media.model_dump(mode="json"),
        file_size=stat[0] if stat else None,
        file_mtime_ns=stat[1] if stat else None,
    )
    project.clips.append(row)
    if project.reference_clip_id is None:
        project.reference_clip_id = row.id
    follow_reference(project)
    session.commit()
    return clip_out(row, project.reference_clip_id)


@router.get("/clips/{clip_id}", response_model=ClipOut)
def get_clip(clip_id: UUID, session: SessionDep) -> ClipOut:
    row = clip_or_404(session, clip_id)
    return clip_out(row, row.project.reference_clip_id)


@router.patch("/clips/{clip_id}", response_model=ClipOut)
def update_clip(clip_id: UUID, body: ClipUpdate, session: SessionDep) -> ClipOut:
    row = clip_or_404(session, clip_id)
    project = row.project
    if body.role is not None:
        row.role = body.role.value
        if body.role is not ClipRole.SPEAKER:
            row.speaker_label = None
        elif not row.speaker_label:
            row.speaker_label = Path(row.path).stem
    if body.speaker_label is not None:
        if ClipRole(row.role) is not ClipRole.SPEAKER:
            raise HTTPException(UNPROCESSABLE, "only speaker cameras have a speaker label")
        row.speaker_label = body.speaker_label
    if body.path is not None:
        path = _resolve(body.path)
        media = _probe(path)
        if row.media and not body.force:
            old = MediaInfo.model_validate(row.media)
            old_s = old.duration_frames / float(old.fps.to_fraction())
            new_s = media.duration_frames / float(media.fps.to_fraction())
            if abs(old_s - new_s) > RELINK_DURATION_TOLERANCE_S:
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    f"{path.name} is {new_s:.1f} s long but the original was {old_s:.1f} s; "
                    "send force=true if this is really the same recording",
                )
        stat = file_stat(str(path))
        same_file = stat is not None and stat[0] == row.file_size
        row.path, row.media = str(path), media.model_dump(mode="json")
        row.file_size, row.file_mtime_ns = (stat[0], stat[1]) if stat else (None, None)
        if not same_file:  # different content: its sync (or everyone's) must be redone
            if row.id == project.reference_clip_id:
                for clip in project.clips:
                    clip.sync = None
            row.sync = None
        follow_reference(project)
    session.commit()
    return clip_out(row, project.reference_clip_id)


@router.delete("/clips/{clip_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_clip(clip_id: UUID, session: SessionDep) -> Response:
    row = clip_or_404(session, clip_id)
    project = row.project
    project.clips.remove(row)
    if project.reference_clip_id == row.id:
        project.reference_clip_id = project.clips[0].id if project.clips else None
        for clip in project.clips:
            clip.sync = None
        follow_reference(project)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
