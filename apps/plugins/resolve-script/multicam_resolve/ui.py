"""Small window in Resolve (Fusion UIManager): connect, style, auto edit, apply."""

import threading
from typing import Any, Dict, List

from .adapter import ResolveAdapter
from .client import EngineError
from .flow import AutoEdit

PRESETS = [
    ("balanced", "Balanced"),
    ("calm", "Calm (long shots)"),
    ("dynamic", "Dynamic"),
    ("punchy", "Punchy (reels)"),
]
METHODS = [
    ("stacked_enable", "Stacked tracks (enable/disable)"),
    ("cuts", "Cuts on one track"),
    ("multicam", "Multicam clip (via FCPXML)"),
]


NO_WIDE = "(no wide camera)"


def wide_roles(cameras: List[Any], index: int) -> List[Dict[str, Any]]:
    """Roles for the video clips: the picked one is the wide shot, the rest speakers.
    ``index`` 0 = no wide camera. Empty before Connect."""
    roles = []
    for i, (clip_id, _name, _was_wide) in enumerate(cameras, start=1):
        roles.append({"clip_id": clip_id, "role": "wide" if i == index else "speaker"})
    return roles


def current_roles(session: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [
        {"clip_id": c["clip_id"], "role": "wide" if c["role"] == "wide" else "speaker"}
        for c in session.get("clips", [])
        if c.get("kind") == "video"
    ]


def main(resolve: Any, fusion: Any, bmd: Any) -> None:
    ui = fusion.UIManager
    disp = bmd.UIDispatcher(ui)
    flow = AutoEdit(ResolveAdapter(resolve))
    state: Dict[str, Any] = {
        "busy": False,
        "status": "Open the timeline with your cameras, then Connect.",
    }

    win = disp.AddWindow(
        {"ID": "MulticamWin", "WindowTitle": "Multicam Studio", "Geometry": [200, 200, 440, 330]},
        ui.VGroup(
            {"Spacing": 6},
            [
                ui.Label(
                    {
                        "ID": "Status",
                        "Text": state["status"],
                        "WordWrap": True,
                        "MinimumSize": [400, 60],
                    }
                ),
                ui.HGroup(
                    [ui.Label({"Text": "Wide camera", "Weight": 0.25}), ui.ComboBox({"ID": "Wide"})]
                ),
                ui.HGroup(
                    [ui.Label({"Text": "Style", "Weight": 0.25}), ui.ComboBox({"ID": "Preset"})]
                ),
                ui.HGroup(
                    [ui.Label({"Text": "Result as", "Weight": 0.25}), ui.ComboBox({"ID": "Method"})]
                ),
                ui.CheckBox(
                    {"ID": "ViaXml", "Text": "Import as FCPXML (safest)", "Checked": False}
                ),
                ui.HGroup(
                    [
                        ui.Button({"ID": "Connect", "Text": "Connect"}),
                        ui.Button({"ID": "Start", "Text": "Start engine"}),
                        ui.Button({"ID": "Run", "Text": "Auto Edit"}),
                        ui.Button({"ID": "Apply", "Text": "Apply"}),
                    ]
                ),
            ],
        ),
    )
    items = win.GetItems()
    items["Preset"].AddItems([label for _, label in PRESETS])
    items["Method"].AddItems([label for _, label in METHODS])
    items["Wide"].AddItems([NO_WIDE])
    # Video clips of the session (filled after Connect; the timer copies them into
    # the "Wide camera" list, because UI calls must stay on the UI thread).
    state["cameras"] = []
    state["cameras_shown"] = None

    def show(text: str) -> None:
        state["status"] = text
        items["Status"].Text = text

    def background(work: Any, done_text: Any) -> None:
        """Long steps run in a thread; a UI timer copies the status into the label."""
        if state["busy"]:
            return
        state["busy"] = True

        def target() -> None:
            try:
                state["status"] = done_text(work())
            except EngineError as exc:
                state["status"] = "{}{}".format(exc.message, "\n" + exc.hint if exc.hint else "")
            except Exception as exc:
                state["status"] = f"Error: {exc}"
            finally:
                state["busy"] = False

        threading.Thread(target=target, daemon=True).start()

    def progress(fraction: float, message: str) -> None:
        state["status"] = f"Working… {fraction:.0%}  {message}"

    def summary(plan: Dict[str, Any]) -> str:
        cuts = max(0, len(plan["video_events"]) - 1)
        low = len([m for m in plan.get("markers", []) if m.get("kind") == "low_confidence"])
        return "Plan v{}: {} cuts{}. Press Apply.".format(
            plan["cutlist_version"], cuts, f", {low} to check" if low else ""
        )

    def on_connect(start: bool) -> None:
        def work() -> Dict[str, Any]:
            return flow.connect(start=start)

        def done(session: Dict[str, Any]) -> str:
            names: List[str] = [c["name"] for c in session["clips"]]
            state["cameras"] = [
                (c["clip_id"], c["name"], c["role"] == "wide")
                for c in session["clips"]
                if c["kind"] == "video"
            ]
            if flow.plan:
                return "Reconnected to {}. {}".format(session["name"], summary(flow.plan))
            return "{}: {} clips ({}). Pick the wide camera and a style, then Auto Edit.".format(
                session["name"], len(names), ", ".join(names)
            )

        show("Connecting…")
        background(work, done)

    def on_run(_: Any) -> None:
        preset = PRESETS[int(items["Preset"].CurrentIndex)][0]
        method = METHODS[int(items["Method"].CurrentIndex)][0]
        roles = wide_roles(state["cameras"], int(items["Wide"].CurrentIndex))

        def work() -> Dict[str, Any]:
            session = flow.session or {}
            changed = roles != current_roles(session)
            if changed:  # who is who changed: the whole edit must be redone
                flow.plan = None
            recut = flow.plan is not None
            flow.setup(preset=preset, method=method, **({"roles": roles} if roles else {}))
            return flow.run(progress, recut=recut)

        show("Starting…")
        background(work, summary)

    def on_apply(_: Any) -> None:
        method = METHODS[int(items["Method"].CurrentIndex)][0]
        via_xml = bool(items["ViaXml"].Checked)

        def work() -> Dict[str, Any]:
            return flow.apply(method=method, via_xml=via_xml, on_progress=progress)

        def done(result: Dict[str, Any]) -> str:
            text = 'Created timeline "{}" ({}).'.format(result["name"], result["via"])
            if result["markers"]:
                text += " {} markers to check.".format(result["markers"])
            return "\n".join([text, *result["warnings"]])

        background(work, done)

    timer = ui.Timer({"ID": "Tick", "Interval": 300})

    def on_tick(_: Any) -> None:
        cams = state["cameras"]
        if cams != state["cameras_shown"]:
            state["cameras_shown"] = list(cams)
            items["Wide"].Clear()
            items["Wide"].AddItems([NO_WIDE] + [name for _, name, _ in cams])
            chosen = [i for i, (_, _, wide) in enumerate(cams, start=1) if wide]
            items["Wide"].CurrentIndex = chosen[0] if chosen else 0
        if items["Status"].Text != state["status"]:
            items["Status"].Text = state["status"]
        for button in ("Connect", "Start", "Run", "Apply"):
            items[button].Enabled = not state["busy"]

    def on_close(_: Any) -> None:
        timer.Stop()
        disp.ExitLoop()

    win.On.MulticamWin.Close = on_close
    win.On.Connect.Clicked = lambda ev: on_connect(False)
    win.On.Start.Clicked = lambda ev: on_connect(True)
    win.On.Run.Clicked = on_run
    win.On.Apply.Clicked = on_apply
    disp.On.Tick.Timeout = on_tick
    timer.Start()
    win.Show()
    disp.RunLoop()
    win.Hide()
