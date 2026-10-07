"""EditPlan helpers (Python port of plugin-core/plan.ts and setup.ts)."""

import re
from fractions import Fraction
from typing import Any, Dict, List

Json = Dict[str, Any]

_WIDE = re.compile(r"(^|[^a-z])(wide|master|ws|group|all)([^a-z]|$)", re.I)
_BROLL = re.compile(r"(^|[^a-z])(b-?roll|cutaway|insert)([^a-z]|$)", re.I)
_NOISE = re.compile(r"^(cam(era)?|a|b|c|d|\d+|mic|audio|track|ch\d*)$", re.I)


def stem(path: str) -> str:
    name = path.replace("\\", "/").rsplit("/", 1)[-1]
    return name.rsplit(".", 1)[0] if "." in name else name


_CAMERA_PREFIX = re.compile(r"^(img|dsc|dscf|mvi|gopr|gx|vid|mov|clip|c|a|p)$", re.I)


def speaker_name(path: str) -> str:
    words = [w for w in re.split(r"[\s_\-.]+", stem(path)) if w and not _NOISE.match(w)]
    if not words or all(_CAMERA_PREFIX.match(w) for w in words):
        return stem(path)  # IMG_0001 / DSC_1234: the file name is the only label we have
    name = " ".join(words).strip() or stem(path)
    return name[:1].upper() + name[1:]


def guess_role(path: str, kind: str) -> str:
    if kind == "audio":
        return "mic"
    s = stem(path)
    if _BROLL.search(s):
        return "broll"
    if _WIDE.search(s):
        return "wide"
    return "speaker"


def default_roles(session: Json) -> List[Json]:
    roles = []
    for c in session["clips"]:
        role = c["role"] if c["role"] != "speaker" else guess_role(c["path"], c["kind"])
        label = None
        if role == "speaker":
            label = (
                c.get("label")
                if c.get("label") and c.get("label") != stem(c["path"])
                else speaker_name(c["path"])
            )
        roles.append({"clip_id": c["clip_id"], "role": role, "speaker_label": label})
    return roles


def looks_synced(clips: List[Json]) -> bool:
    """All clips at frame 0 with no trim = just dropped in, not synced (D88)."""
    if len(clips) < 2:
        return True
    offsets = {int(c.get("record_start_frame", 0)) - int(c.get("in_frame", 0)) for c in clips}
    return offsets != {0}


def fps_fraction(rate: Json) -> Fraction:
    return Fraction(int(rate["num"]), int(rate["den"]))


_NTSC = {23.976: 24, 29.97: 30, 47.952: 48, 59.94: 60, 119.88: 120}


def parse_fps(value: Any) -> Json:
    """Resolve's 'timelineFrameRate' ("29.97", "24", "23.976 DF"...) -> {num, den}."""
    text = str(value).split()[0]
    rate = float(text)
    for ntsc, base in _NTSC.items():
        if abs(rate - ntsc) < 0.005:
            return {"num": base * 1000, "den": 1001}
    f = Fraction(text).limit_denominator(1001)
    return {"num": f.numerator, "den": f.denominator}


def placements(plan: Json, method: str) -> List[Json]:
    """Clips to place: video first (by track, time), then audio."""

    def piece(p: Json, track: int, kind: str, enabled: bool) -> Json:
        return {
            "kind": kind,
            "track": track,
            "clip_id": p["clip_id"],
            "start": p["start"],
            "end": p["end"],
            "source_in_frame": p["source_in_frame"],
            "source_in_sample": p["source_in_sample"],
            "enabled": enabled,
        }

    ops: List[Json] = []
    if method == "cuts":
        ops += [piece(e, 1, "video", True) for e in plan["video_events"]]
    else:
        for t in sorted(plan["video_tracks"], key=lambda t: t["index"]):
            ops += [piece(p, t["index"], "video", bool(p["enabled"])) for p in t["pieces"]]
    for t in sorted(plan["audio_tracks"], key=lambda t: t["index"]):
        ops += [piece(p, t["index"], "audio", True) for p in t["pieces"]]
    return ops


def decide(plan: Json, method: str, caps: Json) -> Json:
    """Native or XML import (same rules as plugin-core decideApply)."""
    xml = caps.get("xml_import")
    if method == "multicam" and not caps.get("multicam"):
        if xml:
            return {"via": "xml", "method": method, "reason": "multicam clips come through FCPXML"}
        method = "stacked_enable"
    reframed = any(
        e.get("reframe") and (e["reframe"].get("scale", 1) != 1 or e["reframe"].get("path"))
        for e in plan["video_events"]
    )
    if reframed and not caps.get("keyframes") and xml:
        return {
            "via": "xml",
            "method": method,
            "reason": "reframing needs keyframes: FCPXML import",
        }
    if len(plan["video_events"]) > caps.get("max_native_events", 1500) and xml:
        return {"via": "xml", "method": method, "reason": "large edit: FCPXML import is faster"}
    return {"via": "native", "method": method, "reason": "native apply"}
