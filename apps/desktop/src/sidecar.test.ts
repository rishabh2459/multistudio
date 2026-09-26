import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

import { afterEach, describe, expect, it } from 'vitest';

import { RestartPolicy, Sidecar, SidecarError, parseReadyLine, type SidecarInfo } from './sidecar';

describe('parseReadyLine', () => {
  it('reads the port from the ready line only', () => {
    expect(parseReadyLine('MULTICAM_API_READY port=51234')).toBe(51234);
    expect(parseReadyLine('MULTICAM_API_READY port=51234\r')).toBe(51234);
    expect(parseReadyLine('INFO: MULTICAM_API_READY port=1')).toBeNull();
    expect(parseReadyLine('MULTICAM_API_READY port=0')).toBeNull();
    expect(parseReadyLine('MULTICAM_API_READY port=70000')).toBeNull();
  });
});

describe('RestartPolicy', () => {
  it('backs off and gives up after too many crashes in the window', () => {
    const policy = new RestartPolicy(3, 60_000, [100, 200, 400]);
    expect(policy.next(0)).toBe(100);
    expect(policy.next(1_000)).toBe(200);
    expect(policy.next(2_000)).toBe(400);
    expect(policy.next(3_000)).toBeNull();
    expect(policy.next(61_500)).toBe(200); // the oldest two fell out of the window
  });
});

// ---------------------------------------------------------------- fake engine
// A tiny Node server that behaves like `multicam-api`: prints the ready line,
// answers /api/system/health, exits when stdin closes, can be told to crash.
const FAKE = `
const http = require('node:http');
const args = process.argv.slice(2);
const port = Number(args[args.indexOf('--port') + 1]);
if (process.env.FAKE_MODE === 'die-early') { console.error('boom: missing library'); process.exit(3); }
const server = http.createServer((req, res) => {
  if (req.url === '/api/system/health') { res.end('{"status":"ok"}'); return; }
  if (req.url === '/crash') { res.end('bye'); setTimeout(() => process.exit(9), 10); return; }
  if (req.url === '/env') { res.end(JSON.stringify({ token: process.env.MULTICAM_API_TOKEN, cors: process.env.MULTICAM_CORS, watch: args.includes('--watch-stdin') })); return; }
  res.statusCode = 404; res.end();
});
server.listen(port, '127.0.0.1', () => console.log('MULTICAM_API_READY port=' + server.address().port));
process.stdin.on('data', () => {});
process.stdin.on('end', () => { console.log('stdin closed'); server.close(() => process.exit(0)); });
if (process.env.FAKE_MODE === 'ignore-stdin') process.stdin.removeAllListeners('end');
`;

const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'sidecar-'));
const script = path.join(dir, 'fake-engine.cjs');
fs.writeFileSync(script, FAKE);

const running: Sidecar[] = [];
afterEach(async () => {
  await Promise.all(running.splice(0).map((s) => s.stop(2_000)));
});

function makeSidecar(env: Record<string, string> = {}, policy?: RestartPolicy) {
  const lines: string[] = [];
  const sidecar = new Sidecar({
    backend: { command: process.execPath, args: [script], env },
    token: 'secret-token',
    uiOrigin: 'app://multicam',
    readyTimeoutMs: 10_000,
    policy: policy ?? new RestartPolicy(3, 60_000, [50, 50, 50]),
    log: (source, line) => lines.push(`${source}: ${line}`),
  });
  running.push(sidecar);
  return { sidecar, lines };
}

describe('Sidecar', () => {
  it('starts the engine, passes token and CORS origin, stops it via stdin', async () => {
    const { sidecar, lines } = makeSidecar();
    const info = await sidecar.start();
    expect(sidecar.status).toBe('ready');
    const env = await (await fetch(`${info.baseUrl}/env`)).json();
    expect(env).toEqual({ token: 'secret-token', cors: 'app://multicam', watch: true });
    await sidecar.stop();
    expect(sidecar.status).toBe('stopped');
    expect(lines).toContain('stdout: stdin closed'); // clean shutdown, not a kill
    await expect(fetch(`${info.baseUrl}/api/system/health`)).rejects.toThrow();
  });

  it('reports a clear error with the output when the engine cannot start', async () => {
    const { sidecar } = makeSidecar({ FAKE_MODE: 'die-early' });
    const err = await sidecar.start().catch((e: unknown) => e);
    expect(err).toBeInstanceOf(SidecarError);
    expect((err as SidecarError).message).toMatch(/stopped during startup \(exit code 3\)/);
    expect((err as SidecarError).output).toContain('boom: missing library');
    expect(sidecar.status).toBe('failed');
  });

  it('reports a missing executable', async () => {
    const sidecar = new Sidecar({
      backend: { command: path.join(dir, 'does-not-exist'), args: [] },
      token: 't',
      uiOrigin: 'app://multicam',
    });
    await expect(sidecar.start()).rejects.toThrow(/could not run/);
  });

  it('restarts after a crash on the same port', async () => {
    const { sidecar } = makeSidecar();
    const first = await sidecar.start();
    const restarted = new Promise<{ info: SidecarInfo; portChanged: boolean }>((resolve) =>
      sidecar.once('restarted', resolve),
    );
    await fetch(`${first.baseUrl}/crash`);
    const { info, portChanged } = await restarted;
    expect(portChanged).toBe(false);
    expect(info.port).toBe(first.port);
    expect(info.pid).not.toBe(first.pid);
    expect(sidecar.restarts).toBe(1);
    expect((await fetch(`${info.baseUrl}/api/system/health`)).ok).toBe(true);
  });

  it('gives up after repeated crashes', async () => {
    const { sidecar } = makeSidecar({}, new RestartPolicy(1, 60_000, [20]));
    const first = await sidecar.start();
    const restarted = new Promise<SidecarInfo>((r) =>
      sidecar.once('restarted', ({ info }) => r(info)),
    );
    await fetch(`${first.baseUrl}/crash`);
    const second = await restarted;
    const failed = new Promise<SidecarError>((r) => sidecar.once('failed', r));
    await fetch(`${second.baseUrl}/crash`);
    expect((await failed).message).toMatch(/keeps stopping/);
    expect(sidecar.status).toBe('failed');
  });

  it('kills an engine that ignores the stop request', async () => {
    const { sidecar, lines } = makeSidecar({ FAKE_MODE: 'ignore-stdin' });
    const info = await sidecar.start();
    await sidecar.stop(300);
    expect(lines.some((l) => l.includes('killing it'))).toBe(true);
    await expect(fetch(`${info.baseUrl}/api/system/health`)).rejects.toThrow();
  });
});
