import { describe, expect, it } from 'vitest';

import { PluginClient, TOKEN_HEADER } from '../src/client';
import { connectEngine, engineFilePath, parseEngineFile, startEngine } from '../src/engine';
import { PluginError } from '../src/errors';
import { fakeEngineHost } from './fake-host';
import { mockFetch } from './helpers';

const endpoint = { baseUrl: 'http://127.0.0.1:47811', token: 'tok' };
const hs = {
  engine_version: 'x',
  api_version: '1.0.0',
  capabilities: [],
  models: { vad: true, face: true, asr: false },
  licence: { status: 'dev' },
  data_dir: '/d',
  pid: 1,
};

describe('PluginClient', () => {
  it('sends the token and parses JSON', async () => {
    const m = mockFetch(() => ({ body: hs }));
    const c = new PluginClient(endpoint, { fetch: m.fetch });
    expect((await c.connect()).pid).toBe(1);
    expect(m.calls[0]!.url).toBe('http://127.0.0.1:47811/api/plugin/v1/handshake');
    expect(m.calls[0]!.headers[TOKEN_HEADER]).toBe('tok');
  });

  it('maps engine errors to PluginError codes', async () => {
    const m = mockFetch((_m, url) =>
      url.pathname.endsWith('/editplan')
        ? {
            status: 409,
            body: { code: 'no_plan', message: 'no edit yet', hint: 'run auto edit first' },
          }
        : { status: 401, body: { detail: 'missing or wrong API token' } },
    );
    const c = new PluginClient(endpoint, { fetch: m.fetch });
    const e1 = await c.editPlan('s1', { host: 'premiere', method: 'cuts' }).catch((e) => e);
    expect(e1).toBeInstanceOf(PluginError);
    expect([e1.code, e1.hint, e1.status]).toEqual(['no_plan', 'run auto edit first', 409]);
    expect(m.calls[0]!.url).toContain('/sessions/s1/editplan?host=premiere&method=cuts');
    const e2 = await c.getSession('s1').catch((e) => e);
    expect(e2.code).toBe('unauthorized');
  });

  it('reports an unreachable engine and refuses another major version', async () => {
    const down = new PluginClient(endpoint, {
      fetch: async () => {
        throw new TypeError('fetch failed');
      },
    });
    await expect(down.handshake()).rejects.toThrow(/cannot reach the engine/);
    const v2 = new PluginClient(endpoint, {
      fetch: mockFetch(() => ({ body: { ...hs, api_version: '2.0.0' } })).fetch,
    });
    const err = await v2.connect().catch((e) => e);
    expect(err.code).toBe('engine_incompatible');
  });
});

describe('engine discovery', () => {
  it('knows where engine.json is', () => {
    expect(engineFilePath('mac', '/Users/r')).toBe(
      '/Users/r/Library/Application Support/Multicam Studio/engine.json',
    );
    expect(
      engineFilePath('windows', 'C:\\Users\\r', { APPDATA: 'C:\\Users\\r\\AppData\\Roaming' }),
    ).toBe('C:\\Users\\r\\AppData\\Roaming\\Multicam Studio\\engine.json');
    expect(engineFilePath('linux', '/home/r')).toBe(
      '/home/r/.local/share/multicam-studio/engine.json',
    );
    expect(parseEngineFile('{"port":1,"token":"t","pid":2,"api":"1.0.0"}')).toEqual({
      port: 1,
      token: 't',
      pid: 2,
      api: '1.0.0',
    });
    expect(parseEngineFile('{oops')).toBeNull();
  });

  it('starts the engine through multicam://start and waits for engine.json', async () => {
    let file: string | null = null;
    const host = fakeEngineHost(() => file);
    await expect(connectEngine(host)).rejects.toThrow(/not running/);
    const fetch = mockFetch(() => ({ body: hs })).fetch;
    let polls = 0;
    const conn = await startEngine(host, {
      fetch,
      pollMs: 1,
      sleep: async () => {
        if (++polls === 3)
          file = JSON.stringify({ port: 47811, token: 'tok', pid: 9, api: '1.0.0' });
      },
    });
    expect(host.opened).toEqual(['multicam://start']);
    expect(conn.client.endpoint.baseUrl).toBe('http://127.0.0.1:47811');
  });
});
