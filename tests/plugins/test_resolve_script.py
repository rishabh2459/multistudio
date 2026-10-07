"""DaVinci Resolve script (PL6): helpers, adapter on a fake Resolve, the window
wiring on a fake UIManager, and the whole flow against a real headless engine."""

from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from multicam_resolve import adapter as adapter_mod
from multicam_resolve.adapter import ResolveAdapter
from multicam_resolve.client import EngineError, PluginClient, connect, data_dir, read_engine_file
from multicam_resolve.flow import AutoEdit
from multicam_resolve.install import SCRIPT_NAME, install, scripts_dir, uninstall
from multicam_resolve.plan import (
    decide,
    default_roles,
    looks_synced,
    parse_fps,
    placements,
    speaker_name,
)

from . import fake_resolve as fr

REPO = Path(__file__).resolve().parents[2]
PLAN_FILE = REPO / "packages/plugin-core/test/fixtures/plan.json"
PLAN: dict[str, Any] = json.loads(PLAN_FILE.read_text())


# ------------------------------------------------------------------ helpers
@pytest.mark.parametrize(
    ("value", "rate"),
    [
        ("29.97", (30000, 1001)),
        ("23.976", (24000, 1001)),
        ("59.94 DF", (60000, 1001)),
        ("25", (25, 1)),
        ("24", (24, 1)),
        (30, (30, 1)),
    ],
)
def test_parse_fps(value: Any, rate: tuple[int, int]) -> None:
    assert parse_fps(value) == {"num": rate[0], "den": rate[1]}


def test_roles_and_names() -> None:
    session = {
        "clips": [
            {
                "clip_id": "1",
                "path": "/r/cam_A_rishabh.mov",
                "kind": "video",
                "role": "speaker",
                "label": "cam_A_rishabh",
            },
            {
                "clip_id": "2",
                "path": "/r/WIDE master.mp4",
                "kind": "video",
                "role": "speaker",
                "label": None,
            },
            {"clip_id": "3", "path": "/r/zoom.wav", "kind": "audio", "role": "mic", "label": None},
        ]
    }
    assert default_roles(session) == [
        {"clip_id": "1", "role": "speaker", "speaker_label": "Rishabh"},
        {"clip_id": "2", "role": "wide", "speaker_label": None},
        {"clip_id": "3", "role": "mic", "speaker_label": None},
    ]
    assert speaker_name("C:\\rec\\guest-cam-2.mp4") == "Guest"
    assert speaker_name("/r/IMG_0001.MOV") == "IMG_0001"  # generic camera names stay distinct
    assert looks_synced([{"record_start_frame": 0, "in_frame": 0}] * 2) is False
    assert (
        looks_synced([{"record_start_frame": 0, "in_frame": 0}, {"record_start_frame": 15}]) is True
    )


def test_placements_and_decision() -> None:
    cuts = [o for o in placements(PLAN, "cuts") if o["kind"] == "video"]
    assert [(o["start"], o["end"]) for o in cuts] == [
        (e["start"], e["end"]) for e in PLAN["video_events"]
    ]
    stacked = [o for o in placements(PLAN, "stacked_enable") if o["kind"] == "video"]
    live = sorted((o["start"], o["clip_id"]) for o in stacked if o["enabled"])
    assert live == [(e["start"], e["clip_id"]) for e in PLAN["video_events"]]
    caps = ResolveAdapter(fr.Resolve(fr.Project())).capabilities()
    assert decide(PLAN, "stacked_enable", caps)["via"] == "native"
    assert decide(PLAN, "multicam", caps)["via"] == "xml"
    assert decide(PLAN, "cuts", {**caps, "max_native_events": 2})["via"] == "xml"


# ------------------------------------------------------------------ adapter
def test_read_selection() -> None:
    resolve = fr.podcast("/m/cam1.mp4", "/m/cam2.mp4", "/m/wide.mp4", "/m/zoom.wav")
    sel = ResolveAdapter(resolve).read_selection()
    assert sel["host"]["app"] == "resolve" and sel["host"]["version"] == "20.1.0"
    assert sel["sequence"] == {
        "fps": {"num": 30000, "den": 1001},
        "width": 1280,
        "height": 720,
        "name": "Ep 42",
    }
    assert [
        (Path(c["path"]).name, c["kind"], c["track"], c["record_start_frame"], c["in_frame"])
        for c in sel["clips"]
    ] == [
        ("cam1.mp4", "video", 1, 0, 0),
        ("cam2.mp4", "video", 2, 0, 30),
        ("wide.mp4", "video", 3, 15, 0),
        ("zoom.wav", "audio", 4, 0, 0),
    ]
    assert sel["already_synced"] is True
    assert (
        ResolveAdapter(fr.podcast("/a", "/b", "/c", synced=False)).read_selection()[
            "already_synced"
        ]
        is False
    )


