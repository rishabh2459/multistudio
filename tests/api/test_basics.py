"""System endpoints, auth, projects, database migrations, recovery, storage."""

from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from fastapi.testclient import TestClient

from multicam_api.app import create_app, recover_jobs
from multicam_api.config import Settings
from multicam_api.db.migrate import upgrade
from multicam_api.db.models import Base, JobRow, ProjectRow
from multicam_api.db.session import Database
from multicam_api.infra.queue import CancelRegistry
from multicam_api.infra.storage import LocalStorage
from multicam_api.main import bind_socket

from .conftest import new_project


def test_health_and_info(api: TestClient) -> None:
    assert api.get("/api/system/health").json()["status"] == "ok"
    info = api.get("/api/system/info").json()
    assert info["encoders_h264"] is None
    assert "youtube-1080p" in info["render_presets"]
    assert Path(info["data_dir"]).is_dir()


def test_info_lists_working_encoders(api: TestClient, ffmpeg: str) -> None:
    info = api.get("/api/system/info", params={"encoders": True}).json()
    assert info["ffmpeg"] and info["encoders_h264"]


def test_token_protects_the_api(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path / "d", token="s3cret")
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/system/health").status_code == 200  # always open
        assert client.get("/api/projects").status_code == 401
        assert client.get("/api/projects", headers={"X-Multicam-Token": "nope"}).status_code == 401
        assert (
            client.get("/api/projects", headers={"X-Multicam-Token": "s3cret"}).status_code == 200
        )
        assert client.get("/api/projects", params={"token": "s3cret"}).status_code == 200
        # The browser UI must be able to read the 401 (CORS headers present).
        origin = {"Origin": "http://localhost:3000"}
        denied = client.get("/api/projects", headers=origin)
        assert denied.status_code == 401
        assert denied.headers["access-control-allow-origin"] == "http://localhost:3000"
        preflight = client.options(
            "/api/projects",
            headers={**origin, "Access-Control-Request-Method": "PATCH",
                     "Access-Control-Request-Headers": "x-multicam-token"},
        )  # fmt: skip
        assert preflight.status_code == 200


def test_project_crud(api: TestClient, settings: Settings) -> None:
    pid = new_project(api, "Episode 42")
    project = api.get(f"/api/projects/{pid}").json()
    assert project["name"] == "Episode 42" and project["preset"] == "balanced"
    assert project["clips"] == [] and project["cutlist_version"] is None
    assert project["output"]["fps"] == {"num": 30000, "den": 1001}
    assert not project["output_custom"]

    patched = api.patch(f"/api/projects/{pid}", json={"name": "Ep 42", "preset": "dynamic",
        "output": {"fps": {"num": 25, "den": 1}, "width": 1280, "height": 720}}).json()  # fmt: skip
    assert patched["name"] == "Ep 42" and patched["preset"] == "dynamic"
    assert patched["output_custom"] and patched["output"]["width"] == 1280

    listing = api.get("/api/projects").json()
    assert [p["id"] for p in listing] == [pid] and listing[0]["clip_count"] == 0

    storage = settings.storage_dir / pid
    LocalStorage(settings.storage_dir).artifact_path(UUID(pid), "x.txt").write_text("x")
    assert api.delete(f"/api/projects/{pid}").status_code == 204
    assert not storage.exists()
    assert api.get(f"/api/projects/{pid}").status_code == 404


def test_validation_and_not_found(api: TestClient) -> None:
    assert api.post("/api/projects", json={"name": ""}).status_code == 422
    assert api.post("/api/projects", json={"name": "x", "extra": 1}).status_code == 422
    assert api.get(f"/api/projects/{uuid4()}").status_code == 404
    assert api.get("/api/projects/not-a-uuid").status_code == 422
    pid = new_project(api)
    bad_ref = api.patch(f"/api/projects/{pid}", json={"reference_clip_id": str(uuid4())})
    assert bad_ref.status_code == 422
    assert api.get(f"/api/projects/{pid}/cutlist").status_code == 404
    assert api.get(f"/api/jobs/{uuid4()}").status_code == 404
    resp = api.post(
        f"/api/projects/{pid}/jobs", json={"kind": "decide", "params": {"preset": "wild"}}
    )
    assert resp.status_code == 422
    resp = api.post(f"/api/projects/{pid}/jobs", json={"kind": "render", "params": {"x": 1}})
    assert resp.status_code == 422


def test_migrations_match_models(tmp_path: Path) -> None:
    db = Database(tmp_path / "m.db")
    upgrade(db.engine)
    upgrade(db.engine)  # idempotent
    with db.engine.connect() as conn:
        assert compare_metadata(MigrationContext.configure(conn), Base.metadata) == []
    db.dispose()


class _FakeQueue:
    def __init__(self) -> None:
        self.submitted: list[UUID] = []

    def submit(self, job_id: UUID) -> None:
        self.submitted.append(job_id)


def test_recover_jobs_after_crash(tmp_path: Path) -> None:
    db = Database(tmp_path / "r.db")
    upgrade(db.engine)
    ids = {status: str(uuid4()) for status in ("running", "queued", "succeeded")}
    with db.transaction() as s:
        s.add(ProjectRow(id="p", name="p", preset="balanced", output={}))
        s.flush()
        for status, jid in ids.items():
            s.add(JobRow(id=jid, project_id="p", kind="sync", status=status, params={}))
    queue = _FakeQueue()
    assert recover_jobs(db, queue) == 1  # type: ignore[arg-type]
    assert queue.submitted == [UUID(ids["queued"])]
    with db.session() as s:
        crashed = s.get(JobRow, ids["running"])
        assert crashed is not None and crashed.status == "failed"
        assert "interrupted" in (crashed.error or "")
    db.dispose()


def test_storage_and_cancel_registry(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path)
    pid = uuid4()
    path = storage.artifact_path(pid, "analysis.npz")
    assert path.parent.is_dir() and path.parent.parent.name == str(pid)
    assert storage.exports_dir(pid).is_dir()
    for bad in ("../x", "a/b", ".hidden"):
        with pytest.raises(ValueError):
            storage.artifact_path(pid, bad)
    reg = CancelRegistry()
    job = uuid4()
    assert not reg.event(job).is_set()
    reg.cancel(job)
    assert reg.event(job).is_set()
    reg.forget(job)
    assert not reg.event(job).is_set()


def test_bind_socket_any_port() -> None:
    sock = bind_socket(0)
    try:
        host, port = sock.getsockname()
        assert host == "127.0.0.1" and port > 0
    finally:
        sock.close()
