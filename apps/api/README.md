# multicam-api

Local backend for Multicam Studio (plan Phase 4). FastAPI on `127.0.0.1`, SQLite
database, Huey job queue (SQLite storage) running inside the same process.
The desktop app (Phase 6) starts it as a sidecar; the UI (Phase 5) talks to it.

```bash
uv run multicam-api --port 8765          # then open http://127.0.0.1:8765/docs
uv run python scripts/api_demo.py cam1.mp4 cam2.mp4   # whole pipeline via the API
```

| Module | Purpose |
|---|---|
| `config` | Settings from environment (`MULTICAM_DATA_DIR`, `MULTICAM_API_TOKEN`, ...) |
| `db` | SQLAlchemy models, session, Alembic migrations (run automatically at startup) |
| `infra` | `StorageBackend` + `JobQueue` interfaces with local implementations |
| `routers` | HTTP endpoints (`/api/...`) |
| `jobs` | What each job kind does (probe, sync, analyze, decide, auto, render) |
| `services` | Row <-> engine model conversion, file checks, cache keys |
