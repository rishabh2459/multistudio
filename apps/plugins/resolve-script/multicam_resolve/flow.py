"""The auto-edit flow without UI: connect -> session -> run -> plan -> apply."""

from typing import Any, Callable, Dict, Optional

from .adapter import ResolveAdapter
from .client import EngineError, PluginClient, connect
from .plan import decide, default_roles

Json = Dict[str, Any]
Progress = Callable[[float, str], None]


class AutoEdit:
    def __init__(self, adapter: ResolveAdapter, connector: Callable[..., Any] = connect) -> None:
        self.adapter = adapter
        self.connector = connector
        self.client: Optional[PluginClient] = None
        self.handshake: Optional[Json] = None
        self.session: Optional[Json] = None
        self.plan: Optional[Json] = None
        self.applied: Optional[Json] = None

    def _client(self) -> PluginClient:
        if self.client is None:
            raise EngineError("engine_unreachable", "not connected", "Press Connect.")
        return self.client

    def _session_id(self) -> str:
        if self.session is None:
            raise EngineError("setup_required", "no clips yet", "Press Connect.")
        return str(self.session["id"])

    def connect(self, start: bool = False) -> Json:
        """Find the engine and send the current timeline's clips."""
        self.client, self.handshake = self.connector(start=start)
        return self.load_selection()

    def load_selection(self) -> Json:
        client = self._client()
        session = client.create_session(self.adapter.read_selection())
        if not session.get("reused"):
            session = client.setup(session["id"], {"roles": default_roles(session)})
        self.session = session
        self.plan = None
        if session.get("reused") and session.get("plan"):
            self.plan = client.editplan(session["id"], host="resolve")
        return session

    def setup(self, **body: Any) -> Json:
        self.session = self._client().setup(self._session_id(), body)
        return self.session

    def run(
        self, on_progress: Optional[Progress] = None, recut: bool = False, **params: Any
    ) -> Json:
        client = self._client()
        sid = self._session_id()
        body: Json = {"steps": ["decide"]} if recut else dict(params)
        job = client.run(sid, body)
        self.session = client.wait(sid, str(job["job_id"]), on_progress)
        self.plan = client.editplan(sid, host="resolve")
        return self.plan

    def apply(
        self,
        method: Optional[str] = None,
        via_xml: bool = False,
        on_progress: Optional[Progress] = None,
    ) -> Json:
        if self.plan is None:
            raise EngineError("no_plan", "no edit to apply yet", "Run Auto Edit first.")
        plan = self.plan
        method = method or plan.get("method") or "stacked_enable"
        caps = self.adapter.capabilities()
        decision = (
            {"via": "xml", "method": method, "reason": "requested"}
            if via_xml
            else decide(plan, method, caps)
        )
        if on_progress:
            on_progress(0.1, decision["reason"])
        if decision["via"] == "xml":
            result = self._via_xml(plan, decision["method"])
        else:
            try:
                result = self.adapter.apply_plan(plan, decision["method"])
            except EngineError:
                raise
            except Exception as exc:
                result = self._via_xml(plan, decision["method"])
                result["warnings"].append(f"native apply failed ({exc}); imported FCPXML")
        if plan.get("markers") and not result["markers"]:
            result["markers"] = self.adapter.add_markers(result["timeline"], plan["markers"])
        self.applied = result
        if on_progress:
            on_progress(1.0, "done")
        return result

    def _via_xml(self, plan: Json, method: str) -> Json:
        exp = self._client().export(
            self._session_id(), "fcpxml", plan.get("cutlist_version"), method=method
        )
        return self.adapter.import_xml(exp["path"], plan)
