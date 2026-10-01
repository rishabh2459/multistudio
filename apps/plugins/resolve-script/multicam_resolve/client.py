"""Plugin API v1 client + engine discovery, standard library only (Python 3.6+)."""

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Dict, Mapping, Optional, Tuple

API = "/api/plugin/v1"
TOKEN_HEADER = "X-Multicam-Token"
START_URL = "multicam://start"
SUPPORTED_MAJOR = 1

Json = Dict[str, Any]


class EngineError(Exception):
    """A failure with a stable code (same codes as the engine), message and hint."""

    def __init__(self, code: str, message: str, hint: str = "", status: int = 0) -> None:
        super().__init__(message)
        self.code, self.message, self.hint, self.status = code, message, hint, status

    def __str__(self) -> str:
        return self.message + (" - " + self.hint if self.hint else "")


def data_dir(
    platform: str = sys.platform,
    env: Optional[Mapping[str, str]] = None,
    home: Optional[str] = None,
) -> str:
    """The engine's data folder (same rule as multicam_api/config.py)."""
    env = os.environ if env is None else env
    home = home or os.path.expanduser("~")
    if env.get("MULTICAM_DATA_DIR"):
        return env["MULTICAM_DATA_DIR"]
    if platform == "darwin":
        return os.path.join(home, "Library", "Application Support", "Multicam Studio")
    if platform == "win32":
        base = env.get("APPDATA") or os.path.join(home, "AppData", "Roaming")
        return os.path.join(base, "Multicam Studio")
    base = env.get("XDG_DATA_HOME") or os.path.join(home, ".local", "share")
    return os.path.join(base, "multicam-studio")


def read_engine_file(folder: Optional[str] = None) -> Optional[Json]:
    path = os.path.join(folder or data_dir(), "engine.json")
    try:
        with open(path, encoding="utf-8") as fh:
            info = json.load(fh)
    except (OSError, ValueError):
        return None
    if isinstance(info, dict) and isinstance(info.get("port"), int) and info.get("token"):
        return info
    return None


def open_url(url: str) -> None:
    """Open multicam://start with the OS (the desktop app starts the engine)."""
    if sys.platform == "darwin":
        subprocess.Popen(["open", url])
    elif sys.platform == "win32":
        os.startfile(url)  # type: ignore[attr-defined]
    else:
        subprocess.Popen(["xdg-open", url])


class PluginClient:
    def __init__(self, base_url: str, token: str, timeout: float = 30.0) -> None:
        self.base_url, self.token, self.timeout = base_url.rstrip("/"), token, timeout

    def request(self, method: str, path: str, body: Optional[Json] = None) -> Any:
        data = None if body is None else json.dumps(body).encode("utf-8")
        req = urllib.request.Request(self.base_url + API + path, data=data, method=method)
        req.add_header(TOKEN_HEADER, self.token)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise _error(exc) from None
        except (urllib.error.URLError, OSError) as exc:
            raise EngineError(
                "engine_unreachable",
                f"cannot reach the engine at {self.base_url} ({exc})",
                "Start Multicam Studio, then try again.",
            ) from None

    # -- endpoints
    def handshake(self) -> Json:
        hs = self.request("GET", "/handshake")
        major = int(str(hs.get("api_version", "0")).split(".")[0])
        if major != SUPPORTED_MAJOR:
            raise EngineError(
                "engine_incompatible",
                "the engine speaks plugin API {}".format(hs.get("api_version")),
                "Update Multicam Studio and this script to matching versions.",
            )
        return hs  # type: ignore[no-any-return]

    def create_session(self, body: Json) -> Json:
        return self.request("POST", "/sessions", body)  # type: ignore[no-any-return]

    def get_session(self, session_id: str) -> Json:
        return self.request("GET", "/sessions/" + session_id)  # type: ignore[no-any-return]

    def setup(self, session_id: str, body: Json) -> Json:
        return self.request("PATCH", f"/sessions/{session_id}/setup", body)  # type: ignore[no-any-return]

    def run(self, session_id: str, body: Optional[Json] = None) -> Json:
        return self.request("POST", f"/sessions/{session_id}/run", body or {})  # type: ignore[no-any-return]

    def editplan(
        self,
        session_id: str,
        host: str = "resolve",
        method: Optional[str] = None,
        version: Optional[int] = None,
    ) -> Json:
        q = {"host": host}
        if method:
            q["method"] = method
        if version:
            q["version"] = str(version)
        path = f"/sessions/{session_id}/editplan?{urllib.parse.urlencode(q)}"
        return self.request("GET", path)  # type: ignore[no-any-return]

    def export(self, session_id: str, fmt: str = "fcpxml", version: Optional[int] = None) -> Json:
        q = {"format": fmt}
        if version:
            q["version"] = str(version)
        path = f"/sessions/{session_id}/export?{urllib.parse.urlencode(q)}"
        return self.request("GET", path)  # type: ignore[no-any-return]

    def wait(
        self,
        session_id: str,
        job_id: str,
        on_progress: Optional[Callable[[float, str], None]] = None,
        poll_s: float = 0.5,
        timeout_s: float = 4 * 3600,
    ) -> Json:
        """Poll until the job ends; returns the session (with ``plan``)."""
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            s = self.get_session(session_id)
            job = s.get("job") or {}
            if job.get("id") == job_id:
                if on_progress:
                    on_progress(
                        float(job.get("progress", 0)), job.get("message") or job.get("stage") or ""
                    )
                if job.get("status") == "succeeded":
                    return s
                if job.get("status") in ("failed", "cancelled"):
                    raise EngineError("job_failed", job.get("error") or "the auto edit failed")
            time.sleep(poll_s)
        raise EngineError("job_failed", "the auto edit took too long")


def _error(exc: "urllib.error.HTTPError") -> EngineError:
    try:
        body = json.loads(exc.read().decode("utf-8"))
    except (ValueError, OSError):
        body = {}
    if exc.code == 401:
        return EngineError("unauthorized", "the engine refused the token", "Reconnect.", 401)
    if isinstance(body, dict) and "code" in body:
        return EngineError(
            str(body["code"]), str(body.get("message", "")), str(body.get("hint", "")), exc.code
        )
    return EngineError("host_error", f"engine answered {exc.code}", "", exc.code)


def connect(
    start: bool = False,
    folder: Optional[str] = None,
    timeout_s: float = 20.0,
    opener: Callable[[str], None] = open_url,
) -> Tuple[PluginClient, Json]:
    """Connect to the running engine; with ``start`` open multicam://start and wait."""
    info = read_engine_file(folder)
    if info is None and start:
        opener(START_URL)
        deadline = time.monotonic() + timeout_s
        while info is None and time.monotonic() < deadline:
            time.sleep(0.5)
            info = read_engine_file(folder)
    if info is None:
        raise EngineError(
            "engine_unreachable",
            "Multicam Studio is not running",
            "Open Multicam Studio (or press Start engine), then try again.",
        )
    client = PluginClient("http://127.0.0.1:{}".format(info["port"]), str(info["token"]))
    last: Optional[EngineError] = None
    deadline = time.monotonic() + (timeout_s if start else 0)
    while True:
        try:
            return client, client.handshake()
        except EngineError as exc:
            last = exc
            if exc.code != "engine_unreachable" or time.monotonic() > deadline:
                raise last from None
            time.sleep(0.5)
