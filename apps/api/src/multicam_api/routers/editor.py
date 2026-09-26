"""What the timeline editor needs: clip timing, waveforms, preview proxies,
and export of the edit to editing software (FCPXML, Premiere XML, EDL)."""

from __future__ import annotations

import re
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from sqlalchemy import select

from multicam_api.db.models import CutListRow, ExportRow
from multicam_api.routers._common import (
    UNPROCESSABLE,
    SessionDep,
    StateDep,
    clip_or_404,
    not_found,
    project_or_404,
)
from multicam_api.schemas import (
    NleExportIn,
    NleExportOut,
    TimelineClip,
    TimelineOut,
    WaveformOut,
)
from multicam_api.services import media
from multicam_api.services.projects import latest_cutlist, project_to_engine
from multicam_api.views import export_out
from multicam_engine.export import EXTENSIONS, build_nle_timeline, write_nle
from multicam_engine.media.probe import ProbeError
from multicam_engine.models import CutList, OutputSettings

router = APIRouter(prefix="/api", tags=["editor"])


@router.get("/projects/{project_id}/timeline", response_model=TimelineOut)
async def timeline(project_id: UUID, session: SessionDep, state: StateDep) -> TimelineOut:
    """How every clip maps onto the timeline (for the players and waveforms)."""
    row = project_or_404(session, project_id)
    proxies = state.storage.proxies_dir(project_id)
    clips: list[TimelineClip] = []
    for clip in row.clips:
        try:
            result = await run_in_threadpool(media.probe_cached, clip.path)
        except (FileNotFoundError, ProbeError):
            continue  # missing files show up in the clip list; nothing to play here
        speed, media_offset, audio_offset = media.timeline_mapping(clip, result)
        clips.append(
            TimelineClip(
                clip_id=UUID(clip.id),
                speed=float(speed),
                media_offset_s=float(media_offset),
                audio_offset_s=float(audio_offset),
                duration_s=float(result.duration),
                fps=result.media.fps,
                has_audio=result.audio_stream_index is not None,
                has_proxy=media.existing_proxy(clip, proxies) is not None,
            )
        )
    latest = latest_cutlist(session, row.id)
    return TimelineOut(
        fps=OutputSettings.model_validate(row.output).fps,
        duration_frames=CutList.model_validate(latest.data).duration_frames if latest else None,
        clips=clips,
        proxies_ready=bool(clips) and all(c.has_proxy for c in clips),
    )


@router.get("/clips/{clip_id}/waveform", response_model=WaveformOut)
async def clip_waveform(
    clip_id: UUID,
    session: SessionDep,
    state: StateDep,
    rate: int = Query(default=50, ge=1, le=400),
) -> WaveformOut:
    """Peak levels of the clip's own audio (sample 0 = start of its audio)."""
    clip = clip_or_404(session, clip_id)
    if not Path(clip.path).is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"file not found: {clip.path}")
    try:
        data = await run_in_threadpool(
            media.waveform, clip.path, state.settings.audio_cache_dir, rate
        )
    except Exception as exc:  # no audio stream, unreadable file
        raise HTTPException(
            UNPROCESSABLE, f"no waveform for {Path(clip.path).name}: {exc}"
        ) from exc
    return WaveformOut(clip_id=clip_id, rate=rate, peaks=media.encode_peaks(data))


@router.get("/clips/{clip_id}/proxy", response_class=FileResponse)
def clip_proxy(clip_id: UUID, session: SessionDep, state: StateDep) -> FileResponse:
    """The clip's preview copy (seekable; created by a `proxy` job)."""
    clip = clip_or_404(session, clip_id)
    path = media.existing_proxy(clip, state.storage.proxies_dir(UUID(clip.project_id)))
    if path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no preview yet: start a proxy job")
    return FileResponse(path, media_type="video/mp4")


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", text).strip("-") or "episode"


@router.post(
    "/projects/{project_id}/nle-exports",
    response_model=NleExportOut,
    status_code=status.HTTP_201_CREATED,
)
def export_timeline(
    project_id: UUID, body: NleExportIn, session: SessionDep, state: StateDep
) -> NleExportOut:
    """Write the edit for Final Cut / Resolve (FCPXML), Premiere (XML) or any NLE (EDL)."""
    row = project_or_404(session, project_id)
    if body.version is None:
        cut_row = latest_cutlist(session, row.id)
    else:
        cut_row = session.scalars(
            select(CutListRow).where(
                CutListRow.project_id == row.id, CutListRow.version == body.version
            )
        ).first()
    if cut_row is None:
        raise not_found("cutlist for project", project_id)
    project = project_to_engine(row)
    cutlist = CutList.model_validate(cut_row.data)
    probes = {}
    for clip in row.clips:
        try:
            probes[UUID(clip.id)] = media.probe_cached(clip.path)
        except (FileNotFoundError, ProbeError):
            continue
    try:
        timeline = build_nle_timeline(project, cutlist, probes, name=row.name)
    except ValueError as exc:
        raise HTTPException(UNPROCESSABLE, f"{exc}. Relink missing files and try again.") from exc
    text = write_nle(timeline, body.format)
    name = f"{_slug(row.name)}-v{cut_row.version}{EXTENSIONS[body.format]}"
    out = (
        Path(body.output_path) if body.output_path else state.storage.exports_dir(project_id) / name
    )
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
    except OSError as exc:
        raise HTTPException(UNPROCESSABLE, f"cannot write {out}: {exc}") from exc
    export = ExportRow(
        id=str(uuid4()),
        project_id=row.id,
        job_id=None,
        kind=body.format.value,
        path=str(out),
        preset=None,
        input_hash=None,
        frames=cutlist.duration_frames,
    )
    session.add(export)
    session.commit()
    return NleExportOut(export=export_out(export), warnings=timeline.warnings)
