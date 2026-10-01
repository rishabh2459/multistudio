/**
 * Finding and starting the engine (PLUGIN_PLAN 3.2): read `engine.json` from the
 * app-data folder, handshake; if there is none, open `multicam://start` and poll.
 */
import { PluginClient, type ClientOptions, type EngineEndpoint } from './client';
import { PluginError } from './errors';
import type { Handshake } from './types';

export interface EngineFile {
  port: number;
  token: string;
  pid: number;
  api: string;
  mode?: string;
}

export interface EngineHost {
  /** Contents of engine.json, or null if it does not exist. */
  readEngineFile(): Promise<string | null>;
  /** Open a URL with the OS (multicam://start). */
  openUrl(url: string): Promise<void>;
}

export const START_URL = 'multicam://start';
export const ENGINE_FILE = 'engine.json';

/** The engine.json path the engine uses on each OS (multicam_api/config.py). */
export function engineFilePath(
  os: 'mac' | 'windows' | 'linux',
  home: string,
  env: Record<string, string | undefined> = {},
): string {
  if (env.MULTICAM_DATA_DIR) return joinPath(env.MULTICAM_DATA_DIR, ENGINE_FILE, os);
  if (os === 'mac') return `${home}/Library/Application Support/Multicam Studio/${ENGINE_FILE}`;
  if (os === 'windows') {
    const appData = env.APPDATA ?? `${home}\\AppData\\Roaming`;
    return `${appData}\\Multicam Studio\\${ENGINE_FILE}`;
  }
  const base = env.XDG_DATA_HOME ?? `${home}/.local/share`;
  return `${base}/multicam-studio/${ENGINE_FILE}`;
}

function joinPath(dir: string, name: string, os: string): string {
  const sep = os === 'windows' ? '\\' : '/';
  return dir.endsWith(sep) ? dir + name : dir + sep + name;
}

export function parseEngineFile(text: string | null): EngineFile | null {
  if (!text) return null;
  try {
    const v = JSON.parse(text) as Partial<EngineFile>;
    if (typeof v.port === 'number' && typeof v.token === 'string' && typeof v.pid === 'number') {
      return { port: v.port, token: v.token, pid: v.pid, api: String(v.api ?? '') };
    }
  } catch {
    // broken file: treat as missing
  }
  return null;
}

export function endpointOf(file: EngineFile): EngineEndpoint {
  return { baseUrl: `http://127.0.0.1:${file.port}`, token: file.token };
}

export interface Connection {
  client: PluginClient;
  handshake: Handshake;
}

/** Connect to a running engine; PluginError('engine_unreachable') if there is none. */
export async function connectEngine(
  host: EngineHost,
  clientOpts: ClientOptions = {},
): Promise<Connection> {
  const file = parseEngineFile(await host.readEngineFile());
  if (!file) {
    throw new PluginError('engine_unreachable', 'Multicam Studio is not running');
  }
  const client = new PluginClient(endpointOf(file), clientOpts);
  return { client, handshake: await client.connect() };
}

/** Start the engine via multicam://start, then wait until it answers (default 20 s). */
export async function startEngine(
  host: EngineHost,
  opts: ClientOptions & {
    timeoutMs?: number;
    pollMs?: number;
    sleep?: (ms: number) => Promise<void>;
  } = {},
): Promise<Connection> {
  try {
    return await connectEngine(host, opts);
  } catch (err) {
    if (!(err instanceof PluginError) || err.code !== 'engine_unreachable') throw err;
  }
  await host.openUrl(START_URL);
  const sleep = opts.sleep ?? ((ms: number) => new Promise<void>((r) => setTimeout(r, ms)));
  const deadline = Date.now() + (opts.timeoutMs ?? 20_000);
  let last: unknown = null;
  while (Date.now() < deadline) {
    await sleep(opts.pollMs ?? 500);
    try {
      return await connectEngine(host, opts);
    } catch (err) {
      last = err;
      if (err instanceof PluginError && err.code === 'engine_incompatible') throw err;
    }
  }
  throw new PluginError(
    'engine_unreachable',
    `the engine did not start (${last instanceof Error ? last.message : 'no answer'})`,
    'Open Multicam Studio once, then try again.',
  );
}
