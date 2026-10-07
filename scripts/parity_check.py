#!/usr/bin/env python3
"""Feature parity check: Multicam Studio vs AutoPod + PodFast (docs/PARITY_TODO.md).

Stdlib only - runs with any Python 3.9+ (macOS's own python3), no `uv sync` needed.

    python3 scripts/parity_check.py                  # static: read the repo, print the matrix
    python3 scripts/parity_check.py --write          # + write docs/PARITY_REPORT.md
    python3 scripts/parity_check.py --save-baseline  # remember today's statuses
    python3 scripts/parity_check.py --check-baseline # exit 1 if any feature went backwards (CI)

    # live: talk to a running engine (desktop app open, or `uv run multicam-api --headless`)
    python3 scripts/parity_check.py --live
    python3 scripts/parity_check.py --live --media samples/demo/cam1.mp4 samples/demo/cam2.mp4 \
        --wide samples/demo/wide.mp4             # + full auto-edit run and plan checks

Static mode decides a status per feature from evidence in the code:

    DONE     every "done" check passes
    PARTIAL  some evidence exists (engine side only, stub, beta ...)
    MISSING  nothing found
    HOST     code is done, but it still has to be confirmed inside the real NLE

Static checks only prove that code exists. The live mode proves the engine does it,
and the HOST items need a person in Premiere / Resolve (checklist in PARITY_TODO.md).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
REPORT = ROOT / "docs" / "PARITY_REPORT.md"
BASELINE = ROOT / "docs" / "parity_baseline.json"
P = "/api/plugin/v1"

RANK = {"MISSING": 0, "PARTIAL": 1, "HOST": 2, "DONE": 3}
SKIP_DIRS = {"node_modules", "dist", "__pycache__", ".venv", ".git", "release", ".mypy_cache"}

# ----------------------------------------------------------------------------- checks
_cache: dict[Path, str] = {}


def _files(rel: str) -> list[Path]:
    base = ROOT / rel
    if base.is_file():
        return [base]
    if not base.is_dir():
        return []
    out: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            if name.endswith((".py", ".ts", ".tsx", ".json", ".xml", ".md", ".mjs")):
                out.append(Path(dirpath) / name)
    return out


def _text(path: Path) -> str:
    if path not in _cache:
        try:
            _cache[path] = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            _cache[path] = ""
    return _cache[path]


Check = tuple[str, Callable[[], bool]]


def exists(rel: str) -> Check:
    return (f"exists {rel}", lambda: (ROOT / rel).exists())


def grep(pattern: str, *rels: str) -> Check:
    rx = re.compile(pattern, re.IGNORECASE | re.MULTILINE)

    def run() -> bool:
        return any(rx.search(_text(f)) for rel in rels for f in _files(rel))

    return (f"/{pattern}/ in {', '.join(rels)}", run)


def no_grep(pattern: str, *rels: str) -> Check:
    name, run = grep(pattern, *rels)
    return ("NOT " + name, lambda: not run())


# ----------------------------------------------------------------------------- features
ENGINE = "engine/src/multicam_engine"
API = "apps/api/src/multicam_api"
PPRO = "apps/plugins/premiere-uxp/src"
RSCRIPT = "apps/plugins/resolve-script"
CORE = "packages/plugin-core/src"
PLUGIN_ROUTER = f"{API}/routers/plugin.py"


@dataclass
class Feature:
    id: str
    source: str  # AutoPod | PodFast | Ours
    area: str
    name: str
    phase: str  # PARITY_TODO phase that owns it
    done: list[Check]
    partial: list[Check] = field(default_factory=list)
    host: bool = False  # still needs a manual test inside the NLE once code is done
    note: str = ""
    status: str = "MISSING"
    evidence: list[str] = field(default_factory=list)

    def evaluate(self) -> None:
        results = [(n, f()) for n, f in self.done]
        self.evidence = [("ok  " if ok else "no  ") + n for n, ok in results]
        if results and all(ok for _, ok in results):
            self.status = "HOST" if self.host else "DONE"
            return
        part = [(n, f()) for n, f in self.partial]
        self.evidence += [("ok  " if ok else "no  ") + "(partial) " + n for n, ok in part]
        if any(ok for _, ok in results) or any(ok for _, ok in part):
            self.status = "PARTIAL"
        else:
            self.status = "MISSING"


SOCIAL_STUB = r"social clips are not available in this engine yet"
ADOBE_NO_MULTICAM = (
    "Adobe has no multicam API: stacked edit + a ready 'Multicam Source' sequence (one import)"
)


def F(  # noqa: N802 - reads like a table row
    fid: str,
    source: str,
    area: str,
    name: str,
    phase: str,
    done: list[Check],
    partial: list[Check] | None = None,
    *,
    host: bool = False,
    note: str = "",
) -> Feature:
    return Feature(fid, source, area, name, phase, done, partial or [], host, note)


FEATURES: list[Feature] = [
    # ------------------------------------------------------------ AutoPod: multicam editor
    F(
        "AP-M1",
        "AutoPod",
        "Multicam",
        "Up to 10 cameras + 10 mics",
        "P1",
        [
            grep(r"MAX_CAMERAS: Final = 10", f"{ENGINE}/models", f"{ENGINE}/layout.py"),
            grep(r"MAX_SPEAKERS: Final = 10", f"{ENGINE}/models", f"{ENGINE}/layout.py"),
        ],
    ),
    F(
        "AP-M2",
        "AutoPod",
        "Multicam",
        "Shot types solo / two / three / four / wide",
        "P1",
        [
            grep(r'SOLO = "solo"', f"{ENGINE}/models"),
            grep(r'FOUR = "four"', f"{ENGINE}/models"),
            grep(r'WIDE = "wide"', f"{ENGINE}/models"),
        ],
    ),
    F(
        "AP-M3",
        "AutoPod",
        "Multicam",
        "Cover-set switching (any common camera layout)",
        "P1",
        [grep(r"group_reward", f"{ENGINE}/decide/switch.py"), grep(r"covers", f"{ENGINE}/models")],
    ),
    F(
        "AP-M4",
        "AutoPod",
        "Multicam",
        '"More wide shots" control (wide frequency)',
        "P1",
        [
            grep(r"wide_frequency", f"{ENGINE}/decide/switch.py"),
            grep(r"wide_frequency", f"{CORE}/ui"),
        ],
    ),
    F(
        "AP-M5",
        "AutoPod",
        "Multicam",
        "Saved presets (create / import / export)",
        "P1",
        [
            grep(r"/import", f"{API}/routers/presets.py"),
            grep(r"/export", f"{API}/routers/presets.py"),
            grep(r"PUNCHY", f"{ENGINE}/models"),
        ],
    ),
    F(
        "AP-M6",
        "AutoPod",
        "Multicam",
        "Output method: plain cuts",
        "P2",
        [
            grep(r'CUTS = "cuts"', f"{ENGINE}/editplan/model.py"),
            grep(r"createOverwriteItemAction", f"{PPRO}/adapter.ts"),
        ],
        host=True,
        note="native apply is beta; run the PL4 spike checklist",
    ),
    F(
        "AP-M7",
        "AutoPod",
        "Multicam",
        "Output method: enable / disable, ONE undo step",
        "P2",
        [
            grep(r"STACKED_ENABLE", f"{ENGINE}/editplan/model.py"),
            grep(r"stackedOneUndo === false", f"{CORE}/plan.ts"),
            grep(r"stackedOneUndo: false", f"{PPRO}/adapter.ts"),
            grep(r"<enabled>|\"enabled\", \"TRUE\" if enabled", f"{ENGINE}/export/xmeml.py"),
        ],
        partial=[grep(r"createSetDisabledAction", f"{PPRO}/adapter.ts")],
        host=True,
        note="stacked always comes in by XML import (clips arrive disabled)",
    ),
    F(
        "AP-M8",
        "AutoPod",
        "Multicam",
        "Output method: multicam in Premiere",
        "P2",
        [
            grep(r"def to_xmeml_multicam", f"{ENGINE}/editplan"),
            grep(r"MULTICAM_SOURCE_SUFFIX", f"{PPRO}/adapter.ts"),
            grep(r"to_xmeml_multicam", PLUGIN_ROUTER),
        ],
        partial=[grep(r"fcpxml_multicam", PLUGIN_ROUTER)],
        host=True,
        note=ADOBE_NO_MULTICAM,
    ),
    F(
        "AP-M9",
        "AutoPod",
        "Multicam",
        "Premiere panel (UXP)",
        "P2",
        [exists("apps/plugins/premiere-uxp/manifest.json"), exists(f"{PPRO}/adapter.ts")],
        host=True,
        note="never loaded in Premiere yet",
    ),
    F(
        "AP-M10",
        "AutoPod",
        "Multicam",
        "DaVinci Resolve support",
        "P2",
        [
            exists(f"{RSCRIPT}/multicam_resolve/adapter.py"),
            exists("apps/plugins/resolve-wi/src/adapter.ts"),
        ],
        host=True,
        note="Resolve spike not run",
    ),
    # ------------------------------------------------------------ AutoPod: social clips
    F(
        "AP-S1",
        "AutoPod",
        "Social",
        "In/out range -> new sequence per aspect ratio",
        "P3",
        [
            no_grep(SOCIAL_STUB, PLUGIN_ROUTER),
            grep(r"def build_social_plans", f"{ENGINE}/editplan"),
            grep(r"createSocial", f"{CORE}/session.ts"),
            grep(r"readInOut", f"{PPRO}/adapter.ts"),
        ],
        partial=[grep(r"class SocialIn", f"{API}/plugin_schemas.py")],
        host=True,
    ),
    F(
        "AP-S2",
        "AutoPod",
        "Social",
        "Sizes 1920x1080 / 1080x1350 / 1080x1920 (+1:1)",
        "P3",
        [
            grep(r"\(1080, 1350\)", f"{ENGINE}/editplan/social.py"),
            grep(r"\(1080, 1920\)", f"{ENGINE}/editplan/social.py"),
        ],
        partial=[grep(r'"4:5"', f"{API}/plugin_schemas.py")],
    ),
    F(
        "AP-S3",
        "AutoPod",
        "Social",
        "Auto-reframe (ours: speaker-aware face tracking)",
        "P3",
        [
            exists(f"{ENGINE}/reframe/auto.py"),
            grep(r"def crop_transform", f"{ENGINE}/editplan"),
            grep(r"Basic Motion", f"{ENGINE}/export/xmeml.py"),
        ],
        partial=[exists(f"{ENGINE}/reframe/auto.py")],
        host=True,
        note="Motion keyframes come in through the XML: check them in Premiere",
    ),
    F(
        "AP-S4",
        "AutoPod",
        "Social",
        "Watermark overlay",
        "P3",
        [
            grep(r"def watermark_overlay", f"{ENGINE}/editplan/social.py"),
            grep(r"watermark", f"{CORE}/ui"),
        ],
    ),
    F(
        "AP-S5",
        "AutoPod",
        "Social",
        "End page / outro clip",
        "P3",
        [grep(r"class EndPage", f"{ENGINE}/editplan/social.py"), grep(r"end_page", f"{CORE}/ui")],
    ),
    F(
        "AP-S6",
        "AutoPod",
        "Social",
        "Clips filed in one bin + batch export (Media Encoder)",
        "P3",
        [grep(r"createBinAction", PPRO), grep(r"exportSequence", f"{PPRO}/adapter.ts")],
        host=True,
        note="AME queue needs Premiere + Media Encoder to confirm",
    ),
    # ------------------------------------------------------------ AutoPod: jump cuts
    F(
        "AP-J1",
        "AutoPod",
        "Jump cuts",
        "Detect silences -> removals in the EditPlan",
        "P4",
        [
            grep(r"RemovalKind\.SILENCE", f"{ENGINE}/jumpcut"),
            grep(r"JUMPCUT", f"{API}/jobs/steps.py"),
        ],
        partial=[grep(r'SILENCE = "silence"', f"{ENGINE}/models/cutlist.py")],
    ),
    F(
        "AP-J2",
        "AutoPod",
        "Jump cuts",
        "dB threshold (AutoPod mode) + VAD mode (ours)",
        "P4",
        [
            grep(r"\bthreshold_db\b", f"{ENGINE}/jumpcut"),
            grep(r'"vad"', f"{ENGINE}/jumpcut"),
            grep(r"mic_threshold_db", f"{ENGINE}/jumpcut"),
        ],
    ),
    F(
        "AP-J3",
        "AutoPod",
        "Jump cuts",
        "Padding / min silence / min cut settings",
        "P4",
        [
            grep(r"min_silence_s", f"{ENGINE}/jumpcut"),
            grep(r"pad_s", f"{ENGINE}/jumpcut"),
            grep(r"min_removal_s", f"{ENGINE}/jumpcut"),
        ],
    ),
    F(
        "AP-J4",
        "AutoPod",
        "Jump cuts",
        "Ripple delete on every track (sync kept)",
        "P4",
        [
            grep(r"def apply_removals", f"{ENGINE}/editplan/ripple.py"),
            grep(r"ripple: true", f"{CORE}/session.ts"),
        ],
        host=True,
        note="engine ripples; Premiere imports the result as a new sequence",
    ),
    F(
        "AP-J5",
        "AutoPod",
        "Jump cuts",
        "Preview / approve removals in the panel",
        "P4",
        [grep(r"removals", f"{CORE}/ui"), grep(r"/removals", PLUGIN_ROUTER)],
    ),
    # ------------------------------------------------------------ PodFast (audio)
    F(
        "PF-1",
        "PodFast",
        "Audio",
        "Speech enhance / denoise (local, not Adobe cloud)",
        "P5",
        [grep(r"arnndn|afftdn|deepfilter|rnnoise|enhance_speech", f"{ENGINE}")],
    ),
    F(
        "PF-2",
        "PodFast",
        "Audio",
        "Loudness normalise (podcast -16 / -14 LUFS)",
        "P5",
        [grep(r"loudnorm|lufs", f"{ENGINE}")],
    ),
    F(
        "PF-3",
        "PodFast",
        "Audio",
        "Mono / stereo export presets",
        "P5",
        [grep(r"mono|stereo", f"{ENGINE}/audiofx", f"{ENGINE}/enhance")],
    ),
    F(
        "PF-4",
        "PodFast",
        "Audio",
        "Vocal remover (voice vs music)",
        "P5",
        [grep(r"demucs|vocal_remov|separate_stems", f"{ENGINE}")],
    ),
    F(
        "PF-5",
        "PodFast",
        "Audio",
        "Splitter: vocals / drums / bass / other stems",
        "P5",
        [
            grep(
                r"drums.*bass|stems", f"{ENGINE}/audiofx", f"{ENGINE}/enhance", f"{ENGINE}/separate"
            )
        ],
    ),
    F(
        "PF-6",
        "PodFast",
        "Audio",
        "Round-trip: processed audio on a free track / replace",
        "P5",
        [grep(r"replaceAudio|freeTrack|free_track|roundtrip|round_trip", PPRO, CORE)],
    ),
    F(
        "PF-7",
        "PodFast",
        "Audio",
        "Custom label + color for processed clips",
        "P5",
        [grep(r"setColorLabel|colorLabel|processed_label", PPRO, CORE)],
    ),
    F(
        "PF-8",
        "PodFast",
        "Project",
        "Auto rename + own bin for imported files",
        "P5",
        [grep(r"createBinAction", PPRO), grep(r"processed_label|\[Enhanced\]", PPRO, CORE)],
        partial=[grep(r"createBinAction|getInsertionBin", PPRO)],
        note="bins exist (Multicam Studio, Social); renaming processed audio comes with P5",
    ),
    F(
        "PF-9",
        "PodFast",
        "Project",
        "Process only the sequence in/out (work area)",
        "P5",
        [grep(r"workArea|work_area", PPRO, CORE)],
        partial=[grep(r"readInOut", f"{PPRO}/adapter.ts")],
        note="In/Out marks are read for social clips; audio tools come with P5",
    ),
    F(
        "PF-10",
        "PodFast",
        "Project",
        "Keyboard shortcuts for panel actions",
        "P5",
        [grep(r'"commands"|shortcut', "apps/plugins/premiere-uxp/manifest.json", PPRO)],
    ),
    F(
        "PF-11",
        "PodFast",
        "Transcript",
        "Local transcription (whisper), Hindi/English",
        "P6",
        [grep(r"whisper|def transcribe", f"{ENGINE}/transcribe")],
        note="engine/transcribe is an empty stub",
    ),
    F(
        "PF-12",
        "PodFast",
        "Transcript",
        "SRT / VTT export aligned to the clip",
        "P6",
        [grep(r'"srt"', PLUGIN_ROUTER), grep(r"def .*srt", f"{ENGINE}")],
    ),
    F(
        "PF-13",
        "PodFast",
        "Transcript",
        "Captions on the Premiere timeline",
        "P6",
        [grep(r"captions:\s*true", f"{PPRO}/adapter.ts")],
    ),
    F(
        "PF-14",
        "PodFast",
        "Transcript",
        "Filler-word removal (um, uh, matlab, basically)",
        "P6",
        [grep(r"RemovalKind\.FILLER", f"{ENGINE}/transcribe", f"{ENGINE}/analysis")],
        partial=[grep(r'FILLER = "filler"', f"{ENGINE}/models/cutlist.py")],
        note="removal review + ripple already exist (jump cuts); needs the transcript",
    ),
    # ------------------------------------------------------------ our extras (keep them working)
    F(
        "OUR-1",
        "Ours",
        "Edge",
        "Built-in audio sync (unsynced clips)",
        "P0",
        [exists(f"{ENGINE}/sync/gcc_phat.py"), exists(f"{ENGINE}/sync/drift.py")],
    ),
    F(
        "OUR-2",
        "Ours",
        "Edge",
        "Skip sync for already-synced sequences",
        "P0",
        [grep(r"already_synced", PLUGIN_ROUTER)],
    ),
    F(
        "OUR-3",
        "Ours",
        "Edge",
        "Low-confidence cut markers",
        "P0",
        [grep(r"low_confidence", f"{ENGINE}/editplan")],
    ),
    F(
        "OUR-4",
        "Ours",
        "Edge",
        "Final Cut (FCPXML multicam)",
        "P0",
        [exists(f"{ENGINE}/editplan/fcpxml_multicam.py")],
        host=True,
        note="not yet imported in Final Cut",
    ),
    F(
        "OUR-5",
        "Ours",
        "Edge",
        "Single-mic mode (diarization / visual ASD)",
        "P7",
        [exists(f"{ENGINE}/analysis/diarize.py")],
        [exists(f"{ENGINE}/analysis/asd.py")],
    ),
    F(
        "OUR-6",
        "Ours",
        "Edge",
        "Learn my style (feedback -> preset)",
        "P7",
        [grep(r"my_style|learn_style", f"{ENGINE}", f"{API}")],
        [grep(r"/feedback", PLUGIN_ROUTER)],
        note="feedback is stored, not used yet",
    ),
    F(
        "OUR-7",
        "Ours",
        "Ship",
        "Licence + signed .ccx + installer",
        "P8",
        [grep(r"ed25519|licen[cs]e_key", f"{ENGINE}", f"{API}")],
        [exists("apps/plugins/premiere-uxp/scripts")],
    ),
]


# ----------------------------------------------------------------------------- static
def run_static() -> list[Feature]:
    for f in FEATURES:
        f.evaluate()
    return FEATURES


def matrix(features: list[Feature], verbose: bool) -> str:
    lines = [
        "| ID | Source | Area | Feature | Status | Phase | Note |",
        "|---|---|---|---|---|---|---|",
    ]
    for f in features:
        lines.append(
            f"| {f.id} | {f.source} | {f.area} | {f.name} | **{f.status}** | {f.phase} | {f.note} |"
        )
    out = "\n".join(lines)
    if verbose:
        out += "\n\n### Evidence\n"
        for f in features:
            out += f"\n**{f.id}** {f.name}\n" + "\n".join(f"    {e}" for e in f.evidence) + "\n"
    return out


def summary(features: list[Feature]) -> str:
    parts = []
    for src in ("AutoPod", "PodFast", "Ours"):
        fs = [f for f in features if f.source == src]
        counts = {s: sum(1 for f in fs if f.status == s) for s in RANK}
        parts.append(f"{src}: " + ", ".join(f"{k} {v}" for k, v in counts.items() if v))
    return " · ".join(parts)


# ----------------------------------------------------------------------------- live
class Engine:
    def __init__(self, base: str, token: str) -> None:
        self.base, self.token = base.rstrip("/"), token

    def call(
        self, method: str, path: str, body: Any = None, timeout: float = 60
    ) -> tuple[int, Any]:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method)
        req.add_header("X-Multicam-Token", self.token)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read()
                return r.status, json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            raw = e.read()
            try:
                return e.code, json.loads(raw)
            except ValueError:
                return e.code, raw.decode(errors="replace")


def default_data_dir() -> Path:
    env = os.environ.get("MULTICAM_DATA_DIR")
    if env:
        return Path(env)
    # One if/elif/else: mypy treats sys.platform as a constant and would flag
    # early returns for the other platforms as unreachable.
    if sys.platform == "darwin":
        path = Path.home() / "Library/Application Support/Multicam Studio"
    elif sys.platform == "win32":
        path = Path(os.environ.get("APPDATA", str(Path.home()))) / "Multicam Studio"
    else:
        base = os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share"))
        path = Path(base) / "multicam-studio"
    return path


def find_engine(args: argparse.Namespace) -> Engine:
    if args.url and args.token:
        return Engine(args.url, args.token)
    candidates = [args.data_dir] if args.data_dir else [default_data_dir()]
    for d in candidates:
        f = Path(d) / "engine.json"
        if f.is_file():
            info = json.loads(f.read_text())
            base = info.get("base_url") or f"http://127.0.0.1:{info['port']}"
            return Engine(base, info["token"])
    sys.exit(
        f"no engine.json in {candidates[0]} - open the desktop app or run "
        "`uv run multicam-api --headless` (or pass --url and --token)"
    )


@dataclass
class LiveResult:
    id: str
    name: str
    ok: bool | None  # None = skipped
    detail: str


def _wait_ready(eng: Engine, sid: str, timeout: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        code, s = eng.call("GET", f"{P}/sessions/{sid}")
        if code == 200 and s["state"] in ("ready", "failed"):
            out: dict[str, Any] = s
            return out
        time.sleep(1.0)
    raise TimeoutError("run did not finish in time")


def _plan_checks(plan: dict[str, Any], min_shot_s: float) -> list[str]:
    """Problems in a plan (empty list = good)."""
    problems: list[str] = []
    fps = plan["sequence"]["fps"]
    fpsf = fps["num"] / fps["den"]
    ev = plan["video_events"]
    if not ev:
        return ["no video events"]
    for i in range(len(ev) - 1):  # (no itertools.pairwise: macOS ships Python 3.9)
        a, b = ev[i], ev[i + 1]
        if b["start"] < a["end"]:  # gaps are fine (a camera not recording yet)
            problems.append(f"overlap at frame {b['start']}")
            break
    min_frames = int(min_shot_s * fpsf * 0.9)
    short = [e for e in ev[1:-1] if e["end"] - e["start"] < min_frames]
    if short:
        problems.append(f"{len(short)} shots shorter than min shot ({min_shot_s}s) - flicker (S3)")
    if ev[-1]["end"] > plan["sequence"]["duration_frames"]:
        problems.append("events run past the sequence end")
    return problems


def run_live(args: argparse.Namespace) -> list[LiveResult]:
    eng = find_engine(args)
    res: list[LiveResult] = []

    code, hs = eng.call("GET", f"{P}/handshake")
    if code != 200:
        sys.exit(f"handshake failed: {code} {hs}")
    caps = set(hs.get("capabilities", []))
    res.append(
        LiveResult(
            "L0", f"handshake (api {hs.get('api_version')})", True, hs.get("engine_version", "")
        )
    )
    for cap, fid in [
        ("method:cuts", "AP-M6"),
        ("method:stacked_enable", "AP-M7"),
        ("method:multicam", "AP-M8"),
        ("presets", "AP-M5"),
        ("markers", "OUR-3"),
        ("already_synced", "OUR-2"),
        ("social", "AP-S1"),
        ("social:watermark", "AP-S4"),
        ("social:end_page", "AP-S5"),
        ("jump_cuts", "AP-J1"),
        ("ripple", "AP-J4"),
        ("export:xmeml_multicam_source", "AP-M8"),
        ("enhance", "PF-1"),
        ("transcribe", "PF-11"),
        ("export:srt", "PF-12"),
    ]:
        res.append(
            LiveResult(
                fid, f"capability {cap}", cap in caps, "" if cap in caps else "not advertised"
            )
        )
    vad = hs.get("models", {}).get("vad")
    res.append(
        LiveResult("L1", "Silero VAD model installed", bool(vad), "" if vad else "run fetch_models")
    )

    code, presets = eng.call("GET", f"{P}/presets")
    names = (
        {str(p.get(k, "")).lower() for p in presets for k in ("id", "name")}
        if code == 200
        else set()
    )
    want = {"calm", "balanced", "punchy"}
    res.append(
        LiveResult(
            "AP-M5",
            "built-in presets calm/balanced/punchy",
            want <= names,
            ", ".join(sorted(n for n in names if n))[:80],
        )
    )

    if not args.media:
        res.append(LiveResult("L2", "full auto-edit run", None, "skipped (pass --media ...)"))
        return res

    clips = [{"path": str(Path(m).resolve()), "kind": "video"} for m in [*args.media, *args.wide]]
    wide = {str(Path(w).resolve()) for w in args.wide}
    code, sess = eng.call(
        "POST",
        f"{P}/sessions",
        {
            "host": {"app": "premiere", "version": "parity-check", "os": sys.platform},
            "host_sequence_id": "parity-check:" + "|".join(c["path"] for c in clips)[-180:],
            "sequence": {"fps": {"num": 30000, "den": 1001}, "width": 1920, "height": 1080},
            "already_synced": args.synced,
            "clips": clips,
        },
    )
    if code not in (200, 201):
        sys.exit(f"POST /sessions failed: {code} {sess}")
    sid = sess["id"]
    roles = [
        {"clip_id": c["clip_id"], "role": "wide" if c["path"] in wide else c["role"]}
        for c in sess["clips"]
    ]
    eng.call(
        "PATCH",
        f"{P}/sessions/{sid}/setup",
        {"roles": roles, "preset": "balanced", "method": "stacked_enable"},
    )
    t0 = time.monotonic()
    code, run = eng.call("POST", f"{P}/sessions/{sid}/run", {})
    if code != 202:
        sys.exit(f"run failed: {code} {run}")
    s = _wait_ready(eng, sid, args.timeout)
    t_full = time.monotonic() - t0
    res.append(
        LiveResult(
            "S4", f"full run finished ({s['state']})", s["state"] == "ready", f"{t_full:.1f}s"
        )
    )
    if s["state"] != "ready":
        return res
    min_shot = float(s["switch"]["min_shot_s"])

    for method in ("cuts", "stacked_enable", "multicam"):
        code, plan = eng.call("GET", f"{P}/sessions/{sid}/editplan?host=premiere&method={method}")
        if code != 200:
            res.append(LiveResult("AP-M6", f"plan method={method}", False, f"{code}"))
            continue
        probs = _plan_checks(plan, min_shot)
        res.append(
            LiveResult(
                "AP-M6" if method == "cuts" else "AP-M7" if method == "stacked_enable" else "AP-M8",
                f"plan method={method}: {len(plan['video_events'])} events, "
                f"{len(plan['markers'])} markers",
                not probs,
                "; ".join(probs),
            )
        )

    for fmt in ("xmeml", "fcpxml", "fcpxml_multicam", "edl", "srt"):
        code, exp = eng.call("GET", f"{P}/sessions/{sid}/export?format={fmt}")
        if code != 200:
            res.append(
                LiveResult(
                    "PF-12" if fmt == "srt" else "OUR-4",
                    f"export {fmt}",
                    False,
                    exp.get("code", str(code)) if isinstance(exp, dict) else str(code),
                )
            )
            continue
        path = Path(exp["path"])
        detail, ok = str(path), path.is_file() and path.stat().st_size > 0
        if ok and fmt != "edl" and fmt != "srt":
            try:
                ET.parse(str(path))
            except ET.ParseError as e:
                ok, detail = False, f"XML does not parse: {e}"
        res.append(LiveResult("OUR-4" if "fcpxml" in fmt else "AP-M6", f"export {fmt}", ok, detail))

    # "more wide shots": wide share must grow with wide_frequency (needs a wide camera)
    if args.wide:
        shares = []
        for wf in (0.0, 1.0):
            sw = dict(s["switch"], wide_frequency=wf)
            eng.call("PATCH", f"{P}/sessions/{sid}/setup", {"switch": sw})
            t1 = time.monotonic()
            eng.call("POST", f"{P}/sessions/{sid}/run", {"steps": ["decide"]})
            _wait_ready(eng, sid, 120)
            t_recut = time.monotonic() - t1
            _, plan = eng.call("GET", f"{P}/sessions/{sid}/editplan?method=cuts")
            total = sum(e["end"] - e["start"] for e in plan["video_events"]) or 1
            shares.append(
                sum(
                    e["end"] - e["start"]
                    for e in plan["video_events"]
                    if e["shot"] in ("wide", "two", "three", "four")
                )
                / total
            )
        res.append(
            LiveResult(
                "AP-M4",
                "wide_frequency 0 -> 1 raises group/wide share",
                shares[1] > shares[0],
                f"{shares[0]:.0%} -> {shares[1]:.0%}",
            )
        )
        res.append(
            LiveResult(
                "S6",
                "re-cut with new settings < 1 s (+ poll overhead)",
                t_recut < 3.0,
                f"{t_recut:.2f}s",
            )
        )
        eng.call("PATCH", f"{P}/sessions/{sid}/setup", {"switch": s["switch"]})

    # Premiere multicam: stacked edit + "Multicam Source" sequence in one xmeml
    code, exp = eng.call("GET", f"{P}/sessions/{sid}/export?format=xmeml&method=multicam")
    seq_names: list[str] = []
    if code == 200 and Path(exp["path"]).is_file():
        root = ET.parse(exp["path"]).getroot()
        seq_names = [x.findtext("name") or "" for x in root.iter("sequence")]
    res.append(
        LiveResult(
            "AP-M8",
            "xmeml multicam = edit + Multicam Source",
            len(seq_names) == 2 and seq_names[1].endswith("Multicam Source"),
            ", ".join(seq_names),
        )
    )

    # social clips: one sequence per aspect, each with an xmeml
    code, soc = eng.call(
        "POST",
        f"{P}/sessions/{sid}/social",
        {"in_frame": 0, "out_frame": 300, "aspects": ["16:9", "4:5", "9:16", "1:1"]},
    )
    ok = code == 200 and [c["aspect"] for c in soc["clips"]] == ["16:9", "4:5", "9:16", "1:1"]
    if ok:
        ok = all(c["xml_path"] and Path(c["xml_path"]).is_file() for c in soc["clips"])
    res.append(
        LiveResult(
            "AP-S1",
            "social clips: 4 aspects with xmeml",
            ok,
            soc.get("message", "") if isinstance(soc, dict) and code != 200 else "",
        )
    )

    # jump cuts: find pauses (dB), review, ripple
    code, run = eng.call(
        "POST", f"{P}/sessions/{sid}/jumpcuts", {"mode": "db", "threshold_db": -40}
    )
    if code != 202:
        res.append(LiveResult("AP-J1", "jump cuts job", False, str(run)[:120]))
        return res
    s2 = _wait_ready(eng, sid, args.timeout)
    code, rem = eng.call("GET", f"{P}/sessions/{sid}/removals")
    found = len(rem.get("removals", [])) if code == 200 else 0
    res.append(
        LiveResult(
            "AP-J1",
            "jump cuts: pauses found (dB mode)",
            s2["state"] == "ready" and found > 0,
            f"{found} pauses, {rem.get('removed_seconds', 0)} s" if code == 200 else str(rem),
        )
    )
    if found:
        code, full = eng.call("GET", f"{P}/sessions/{sid}/editplan")
        code2, cut = eng.call("GET", f"{P}/sessions/{sid}/editplan?ripple=true")
        ok = code == code2 == 200 and (
            cut["sequence"]["duration_frames"]
            == full["sequence"]["duration_frames"] - rem["removed_frames"]
        )
        res.append(LiveResult("AP-J4", "ripple: duration shrinks by the removals", ok, ""))
        eng.call("PATCH", f"{P}/sessions/{sid}/removals", {"all": False})  # leave it clean
    return res


def live_table(results: list[LiveResult]) -> str:
    lines = ["| ID | Check | Result | Detail |", "|---|---|---|---|"]
    for r in results:
        mark = "PASS" if r.ok else "SKIP" if r.ok is None else "FAIL"
        lines.append(f"| {r.id} | {r.name} | **{mark}** | {r.detail} |")
    return "\n".join(lines)


# ----------------------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--write", action="store_true", help=f"write {REPORT.relative_to(ROOT)}")
    ap.add_argument("--verbose", "-v", action="store_true", help="show the evidence per feature")
    ap.add_argument("--json", action="store_true", help="print machine-readable statuses")
    ap.add_argument("--save-baseline", action="store_true")
    ap.add_argument("--check-baseline", action="store_true", help="exit 1 if a feature regressed")
    ap.add_argument("--live", action="store_true", help="also test a running engine")
    ap.add_argument("--media", nargs="*", default=[], help="speaker camera files for a live run")
    ap.add_argument("--wide", action="append", default=[], help="wide camera file (repeatable)")
    ap.add_argument("--synced", action="store_true", help="clips already in sync at frame 0")
    ap.add_argument("--data-dir", type=Path)
    ap.add_argument("--url")
    ap.add_argument("--token")
    ap.add_argument("--timeout", type=float, default=900)
    args = ap.parse_args()

    features = run_static()
    if args.json:
        print(json.dumps({f.id: f.status for f in features}, indent=2))
    else:
        print(matrix(features, args.verbose))
        print("\n" + summary(features))

    live: list[LiveResult] = []
    if args.live:
        live = run_live(args)
        print("\n## Live engine checks\n")
        print(live_table(live))

    if args.write:
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        body = (
            f"# Parity report\n\n_Generated by `scripts/parity_check.py` on "
            f"{time.strftime('%Y-%m-%d %H:%M')}. Do not edit by hand._\n\n"
            f"{summary(features)}\n\n## Static (code evidence)\n\n{matrix(features, True)}\n"
        )
        if live:
            body += f"\n## Live engine checks\n\n{live_table(live)}\n"
        REPORT.write_text(body, encoding="utf-8")
        print(f"\nwrote {REPORT}")

    if args.save_baseline:
        BASELINE.write_text(json.dumps({f.id: f.status for f in features}, indent=2) + "\n")
        print(f"saved baseline -> {BASELINE}")

    rc = 0
    if args.check_baseline:
        if not BASELINE.is_file():
            print("no baseline yet: run with --save-baseline first")
            return 2
        base = json.loads(BASELINE.read_text())
        worse = [
            (f.id, base[f.id], f.status)
            for f in features
            if f.id in base and RANK[f.status] < RANK[base[f.id]]
        ]
        for fid, was, now in worse:
            print(f"REGRESSION {fid}: {was} -> {now}")
        better = [f.id for f in features if f.id in base and RANK[f.status] > RANK[base[f.id]]]
        if better:
            print("improved: " + ", ".join(better) + "  (run --save-baseline to lock it in)")
        rc = 1 if worse else 0
    if live and any(r.ok is False for r in live if r.id.startswith(("AP-M", "S", "OUR"))):
        rc = rc or 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
