import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

import { describe, expect, it } from 'vitest';

import { CHANNELS } from './channels';
import { buildDiagnosticReport, redact } from './diagnostics';
import { LogFile, tailFile } from './logs';

describe('diagnostic report', () => {
  it('has the useful facts and never the token', () => {
    const token = 'tok-SECRET-123';
    const report = buildDiagnosticReport({
      appVersion: '0.1.0',
      versions: { electron: '44.4.5', chrome: '152', node: '24' },
      os: {
        platform: 'darwin',
        release: '25.0.0',
        arch: 'arm64',
        cpus: '8× Apple M2',
        memoryGb: 16,
      },
      packaged: true,
      paths: { logs: '/Users/me/Library/Logs/Multicam Studio' },
      engine: {
        status: 'ready',
        url: 'http://127.0.0.1:5000',
        pid: 42,
        restarts: 1,
        lastExit: 'exit code 9',
      },
      systemInfo: { ffmpeg: '/x/ffmpeg', vad_model_available: true },
      logs: { 'engine.log': `GET /api/projects?token=${token} 200` },
      token,
      now: new Date('2026-01-01T00:00:00Z'),
    });
    expect(report).toContain('Version: 0.1.0');
    expect(report).toContain('Electron 44.4.5');
    expect(report).toContain('darwin 25.0.0 (arm64)');
    expect(report).toContain('Automatic restarts: 1 · last stop: exit code 9');
    expect(report).toContain('"vad_model_available": true');
    expect(report).toContain('token=[redacted]');
    expect(report).not.toContain(token);
  });

  it('redacts only real secrets', () => {
    expect(redact('a b a', ['a'])).toBe('a b a'); // too short to be a secret
    expect(redact('xx-secret-xx secret', ['secret'])).toBe('xx-[redacted]-xx [redacted]');
  });
});

describe('log files', () => {
  it('appends, rotates big files and returns the tail', () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'logs-'));
    const file = path.join(dir, 'main.log');
    fs.writeFileSync(file, 'x'.repeat(2000));
    const log = new LogFile(file, 1000);
    expect(fs.existsSync(`${file}.1`)).toBe(true);
    for (let i = 1; i <= 5; i++) log.write('main', `line ${i}`);
    log.close();
    const tail = tailFile(file, 2).split('\n');
    expect(tail).toHaveLength(2);
    expect(tail[1]).toMatch(/\[main\] line 5$/);
    expect(tailFile(path.join(dir, 'nope.log'), 5)).toBe('');
  });
});

describe('preload bridge', () => {
  it('uses the same channel names as the main process', () => {
    const preload = fs.readFileSync(path.join(__dirname, 'preload.ts'), 'utf8');
    for (const channel of Object.values(CHANNELS)) expect(preload).toContain(`'${channel}'`);
  });
});
