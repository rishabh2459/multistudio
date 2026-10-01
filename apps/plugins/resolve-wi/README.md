# Multicam Studio for DaVinci Resolve Studio — Workflow Integration

Electron plugin for *Workspace → Workflow Integrations* (Resolve **Studio** only).
It shows the same panel as Premiere (`@multicam/plugin-core`); the Resolve object
lives in the plugin's main process and the panel reaches it over IPC (`bridge.ts`).

## Build and install (Mac / Windows)

```bash
pnpm install && pnpm --filter @multicam/resolve-wi build
```

Copy this folder (`manifest.xml`, `index.html`, `dist/`) plus Resolve's own
`WorkflowIntegration.node` (from *DaVinci Resolve/Developer/Workflow Integrations/Examples*)
into:

- macOS: `/Library/Application Support/Blackmagic Design/DaVinci Resolve/Workflow Integration Plugins/Multicam Studio/`
- Windows: `%PROGRAMDATA%\Blackmagic Design\DaVinci Resolve\Support\Workflow Integration Plugins\Multicam Studio\`

Restart Resolve Studio → *Workspace → Workflow Integrations → Multicam Studio*.

Spike items are the same as the Resolve script's (see `../resolve-script/README.md`),
plus: do WI API calls return promises (handled either way)?
