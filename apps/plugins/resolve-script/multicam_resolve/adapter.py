"""DaVinci Resolve glue (PLUGIN_PLAN 8.3): read the current timeline, build the edit.

Uses the scripting API available to scripts run from Workspace -> Scripts, which
works in Resolve Free too (D72).
"""

from fractions import Fraction
from typing import Any, Dict, List, Optional

from .client import EngineError
from .plan import fps_fraction, looks_synced, parse_fps, placements

Json = Dict[str, Any]

#: Whether AppendToTimeline's endFrame is the last frame (True) or one past it.
#: Spike item (PL6): confirm in Resolve 19/20.
END_INCLUSIVE = True
MARKER_COLORS = {"red": "Red", "yellow": "Yellow", "green": "Green", "blue": "Blue"}
VIDEO, AUDIO = 1, 2


class ResolveAdapter:
    host = "resolve"

    def __init__(self, resolve: Any) -> None:
        if resolve is None:
            raise EngineError("host_error", "run this from DaVinci Resolve: Workspace > Scripts")
        self.resolve = resolve

    # ------------------------------------------------------------ helpers
    def project(self) -> Any:
        project = self.resolve.GetProjectManager().GetCurrentProject()
        if not project:
            raise EngineError("setup_required", "Open a Resolve project first.")
        return project

    def timeline(self) -> Any:
        tl = self.project().GetCurrentTimeline()
        if not tl:
            raise EngineError(
                "setup_required",
                "No timeline is open.",
                "Open the timeline with your camera clips, then press Connect.",
            )
        return tl

    def capabilities(self) -> Json:
        return {
            "multicam": False,
            "enable_disable": True,
            "keyframes": False,
            "markers": True,
            "xml_import": "fcpxml",
            "max_native_events": 1500,
        }

    # ------------------------------------------------------------ selection
    def read_selection(self) -> Json:
        project = self.project()
        tl = self.timeline()
        fps = parse_fps(
            tl.GetSetting("timelineFrameRate") or project.GetSetting("timelineFrameRate")
        )
        width = int(project.GetSetting("timelineResolutionWidth") or 1920)
        height = int(project.GetSetting("timelineResolutionHeight") or 1080)
        start = int(tl.GetStartFrame())
        clips: Dict[str, Json] = {}
        for kind in ("video", "audio"):
            for track in range(1, int(tl.GetTrackCount(kind)) + 1):
                for item in tl.GetItemListInTrack(kind, track) or []:
                    mpi = item.GetMediaPoolItem()
                    if not mpi:
                        continue  # titles, generators, compound clips
                    path = mpi.GetClipProperty("File Path")
                    if not path or path in clips:
                        continue
                    if kind == "audio" and "audio" not in str(mpi.GetClipProperty("Type")).lower():
                        continue  # a camera's own audio is not a separate mic
                    rec = int(item.GetStart()) - start
                    left = int(item.GetLeftOffset())
                    clips[path] = {
                        "path": path,
                        "kind": kind,
                        "host_ref": mpi.GetUniqueId(),
                        "track": track,
                        "record_start_frame": rec,
                        "in_frame": left,
                        "out_frame": left + int(item.GetDuration()),
                        "label": None,
                    }
        found = list(clips.values())
        if not any(c["kind"] == "video" for c in found):
            raise EngineError(
                "setup_required",
                f'"{tl.GetName()}" has no video clips.',
                "Put each camera on its own video track.",
            )
        return {
            "host": {
                "app": "resolve",
                "version": str(self.resolve.GetVersionString()),
                "os": _os(),
            },
            "host_sequence_id": str(tl.GetUniqueId()),
            "sequence": {"fps": fps, "width": width, "height": height, "name": tl.GetName()},
            "already_synced": looks_synced(found),
            "clips": found,
        }

    # ------------------------------------------------------------ media pool
    def _media_items(self, plan: Json) -> Dict[str, Any]:
        pool = self.project().GetMediaPool()
        by_path: Dict[str, Any] = {}

        def walk(folder: Any) -> None:
            for clip in folder.GetClipList() or []:
                path = clip.GetClipProperty("File Path")
                if path and path not in by_path:
                    by_path[path] = clip
            for sub in folder.GetSubFolderList() or []:
                walk(sub)

        walk(pool.GetRootFolder())
        missing = [m["path"] for m in plan["media"] if m["path"] not in by_path]
        if missing:
            for clip in pool.ImportMedia(missing) or []:
                by_path[clip.GetClipProperty("File Path")] = clip
        out = {}
        for m in plan["media"]:
            if m["path"] not in by_path:
                raise EngineError(
                    "media_offline", "cannot import " + m["name"], "Relink the media."
                )
            out[m["clip_id"]] = by_path[m["path"]]
        return out

    # ------------------------------------------------------------ apply
    def apply_plan(self, plan: Json, method: str) -> Json:
        project = self.project()
        pool = project.GetMediaPool()
        items = self._media_items(plan)
        tl = pool.CreateEmptyTimeline(plan["sequence"]["name"])
        if not tl:
            raise EngineError("host_error", "Resolve could not create the timeline (name taken?)")
        project.SetCurrentTimeline(tl)
        ops = placements(plan, method)
        for kind in ("video", "audio"):
            need = max([o["track"] for o in ops if o["kind"] == kind] or [0])
            while int(tl.GetTrackCount(kind)) < need:
                if not (tl.AddTrack(kind) if kind == "video" else tl.AddTrack(kind, "stereo")):
                    break
        seq_fps = fps_fraction(plan["sequence"]["fps"])
        media = {m["clip_id"]: m for m in plan["media"]}
        rates = {cid: self._clip_rate(m, items[cid], seq_fps) for cid, m in media.items()}
        start = int(tl.GetStartFrame())
        infos: List[Json] = []
        for op in ops:
            m, rate = media[op["clip_id"]], rates[op["clip_id"]]
            src_frames = round(Fraction(op["end"] - op["start"]) * rate / seq_fps)
            if m["width"] > 0:
                first = int(op["source_in_frame"])  # already at the clip's own rate
            else:  # sound-only: the plan counts 100 "fps"; Resolve uses the clip's rate
                first = round(Fraction(int(op["source_in_sample"]), int(m["sample_rate"])) * rate)
            infos.append(
                {
                    "mediaPoolItem": items[op["clip_id"]],
                    "startFrame": first,
                    "endFrame": first + max(1, src_frames) - (1 if END_INCLUSIVE else 0),
                    "trackIndex": op["track"],
                    "recordFrame": start + op["start"],
                    "mediaType": VIDEO if op["kind"] == "video" else AUDIO,
                }
            )
        placed = pool.AppendToTimeline(infos) or []
        warnings: List[str] = []
        if len(placed) != len(infos):
            warnings.append(f"Resolve placed {len(placed)} of {len(infos)} clips")
        if method == "stacked_enable" and len(placed) != len(infos):
            warnings.append("Not disabling cameras: Resolve skipped clips, check the tracks.")
        elif method == "stacked_enable":
            for op, item in zip(ops, placed):
                if op["kind"] == "video" and not op["enabled"]:
                    if hasattr(item, "SetClipEnabled"):
                        item.SetClipEnabled(False)
                    else:
                        warnings.append("This Resolve cannot disable clips from a script.")
                        break
        return {
            "timeline": tl,
            "name": tl.GetName(),
            "via": "native",
            "markers": 0,
            "warnings": warnings,
        }

    @staticmethod
    def _clip_rate(media: Json, item: Any, seq_fps: Fraction) -> Fraction:
        """Frame rate Resolve counts this clip's source frames in."""
        if media["width"] > 0:
            return fps_fraction(media["fps"])
        try:
            rate = parse_fps(item.GetClipProperty("FPS"))
            return Fraction(int(rate["num"]), int(rate["den"]))
        except (ValueError, TypeError, ZeroDivisionError, AttributeError, IndexError):
            return seq_fps  # audio files usually take the project rate

    def import_xml(self, path: str, plan: Json) -> Json:
        project = self.project()
        tl = project.GetMediaPool().ImportTimelineFromFile(
            path, {"timelineName": plan["sequence"]["name"], "importSourceClips": True}
        )
        if not tl:
            raise EngineError("host_error", "Resolve could not import " + path)
        project.SetCurrentTimeline(tl)
        return {
            "timeline": tl,
            "name": tl.GetName(),
            "via": "xml",
            "markers": len(plan["markers"]),
            "warnings": [],
        }

    def add_markers(self, timeline: Any, markers: List[Json]) -> int:
        added = 0
        for m in markers:
            ok = timeline.AddMarker(
                int(m["frame"]),
                MARKER_COLORS.get(m.get("color", "yellow"), "Yellow"),
                (m.get("note") or "Check this cut")[:60],
                m.get("note", ""),
                int(m.get("duration", 1)),
                "",
            )
            added += 1 if ok else 0
        return added


def _os() -> str:
    import sys

    return {"darwin": "mac", "win32": "windows"}.get(sys.platform, "linux")


def find_resolve(globals_: Optional[Dict[str, Any]] = None) -> Any:
    """The `resolve` object inside Resolve's Scripts menu (or via DaVinciResolveScript)."""
    g = globals_ or {}
    if g.get("resolve"):
        return g["resolve"]
    if g.get("app"):
        return g["app"].GetResolve()
    if g.get("bmd"):
        return g["bmd"].scriptapp("Resolve")
    try:
        import DaVinciResolveScript as dvr  # type: ignore[import-not-found]  # noqa: N813

        return dvr.scriptapp("Resolve")
    except ImportError:
        return None
