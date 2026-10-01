/**
 * The desktop app's side of NLE-plugin discovery (PLUGIN_PLAN 3.2, D75).
 *
 * - `multicam://start` (opened by a plugin's "Start engine" button) launches the
 *   engine headless when the app is not running; when it is, the app's own engine
 *   already serves plugins (it runs with `--discovery`).
 * - A headless engine owns `engine.json` in the data folder. If the app starts
 *   while one runs, the app asks it to shut down (`POST /api/system/shutdown`) and
 *   starts its own, so there is only ever one engine per data folder.
 *
 * No Electron imports: unit-tested with plain Node.
 */
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';

import type { BackendCommand } from './sidecar';

export const URL_SCHEME = 'multicam';
export const APP_DIR_NAME = 'Multicam Studio';

export type MulticamUrl = { action: 'start' } | { action: 'open'; sessionId: string | null };

/** `multicam://start`, `multicam://open?session=<id>`; anything else -> null. */
export function parseMulticamUrl(raw: string): MulticamUrl | null {
  let url: URL;
  try {
    url = new URL(raw);
  } catch {
    return null;
  }
  if (url.protocol !== `${URL_SCHEME}:`) return null;
  // multicam://start -> host "start"; multicam:start -> pathname "start"
  const action = (url.host || url.pathname.replace(/^\/+/, '')).toLowerCase();
  if (action === 'start') return { action: 'start' };
  if (action === 'open') {
    const id = url.searchParams.get('session');
    return { action: 'open', sessionId: id && /^[0-9a-f-]{36}$/i.test(id) ? id : null };
  }
  return null;
}

/** The URL the OS passed on the command line (Windows / Linux), if any. */
export function findUrlInArgv(argv: readonly string[]): MulticamUrl | null {
  for (const arg of argv) {
    if (arg.toLowerCase().startsWith(`${URL_SCHEME}:`)) {
      const parsed = parseMulticamUrl(arg);
      if (parsed) return parsed;
    }
  }
  return null;
}

/** Same rules as the engine's `default_data_dir()` (multicam_api/config.py). */
export function defaultDataDir(
  platform: NodeJS.Platform,
  env: Record<string, string | undefined>,
  home: string,
): string {
  if (env.MULTICAM_DATA_DIR) return env.MULTICAM_DATA_DIR;
  if (platform === 'darwin') return path.join(home, 'Library', 'Application Support', APP_DIR_NAME);
  if (platform === 'win32') {
    return path.join(env.APPDATA ?? path.join(home, 'AppData', 'Roaming'), APP_DIR_NAME);
  }
  return path.join(env.XDG_DATA_HOME ?? path.join(home, '.local', 'share'), 'multicam-studio');
}

export interface EngineFile {
  port: number;
  token: string;
  pid: number;
  api: string;
  mode?: string;
}

export function readEngineFile(dataDir: string): EngineFile | null {
  try {
    const raw: unknown = JSON.parse(fs.readFileSync(path.join(dataDir, 'engine.json'), 'utf8'));
    if (
      raw &&
      typeof raw === 'object' &&
      typeof (raw as EngineFile).port === 'number' &&
      typeof (raw as EngineFile).token === 'string' &&
      typeof (raw as EngineFile).pid === 'number'
    ) {
      return raw as EngineFile;
    }
  } catch {
    // absent or unreadable
  }
  return null;
}

export function pidAlive(pid: number): boolean {
  if (pid <= 0) return false;
  try {
    process.kill(pid, 0);
    return true;
  } catch (err) {
    return (err as NodeJS.ErrnoException).code === 'EPERM';
  }
}

const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

export type TakeOverResult = 'stopped' | 'none' | 'busy' | 'failed';

/**
 * Ask the engine described by `engine.json` to stop and wait until it has.
 * `busy`: it is running jobs (the caller may retry later).
 */
export async function takeOverEngine(
  dataDir: string,
  opts: {
    fetchImpl?: typeof fetch;
    isAlive?: (pid: number) => boolean;
    timeoutMs?: number;
    pollMs?: number;
  } = {},
): Promise<TakeOverResult> {
  const info = readEngineFile(dataDir);
  if (!info) return 'none';
  const doFetch = opts.fetchImpl ?? fetch;
  const isAlive = opts.isAlive ?? pidAlive;
  let res: Response;
  try {
    res = await doFetch(`http://127.0.0.1:${info.port}/api/system/shutdown`, {
      method: 'POST',
      headers: { 'X-Multicam-Token': info.token },
    });
  } catch {
    return isAlive(info.pid) ? 'failed' : 'stopped';
  }
  if (res.status === 409) return 'busy';
  if (!res.ok) return 'failed';
  const deadline = Date.now() + (opts.timeoutMs ?? 20_000);
  while (Date.now() < deadline) {
    if (!isAlive(info.pid)) return 'stopped';
    await sleep(opts.pollMs ?? 200);
  }
  return 'failed';
}

/** Start the engine on its own (no window): `multicam://start` with the app closed. */
export function spawnHeadlessEngine(backend: BackendCommand): number | undefined {
  const child = spawn(backend.command, [...backend.args, '--headless'], {
    cwd: backend.cwd,
    env: { ...process.env, ...backend.env, PYTHONUNBUFFERED: '1' },
    detached: true,
    stdio: 'ignore',
    windowsHide: true,
  });
  child.unref();
  return child.pid;
}