def test_selection_errors() -> None:
    with pytest.raises(EngineError, match="Open a Resolve project"):
        ResolveAdapter(fr.Resolve(None)).read_selection()
    with pytest.raises(EngineError, match="No timeline"):
        ResolveAdapter(fr.Resolve(fr.Project())).read_selection()


@pytest.mark.parametrize("method", ["cuts", "stacked_enable"])
def test_apply_plan_native(method: str) -> None:
    resolve = fr.podcast("/media/demo/cam1.mp4", "/media/demo/cam2.mp4", "/media/demo/wide.mp4")
    project = resolve.project
    assert project is not None
    result = ResolveAdapter(resolve).apply_plan(copy.deepcopy(PLAN), method)
    tl: fr.Timeline = result["timeline"]
    assert result["via"] == "native" and tl.name == PLAN["sequence"]["name"]
    assert project.current is tl
    assert len(project.pool.appends) == 1  # one AppendToTimeline call for everything
    infos = project.pool.appends[0]
    ops = placements(PLAN, method)
    assert len(infos) == len(ops)
    first = infos[0]
    assert first["recordFrame"] == tl.start_frame + ops[0]["start"]
    assert first["startFrame"] == ops[0]["source_in_frame"]
    if adapter_mod.END_INCLUSIVE:
        assert first["endFrame"] - first["startFrame"] + 1 == ops[0]["end"] - ops[0]["start"]
    video = [i for t in tl.tracks["video"] for i in t]
    if method == "stacked_enable":
        assert tl.GetTrackCount("video") == 3
        assert sum(1 for i in video if i.enabled) == len(PLAN["video_events"])
    else:
        assert all(i.enabled for i in video) and len(tl.tracks["video"][0]) == len(
            PLAN["video_events"]
        )


def test_apply_imports_missing_media_and_rejects_duplicate_names() -> None:
    project = fr.Project()
    project.current = fr.Timeline("x")
    resolve = fr.Resolve(project)
    ResolveAdapter(resolve).apply_plan(PLAN, "cuts")
    assert {c.path for c in project.pool.root.subs[0].clips} == {m["path"] for m in PLAN["media"]}
    with pytest.raises(EngineError, match="could not create the timeline"):
        ResolveAdapter(resolve).apply_plan(PLAN, "cuts")


def test_import_xml_and_markers() -> None:
    resolve = fr.podcast("/a", "/b", "/c")
    adapter = ResolveAdapter(resolve)
    r = adapter.import_xml("/x/plan.fcpxml", PLAN)
    assert r["via"] == "xml" and resolve.project is not None
    assert resolve.project.pool.imported_xml == ["/x/plan.fcpxml"]
    n = adapter.add_markers(
        r["timeline"], [{"frame": 120, "color": "yellow", "note": "Check this cut (0.4)"}]
    )
    assert n == 1 and r["timeline"].markers[0][:3] == (120, "Yellow", "Check this cut (0.4)")


# ------------------------------------------------------------------ install
def test_install_and_uninstall(tmp_path: Path) -> None:
    scripts, lib = tmp_path / "Scripts" / "Edit", tmp_path / "data" / "resolve-plugin"
    paths = install(str(scripts), str(lib))
    assert (scripts / SCRIPT_NAME).is_file() and (lib / "multicam_resolve" / "ui.py").is_file()
    assert not list(lib.rglob("__pycache__"))
    assert len(paths) == 2 and len(uninstall(str(scripts), str(lib))) == 2
    assert not (scripts / SCRIPT_NAME).exists()
    assert Path(scripts_dir("darwin")).parts[-3:] == ("Fusion", "Scripts", "Edit")
    assert "Support" in scripts_dir("win32")


def test_scripts_are_python36_syntax() -> None:
    """Resolve may run Python 3.6: no walrus, no match, no PEP 604/585 at runtime."""
    import ast

    for path in (REPO / "apps/plugins/resolve-script").rglob("*.py"):
        tree = ast.parse(path.read_text(), feature_version=(3, 6))
        for node in ast.walk(tree):
            assert not isinstance(node, ast.ImportFrom) or node.module != "__future__", path


