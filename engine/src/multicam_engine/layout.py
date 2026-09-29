"""People and cameras of a project: who is recorded by which mic, who is in which shot.

A project can state this explicitly (``Project.speakers`` / ``Project.cameras``),
for any layout: solo, two-shot, three-shot, four-shot, wide, several angles on
one person. Older projects only have clip roles; they get the layout those roles
imply (every SPEAKER clip is a solo camera + that person's mic, every WIDE clip
shows everyone), so switching behaves exactly as before for them.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import NAMESPACE_URL, UUID, uuid5

from multicam_engine.models.project import (
    CameraLayout,
    ClipRole,
    Project,
    ShotType,
    Speaker,
)


class LayoutError(ValueError):
    """The layout cannot be used for auto-editing (message is for the user)."""


def derived_speaker_id(clip_id: UUID) -> UUID:
    """Stable id for the person recorded by a SPEAKER clip (role-derived layouts)."""
    return uuid5(NAMESPACE_URL, f"multicam:speaker:{clip_id}")


@dataclass(frozen=True)
class ResolvedLayout:
    speakers: list[Speaker]
    #: Cameras auto-edit may choose (B-roll left out), in project clip order.
    cameras: list[CameraLayout]
    #: Layouts of every clip, B-roll included.
    all_cameras: list[CameraLayout]
    custom: bool

    def speaker_index(self) -> dict[UUID, int]:
        return {s.id: i for i, s in enumerate(self.speakers)}

    @property
    def mic_keys(self) -> list[tuple[UUID, int | None]]:
        """(clip, channel) of each speaker's mic, in speaker order."""
        out: list[tuple[UUID, int | None]] = []
        for s in self.speakers:
            if s.mic_clip_id is None:
                raise LayoutError(
                    f"{s.name} has no microphone. Pick the clip that records them "
                    "(single-mic editing is not available yet)."
                )
            out.append((s.mic_clip_id, s.mic_channel))
        return out


def role_layout(project: Project) -> tuple[list[Speaker], list[CameraLayout]]:
    """The layout implied by clip roles (the pre-layout model)."""
    speakers = [
        Speaker(
            id=derived_speaker_id(c.id),
            name=c.speaker_label or _stem(c.path),
            mic_clip_id=c.id,
        )
        for c in project.clips
        if c.role is ClipRole.SPEAKER
    ]
    everyone = [s.id for s in speakers]
    cameras: list[CameraLayout] = []
    for c in project.clips:
        if c.role is ClipRole.SPEAKER:
            cameras.append(
                CameraLayout(clip_id=c.id, shot=ShotType.SOLO, covers=[derived_speaker_id(c.id)])
            )
        elif c.role is ClipRole.WIDE:
            cameras.append(CameraLayout(clip_id=c.id, shot=ShotType.WIDE, covers=everyone))
        else:
            cameras.append(CameraLayout(clip_id=c.id, shot=ShotType.BROLL, covers=[]))
    return speakers, cameras


def resolve_layout(project: Project) -> ResolvedLayout:
    """The project's layout (explicit, else derived from roles), checked for use."""
    custom = bool(project.speakers)
    if custom:
        speakers = list(project.speakers)
        by_clip = {c.clip_id: c for c in project.cameras}
        # Clips without a layout: B-roll (never auto-selected) until the user says otherwise.
        all_cameras = [
            by_clip.get(c.id, CameraLayout(clip_id=c.id, shot=ShotType.BROLL, covers=[]))
            for c in project.clips
        ]
    else:
        speakers, all_cameras = role_layout(project)
    cameras = [c for c in all_cameras if c.shot is not ShotType.BROLL]
    if not speakers:
        raise LayoutError("project has no speakers: mark who is talking on which clip")
    if not cameras:
        raise LayoutError("project has no cameras to switch between (all clips are B-roll)")
    return ResolvedLayout(speakers, cameras, all_cameras, custom)


def _stem(path: str) -> str:
    name = path.replace("\\", "/").rsplit("/", 1)[-1]
    return name.rsplit(".", 1)[0] or name
