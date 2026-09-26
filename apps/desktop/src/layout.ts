/**
 * Where things are: the web UI files, the engine executable, ffmpeg.
 *
 * Packaged app (electron-builder `extraResources`):
 *   <resources>/web/                 static UI (apps/web/out)
 *   <resources>/backend/multicam-api  PyInstaller one-folder build (+ ffmpeg, ffprobe)
 * Development (`pnpm --filter @multicam/desktop dev`): the repo's apps/web/out
 * and `uv run multicam-api`. Environment overrides:
 *   MULTICAM_WEB_OUT   folder with the static UI
 *   MULTICAM_WEB_URL   load the UI from a dev server instead (e.g. next dev)
 *   MULTICAM_BACKEND   JSON array command, e.g. ["python3","-m","multicam_api.main"]
 */
import path from 'node:path';

import type { BackendCommand } from './sidecar';

export interface Layout {
  packaged: boolean;
  webRoot: string;
  webUrl: string | null;
  backend: BackendCommand;
  repoRoot: string | null;
}

export interface LayoutInput {
  packaged: boolean;
  resourcesPath: string;
  appPath: string;
  platform: NodeJS.Platform;
  env: Record<string, string | undefined>;
  isFile: (p: string) => boolean;
}

function parseCommand(json: string): string[] {
  const value: unknown = JSON.parse(json);
  if (!Array.isArray(value) || value.length === 0 || !value.every((v) => typeof v === 'string')) {
    throw new Error('MULTICAM_BACKEND must be a JSON array of strings');
  }
  return value as string[];
}

export function resolveLayout(input: LayoutInput): Layout {
  const { env, platform } = input;
  const exe = (name: string) => (platform === 'win32' ? `${name}.exe` : name);

  if (input.packaged) {
    const backendDir = path.join(input.resourcesPath, 'backend');
    const tools: Record<string, string> = {};
    for (const tool of ['ffmpeg', 'ffprobe']) {
      const file = path.join(backendDir, exe(tool));
      if (input.isFile(file)) tools[`MULTICAM_${tool.toUpperCase()}`] = file;
    }
    return {
      packaged: true,
      webRoot: path.join(input.resourcesPath, 'web'),
      webUrl: null,
      backend: { command: path.join(backendDir, exe('multicam-api')), args: [], env: tools },
      repoRoot: null,
    };
  }

  const repoRoot = path.resolve(input.appPath, '..', '..');
  const [command, ...args] = env.MULTICAM_BACKEND
    ? parseCommand(env.MULTICAM_BACKEND)
    : ['uv', 'run', 'multicam-api'];
  return {
    packaged: false,
    webRoot: env.MULTICAM_WEB_OUT ?? path.join(repoRoot, 'apps', 'web', 'out'),
    webUrl: env.MULTICAM_WEB_URL ?? null,
    backend: { command: command!, args, cwd: repoRoot },
    repoRoot,
  };
}