# ------------------------------------------------------------------ real engine
@pytest.fixture(scope="module")
def engine(tmp_path_factory: pytest.TempPathFactory) -> Iterator[tuple[Path, dict[str, Path]]]:
    root = tmp_path_factory.mktemp("resolve-e2e")
    media = root / "media"
    subprocess.run(
        [sys.executable, str(REPO / "scripts/make_demo_media.py"), "--seconds", "30", str(media)],
        check=True,
        capture_output=True,
    )
    data = root / "data"
    env = {k: v for k, v in os.environ.items() if k != "MULTICAM_API_TOKEN"}
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "multicam_api.main",
            "--headless",
            "--port",
            "0",
            "--idle-exit",
            "0",
            "--data-dir",
            str(data),
            "--log-level",
            "warning",
        ],
        stdout=subprocess.DEVNULL,
        env=env,
    )
    try:
        deadline = time.monotonic() + 60
        while True:
            info = read_engine_file(str(data))
            if info is not None:
                try:
                    PluginClient(f"http://127.0.0.1:{info['port']}", info["token"]).handshake()
                    break
                except EngineError:
                    pass
            assert time.monotonic() < deadline, "engine did not start"
            time.sleep(0.2)
        yield data, {n: media / f"{n}.mp4" for n in ("cam1", "cam2", "wide")}
    finally:
        proc.terminate()
        proc.wait(timeout=30)


def test_full_flow_against_the_engine(engine: tuple[Path, dict[str, Path]]) -> None:
    data, media = engine
    resolve = fr.podcast(str(media["cam1"]), str(media["cam2"]), str(media["wide"]), synced=False)
    flow = AutoEdit(
        ResolveAdapter(resolve), connector=lambda start=False: connect(start, folder=str(data))
    )
    session = flow.connect()
    assert [c["role"] for c in session["clips"]] == ["speaker", "speaker", "wide"]
    assert session["already_synced"] is False  # all at frame 0: the engine syncs

    seen: list[float] = []
    plan = flow.run(lambda f, m: seen.append(f), vad="energy")
    assert plan["host"] == "resolve" and len(plan["video_events"]) > 1
    assert seen and seen[-1] == 1.0

    result = flow.apply(method="stacked_enable")
    assert result["via"] == "native" and not result["warnings"]
    assert resolve.project is not None and resolve.project.current is result["timeline"]

    flow.setup(preset="punchy")
    plan2 = flow.run(recut=True)
    assert plan2["cutlist_version"] == plan["cutlist_version"] + 1

    xml = flow.apply(via_xml=True)
    assert xml["via"] == "xml"
    imported = resolve.project.pool.imported_xml[-1]
    assert ET.parse(imported).getroot().tag == "fcpxml"


def test_connect_errors(tmp_path: Path) -> None:
    with pytest.raises(EngineError) as exc:
        connect(folder=str(tmp_path))
    assert exc.value.code == "engine_unreachable" and "Start" in exc.value.hint
    opened: list[str] = []
    with pytest.raises(EngineError):
        connect(start=True, folder=str(tmp_path), timeout_s=0.6, opener=opened.append)
    assert opened == ["multicam://start"]
    assert (
        data_dir("darwin", {}, "/Users/r") == "/Users/r/Library/Application Support/Multicam Studio"
    )


# ------------------------------------------------------------------ window
class _Item:
    Text = ""
    Checked = False

    def __init__(self, props: dict[str, Any]) -> None:
        self.__dict__.update(props)
        self.Enabled = True
        self.options: list[str] = []
        self.CurrentIndex = 0

    def AddItems(self, items: list[str]) -> None:  # noqa: N802
        self.options.extend(items)

    def Clear(self) -> None:  # noqa: N802
        self.options = []


class _On:
    def __init__(self) -> None:
        self.handlers: dict[str, dict[str, Any]] = {}

    def __getattr__(self, name: str) -> Any:
        events = self.handlers.setdefault(name, {})

        class Slot:
            def __setattr__(self, event: str, fn: Any) -> None:
                events[event] = fn

        return Slot()


class _UI:
    def __init__(self) -> None:
        self.items: dict[str, _Item] = {}

    def _make(self, props: dict[str, Any]) -> dict[str, Any]:
        if "ID" in props:
            self.items[props["ID"]] = _Item(props)
        return props

    Label = ComboBox = CheckBox = Button = _make

    def VGroup(self, *args: Any) -> Any:  # noqa: N802
        return args

    HGroup = VGroup

    def Timer(self, props: dict[str, Any]) -> Any:  # noqa: N802
        class T:
            def Start(self) -> None:  # noqa: N802
                pass

            def Stop(self) -> None:  # noqa: N802
                pass

        return T()


