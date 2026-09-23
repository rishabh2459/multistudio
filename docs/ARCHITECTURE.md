# Architecture Notes

The full picture lives in `PROJECT_PLAN.md` §3. This file records the rules
that code must follow.

## Layers

```
apps/desktop (Electron, Phase 6)
   └── apps/web (Next.js static export, Phase 5) ── uses ──► packages/types
          │ HTTP + SSE
          ▼
apps/api (FastAPI, Phase 4) ── jobs ──► engine (multicam_engine)
```

* `engine` never imports web, API, or desktop code.
* `apps/api` owns persistence and job orchestration; it calls the engine.
* `packages/types` is **generated** from the engine's Pydantic models.

## Contracts

**Data model:** `engine/src/multicam_engine/models` is the single source of truth.
Flow: Python models → `schemas/multicam.schema.json` → `packages/types/src/generated/models.ts`.
Run `make schemas` after any model change; CI fails if generated files are stale.

**Time:** timeline positions are integer frames (at the project output rate),
audio positions are integer samples, ground truth is integer milliseconds.
Floats are never used for positions. Conversions go through
`multicam_engine.models.time` with an explicit rounding mode (default: half-up).

**Timeline ranges** are half-open: `[start_frame, end_frame)`.

**Sync sign convention:** `offset = position_in_clip − position_in_reference`.
Positive means the clip started recording earlier than the reference.
`drift_ppm` positive means the clip's clock runs fast relative to the reference.

**Versioning:** every persisted document carries `schema_version`. Breaking
changes bump it and ship a migration.

## Dependencies

Every new dependency must pass the license policy in `PROJECT_PLAN.md` §5
and be recorded in `DECISIONS.md`.
