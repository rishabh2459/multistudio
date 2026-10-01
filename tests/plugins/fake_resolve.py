"""A fake DaVinci Resolve scripting API (the calls the Resolve script uses)."""

from __future__ import annotations

from pathlib import Path
from typing import Any


class MediaPoolItem:
    def __init__(self, path: str, kind: str = "Video + Audio") -> None:
        self.path, self.kind = path, kind

    def GetClipProperty(self, key: str) -> Any:  # noqa: N802
        return {"File Path": self.path, "Type": self.kind}.get(key)

    def GetUniqueId(self) -> str:  # noqa: N802
        return "mpi:" + Path(self.path).name


class TimelineItem:
    def __init__(self, mpi: MediaPoolItem, start: int, duration: int, left: int = 0) -> None:
        self.mpi, self.start, self.duration, self.left = mpi, start, duration, left
        self.enabled = True
        self.info: dict[str, Any] = {}

    def GetMediaPoolItem(self) -> MediaPoolItem:  # noqa: N802
        return self.mpi

    def GetStart(self) -> int:  # noqa: N802
        return self.start

    def GetDuration(self) -> int:  # noqa: N802
        return self.duration

    def GetLeftOffset(self) -> int:  # noqa: N802
        return self.left

    def SetClipEnabled(self, on: bool) -> bool:  # noqa: N802
        self.enabled = on
        return True


class Timeline:
    def __init__(self, name: str, fps: str = "29.97", start_frame: int = 107892) -> None:
        self.name, self.fps, self.start_frame = name, fps, start_frame
        self.tracks: dict[str, list[list[TimelineItem]]] = {"video": [[]], "audio": [[]]}
        self.markers: list[tuple[Any, ...]] = []

    def GetName(self) -> str:  # noqa: N802
        return self.name

    def GetUniqueId(self) -> str:  # noqa: N802
        return "tl:" + self.name

    def GetSetting(self, key: str) -> Any:  # noqa: N802
        return self.fps if key == "timelineFrameRate" else None

    def GetStartFrame(self) -> int:  # noqa: N802
        return self.start_frame

    def GetTrackCount(self, kind: str) -> int:  # noqa: N802
        return len(self.tracks[kind])

    def GetItemListInTrack(self, kind: str, index: int) -> list[TimelineItem]:  # noqa: N802
        return self.tracks[kind][index - 1]

    def AddTrack(self, kind: str, sub: str | None = None) -> bool:  # noqa: N802
        self.tracks[kind].append([])
        return True

    def AddMarker(  # noqa: N802
        self, frame: int, color: str, name: str, note: str, duration: int, data: str
    ) -> bool:
        self.markers.append((frame, color, name, note, duration))
        return True

    def put(self, kind: str, track: int, item: TimelineItem) -> None:
        while len(self.tracks[kind]) < track:
            self.tracks[kind].append([])
        self.tracks[kind][track - 1].append(item)


class Folder:
    def __init__(self, clips: list[MediaPoolItem], subs: list[Folder] | None = None) -> None:
        self.clips, self.subs = clips, subs or []

    def GetClipList(self) -> list[MediaPoolItem]:  # noqa: N802
        return self.clips

    def GetSubFolderList(self) -> list[Folder]:  # noqa: N802
        return self.subs


class MediaPool:
    def __init__(self, project: Project) -> None:
        self.project = project
        self.root = Folder([], [Folder([])])
        self.appends: list[list[dict[str, Any]]] = []
        self.imported_xml: list[str] = []

    def GetRootFolder(self) -> Folder:  # noqa: N802
        return self.root

    def ImportMedia(self, paths: list[str]) -> list[MediaPoolItem]:  # noqa: N802
        new = [MediaPoolItem(p) for p in paths]
        self.root.subs[0].clips.extend(new)
        return new

    def CreateEmptyTimeline(self, name: str) -> Timeline | None:  # noqa: N802
        if any(t.name == name for t in self.project.timelines):
            return None
        tl = Timeline(name)
        self.project.timelines.append(tl)
        return tl

    def AppendToTimeline(self, infos: list[dict[str, Any]]) -> list[TimelineItem]:  # noqa: N802
        self.appends.append(infos)
        tl = self.project.current
        assert tl is not None
        out = []
        for info in infos:
            kind = "video" if info["mediaType"] == 1 else "audio"
            assert info["trackIndex"] <= tl.GetTrackCount(kind), "track does not exist"
            item = TimelineItem(
                info["mediaPoolItem"],
                info["recordFrame"],
                info["endFrame"] - info["startFrame"] + 1,
                info["startFrame"],
            )
            item.info = info
            tl.put(kind, info["trackIndex"], item)
            out.append(item)
        return out

    def ImportTimelineFromFile(self, path: str, options: dict[str, Any]) -> Timeline | None:  # noqa: N802
        self.imported_xml.append(path)
        tl = Timeline(options["timelineName"])
        self.project.timelines.append(tl)
        return tl


class Project:
    def __init__(self) -> None:
        self.timelines: list[Timeline] = []
        self.current: Timeline | None = None
        self.pool = MediaPool(self)

    def GetMediaPool(self) -> MediaPool:  # noqa: N802
        return self.pool

    def GetCurrentTimeline(self) -> Timeline | None:  # noqa: N802
        return self.current

    def SetCurrentTimeline(self, tl: Timeline) -> bool:  # noqa: N802
        self.current = tl
        return True

    def GetSetting(self, key: str) -> Any:  # noqa: N802
        return {
            "timelineResolutionWidth": "1280",
            "timelineResolutionHeight": "720",
            "timelineFrameRate": "29.97",
        }.get(key)


class Resolve:
    def __init__(self, project: Project | None) -> None:
        self.project = project

    def GetProjectManager(self) -> Any:  # noqa: N802
        project = self.project

        class Manager:
            def GetCurrentProject(self) -> Project | None:  # noqa: N802
                return project

        return Manager()

    def GetVersionString(self) -> str:  # noqa: N802
        return "20.1.0"


def podcast(
    cam1: str, cam2: str, wide: str, mic: str | None = None, synced: bool = True
) -> Resolve:
    """A project whose open timeline has three cameras (and a mic file)."""
    project = Project()
    tl = Timeline("Ep 42")
    project.timelines.append(tl)
    project.current = tl
    s = tl.start_frame
    items = [MediaPoolItem(p) for p in (cam1, cam2, wide)]
    tl.put("video", 1, TimelineItem(items[0], s, 900))
    tl.put("video", 2, TimelineItem(items[1], s, 900, left=30 if synced else 0))
    tl.put("video", 3, TimelineItem(items[2], s + (15 if synced else 0), 900))
    tl.put("audio", 1, TimelineItem(items[0], s, 900))  # camera audio: not a mic
    if mic:
        m = MediaPoolItem(mic, "Audio")
        items.append(m)
        tl.put("audio", 4, TimelineItem(m, s, 900))
    project.pool.root.subs[0].clips.extend(items)
    return Resolve(project)
