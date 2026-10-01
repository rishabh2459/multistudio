# @multicam/plugin-core

Everything the NLE plugins share (PLUGIN_PLAN PL3). A host plugin only writes a
`HostAdapter` (Premiere UXP, Resolve WI) and renders `<AutoEditPanel>`.

| Module | What |
|---|---|
| `client.ts` | Typed Plugin API v1 client (`fetch` only: UXP, Electron, Node); `{code, message, hint}` errors as `PluginError` |
| `engine.ts` | Find the engine through `engine.json`, start it with `multicam://start`, version check |
| `events.ts` | Follow a run: SSE over streaming `fetch`, falls back to polling |
| `session.ts` | `AutoEditController`: idle → connecting → setup → running → review → applying → applied \| error |
| `plan.ts` | Exact ticks, native-vs-XML decision (7.2 / Rule C), placements per method, preview lanes |
| `setup.ts` | Role / name guesses, camera cards ⇄ layout |
| `adapter.ts` | `HostAdapter` + `HostCaps` |
| `ui/` | React views with injectable primitives (`htmlPrimitives`; Premiere passes Spectrum ones) |
| `test/fake-host.ts` | In-memory NLE (one undo step per apply) |

Tests: `pnpm --filter @multicam/plugin-core test`. `flow.test.ts` also starts a real
headless engine (`uv run python -m multicam_api.main --headless`) and skips when the
engine cannot be imported; override the command with `MULTICAM_TEST_ENGINE='["python3"]'`.