def test_window_wiring(
    engine: tuple[Path, dict[str, Path]], monkeypatch: pytest.MonkeyPatch
) -> None:
    from multicam_resolve import ui as ui_mod

    data, media = engine
    monkeypatch.setattr(
        ui_mod,
        "AutoEdit",
        lambda adapter: AutoEdit(
            adapter, connector=lambda start=False: connect(start, folder=str(data))
        ),
    )
    resolve = fr.podcast(str(media["cam1"]), str(media["cam2"]), str(media["wide"]))
    assert resolve.project is not None and resolve.project.current is not None
    resolve.project.current.name = "Ep 43"  # a timeline the engine has not seen
    fake = _UI()
    statuses: list[str] = []

    class Window:
        On = _On()

        def GetItems(self) -> dict[str, _Item]:  # noqa: N802
            return fake.items

        def Show(self) -> None:  # noqa: N802
            pass

        def Hide(self) -> None:  # noqa: N802
            pass

    win = Window()

    class Dispatcher:
        On = _On()

        def AddWindow(self, props: dict[str, Any], layout: Any) -> Window:  # noqa: N802
            return win

        def ExitLoop(self) -> None:  # noqa: N802
            pass

        def RunLoop(self) -> None:  # noqa: N802
            tick = self.On.handlers["Tick"]["Timeout"]

            def click(button: str) -> None:
                win.On.handlers[button]["Clicked"](None)
                tick(None)  # the timer disables the buttons while busy
                deadline = time.monotonic() + 120
                while not fake.items[button].Enabled:
                    assert time.monotonic() < deadline
                    time.sleep(0.05)
                    tick(None)
                statuses.append(fake.items["Status"].Text)

            click("Connect")
            wide_list = fake.items["Wide"].options
            assert wide_list[0] == "(no wide camera)" and "wide.mp4" in wide_list
            fake.items["Wide"].CurrentIndex = wide_list.index("wide.mp4")
            fake.items["Preset"].CurrentIndex = 2  # dynamic
            click("Run")
            click("Apply")
            win.On.handlers["MulticamWin"]["Close"](None)

    class Bmd:
        def UIDispatcher(self, ui: Any) -> Dispatcher:  # noqa: N802
            return Dispatcher()

    class Fusion:
        UIManager = fake

    ui_mod.main(resolve, Fusion(), Bmd())
    assert "Pick the wide camera" in statuses[0], statuses
    assert statuses[1].startswith("Plan v"), statuses
    assert statuses[2].startswith('Created timeline "'), statuses
    assert fake.items["Preset"].options[2] == "Dynamic"


def _plan_with_mic() -> tuple[dict[str, Any], str]:
    plan = copy.deepcopy(PLAN)
    mic_id = "00000000-0000-0000-0000-00000000a1c0"
    plan["media"].append(
        {
            **plan["media"][0],
            "clip_id": mic_id,
            "path": "/media/demo/zoom.wav",
            "name": "zoom.wav",
            "label": "zoom",
            "fps": {"num": 100, "den": 1},
            "width": 0,
            "height": 0,
            "angle": None,
            "video_track": None,
            "audio_track": len(plan["audio_tracks"]) + 1,
            "sample_rate": 48000,
        }
    )
    plan["audio_tracks"].append(
        {
            "index": len(plan["audio_tracks"]) + 1,
            "clip_id": mic_id,
            "gain_db": 0.0,
            "pieces": [
                {
                    "start": 0,
                    "end": 300,
                    "clip_id": mic_id,
                    "source_in_frame": 1000,
                    "source_in_sample": 480000,
                    "source_in_ticks": 0,
                }
            ],
        }
    )
    return plan, mic_id


def test_sound_only_mic_frames_follow_resolve_clip_rate() -> None:
    plan, _ = _plan_with_mic()
    resolve = fr.podcast("/media/demo/cam1.mp4", "/media/demo/cam2.mp4", "/media/demo/wide.mp4")
    ResolveAdapter(resolve).apply_plan(plan, "cuts")
    assert resolve.project is not None
    mic = next(
        i for i in resolve.project.pool.appends[0] if i["mediaPoolItem"].path.endswith(".wav")
    )
    # 10 s into the file at the clip's rate (project rate 29.97 here), 300 frames long
    assert mic["startFrame"] == 300 and mic["mediaType"] == 2
    assert mic["endFrame"] - mic["startFrame"] + 1 == 300


def test_stacked_does_not_disable_by_position_when_resolve_skips(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolve = fr.podcast("/media/demo/cam1.mp4", "/media/demo/cam2.mp4", "/media/demo/wide.mp4")
    assert resolve.project is not None
    pool = resolve.project.pool
    real = pool.AppendToTimeline
    monkeypatch.setattr(pool, "AppendToTimeline", lambda infos: real(infos)[1:])  # one skipped
    result = ResolveAdapter(resolve).apply_plan(PLAN, "stacked_enable")
    assert any("Not disabling" in w for w in result["warnings"])
    assert all(i.enabled for t in result["timeline"].tracks["video"] for i in t)
