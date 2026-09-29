"""Editing presets: the built-in ones and the user's own (saved sliders).

A user preset is a named ``SwitchSettings``. Apply one to a project with
``PATCH /api/projects/{id}`` ``{"switch": <settings>}``. Share one as a
``.mcpreset.json`` file (``GET .../export``, ``POST /api/presets/import``).
"""

from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from multicam_api.db.models import UserPresetRow
from multicam_api.routers._common import SessionDep
from multicam_api.schemas import PresetFile, PresetOut, UserPresetIn
from multicam_engine.decide.presets import PRESETS, SwitchSettings

router = APIRouter(prefix="/api/presets", tags=["presets"])


def _user_out(row: UserPresetRow) -> PresetOut:
    return PresetOut(
        id=row.id,
        name=row.name,
        builtin=False,
        settings=SwitchSettings.model_validate(row.settings),
    )


def _user_or_404(session: SessionDep, preset_id: str) -> UserPresetRow:
    row = session.get(UserPresetRow, preset_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"preset {preset_id} not found")
    return row


@router.get("", response_model=list[PresetOut])
def list_presets(session: SessionDep) -> list[PresetOut]:
    builtin = [
        PresetOut(
            id=p.value, name=p.value.capitalize(), builtin=True,
            settings=SwitchSettings.from_params(v),
        )
        for p, v in PRESETS.items()
    ]  # fmt: skip
    rows = session.scalars(select(UserPresetRow).order_by(UserPresetRow.name)).all()
    return builtin + [_user_out(r) for r in rows]


@router.post("", response_model=PresetOut, status_code=status.HTTP_201_CREATED)
def create_preset(body: UserPresetIn, session: SessionDep) -> PresetOut:
    if body.name.strip().lower() in {p.value for p in PRESETS}:
        raise HTTPException(status.HTTP_409_CONFLICT, "that name belongs to a built-in preset")
    row = UserPresetRow(
        id=str(uuid4()), name=body.name.strip(), settings=body.settings.model_dump(mode="json")
    )
    session.add(row)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "a preset with that name exists") from exc
    return _user_out(row)


@router.post("/import", response_model=PresetOut, status_code=status.HTTP_201_CREATED)
def import_preset(body: PresetFile, session: SessionDep) -> PresetOut:
    """Import a ``.mcpreset.json``. A name clash gets " (2)", " (3)" ... appended."""
    taken = set(session.scalars(select(UserPresetRow.name)).all()) | {p.value for p in PRESETS}
    name, n = body.name.strip(), 2
    while name.lower() in {t.lower() for t in taken}:
        name = f"{body.name.strip()[:54]} ({n})"
        n += 1
    return create_preset(UserPresetIn(name=name, settings=body.settings), session)


@router.get("/{preset_id}/export", response_model=PresetFile)
def export_preset(preset_id: str, session: SessionDep) -> PresetFile:
    """The ``.mcpreset.json`` contents of a built-in or user preset."""
    for p, v in PRESETS.items():
        if p.value == preset_id:
            return PresetFile(name=p.value, settings=SwitchSettings.from_params(v))
    row = _user_or_404(session, preset_id)
    return PresetFile(name=row.name, settings=SwitchSettings.model_validate(row.settings))


@router.delete("/{preset_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_preset(preset_id: str, session: SessionDep) -> Response:
    if preset_id in {p.value for p in PRESETS}:
        raise HTTPException(status.HTTP_409_CONFLICT, "built-in presets cannot be deleted")
    session.delete(_user_or_404(session, preset_id))
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
