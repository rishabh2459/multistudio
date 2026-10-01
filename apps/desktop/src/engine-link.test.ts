import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

import { describe, expect, it } from 'vitest';

import {
  defaultDataDir,
  findUrlInArgv,
  parseMulticamUrl,
  readEngineFile,
  takeOverEngine,
} from './engine-link';

describe('parseMulticamUrl', () => {
  it('understands start and open', () => {
    expect(parseMulticamUrl('multicam://start')).toEqual({ action: 'start' });
    expect(parseMulticamUrl('multicam://START/')).toEqual({ action: 'start' });
    expect(parseMulticamUrl('multicam:start')).toEqual({ action: 'start' });
    const id = '0f803793-3246-42c0-90d5-c1e9dc1212d2';
    expect(parseMulticamUrl(`multicam://open?session=${id}`)).toEqual({
      action: 'open',
      sessionId: id,
    });
    expect(parseMulticamUrl('multicam://open?session=../../etc')).toEqual({
      action: 'open',
      sessionId: null,
    });
  });

  it('rejects anything else', () => {
    expect(parseMulticamUrl('https://start')).toBeNull();
    expect(parseMulticamUrl('multicam://delete-everything')).toBeNull();
    expect(parseMulticamUrl('not a url')).toBeNull();
  });

  it('finds the URL in argv (Windows / Linux launch)', () => {
    expect(findUrlInArgv(['/app/Multicam Studio', '--flag', 'multicam://start'])).toEqual({
      action: 'start',
    });
    expect(findUrlInArgv(['/app/Multicam Studio'])).toBeNull();
  });
});

describe('defaultDataDir', () => {
  it('matches the engine on every OS', () => {
    expect(defaultDataDir('darwin', {}, '/Users/a')).toBe(
      '/Users/a/Library/Application Support/Multicam Studio',
    );
    expect(
      defaultDataDir('win32', { APPDATA: 'C:\\Users\\a\\AppData\\Roaming' }, 'C:\\Users\\a'),
    ).toContain('Multicam Studio');
    expect(defaultDataDir('linux', {}, '/home/a')).toBe('/home/a/.local/share/multicam-studio');
    expect(defaultDataDir('linux', { MULTICAM_DATA_DIR: '/x' }, '/home/a')).toBe('/x');
  });
});

function folderWith(info: object | string | null): string {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'engine-link-'));
  if (info !== null) {
    fs.writeFileSync(
      path.join(dir, 'engine.json'),
      typeof info === 'string' ? info : JSON.stringify(info),
    );
  }
  return dir;
}

describe('takeOverEngine', () => {
  const info = { port: 47811, token: 'tok', pid: 4242, api: '1.0.0' };

  it('reads engine.json', () => {
    expect(readEngineFile(folderWith(info))).toEqual(info);
    expect(readEngineFile(folderWith('{broken'))).toBeNull();
    expect(readEngineFile(folderWith(null))).toBeNull();
  });

  it('asks the engine to stop with its token and waits for it', async () => {
    let alive = true;
    const calls: [string, RequestInit | undefined][] = [];
    const fetchImpl = (async (url: string, init?: RequestInit) => {
      calls.push([url, init]);
      setTimeout(() => (alive = false), 30);
      return new Response('{}', { status: 202 });
    }) as unknown as typeof fetch;
    const result = await takeOverEngine(folderWith(info), {
      fetchImpl,
      isAlive: () => alive,
      pollMs: 10,
    });
    expect(result).toBe('stopped');
    expect(calls[0]![0]).toBe('http://127.0.0.1:47811/api/system/shutdown');
    expect((calls[0]![1]!.headers as Record<string, string>)['X-Multicam-Token']).toBe('tok');
  });

  it('reports busy, none and unreachable', async () => {
    const busy = (async () => new Response('{}', { status: 409 })) as unknown as typeof fetch;
    expect(await takeOverEngine(folderWith(info), { fetchImpl: busy })).toBe('busy');
    expect(await takeOverEngine(folderWith(null))).toBe('none');
    const down = (async () => {
      throw new TypeError('connect ECONNREFUSED');
    }) as unknown as typeof fetch;
    expect(await takeOverEngine(folderWith(info), { fetchImpl: down, isAlive: () => false })).toBe(
      'stopped',
    );
  });
});
