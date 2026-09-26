import path from 'node:path';

import { describe, expect, it } from 'vitest';

import { resolveLayout } from './layout';

const base = {
  resourcesPath: path.resolve('/Applications/Multicam Studio.app/Contents/Resources'),
  appPath: path.resolve('/repo/apps/desktop'),
  env: {},
};

describe('resolveLayout', () => {
  it('uses the bundled engine, UI and ffmpeg when packaged', () => {
    const res = base.resourcesPath;
    const layout = resolveLayout({
      ...base,
      packaged: true,
      platform: 'darwin',
      isFile: (p) => p === path.join(res, 'backend', 'ffmpeg'),
    });
    expect(layout.webRoot).toBe(path.join(res, 'web'));
    expect(layout.backend.command).toBe(path.join(res, 'backend', 'multicam-api'));
    expect(layout.backend.env).toEqual({ MULTICAM_FFMPEG: path.join(res, 'backend', 'ffmpeg') });
  });

  it('adds .exe on Windows', () => {
    const layout = resolveLayout({
      ...base,
      packaged: true,
      platform: 'win32',
      isFile: () => true,
    });
    expect(layout.backend.command.endsWith('multicam-api.exe')).toBe(true);
    expect(layout.backend.env?.MULTICAM_FFPROBE?.endsWith('ffprobe.exe')).toBe(true);
  });

  it('runs the engine with uv from the repo in development', () => {
    const layout = resolveLayout({
      ...base,
      packaged: false,
      platform: 'darwin',
      isFile: () => false,
    });
    expect(layout.repoRoot).toBe(path.resolve('/repo'));
    expect(layout.backend).toEqual({
      command: 'uv',
      args: ['run', 'multicam-api'],
      cwd: path.resolve('/repo'),
    });
    expect(layout.webRoot).toBe(path.join(path.resolve('/repo'), 'apps', 'web', 'out'));
    expect(layout.webUrl).toBeNull();
  });

  it('honours development overrides', () => {
    const layout = resolveLayout({
      ...base,
      packaged: false,
      platform: 'linux',
      isFile: () => false,
      env: {
        MULTICAM_BACKEND: '["python3","-m","multicam_api.main"]',
        MULTICAM_WEB_URL: 'http://localhost:3000',
        MULTICAM_WEB_OUT: '/tmp/out',
      },
    });
    expect(layout.backend.command).toBe('python3');
    expect(layout.backend.args).toEqual(['-m', 'multicam_api.main']);
    expect(layout.webUrl).toBe('http://localhost:3000');
    expect(layout.webRoot).toBe('/tmp/out');
    expect(() =>
      resolveLayout({
        ...base,
        packaged: false,
        platform: 'linux',
        isFile: () => false,
        env: { MULTICAM_BACKEND: '"uv"' },
      }),
    ).toThrow(/JSON array/);
  });
});
