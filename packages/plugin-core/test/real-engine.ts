/**
 * Start a real headless engine for integration tests (PL3 "done when": the flow
 * runs against fake-host.ts AND the real engine).
 *
 * MULTICAM_TEST_ENGINE: JSON command, default ["uv","run","python"] when uv is on
 * PATH, else ["python3"]. Tests skip when the engine cannot be imported.
 */
import { execFileSync, spawn, type ChildProcess } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

export const REPO = path.resolve(__dirname, '..', '..', '..');

function pythonCmd(): string[] {
  if (process.env.MULTICAM_TEST_ENGINE) return JSON.parse(process.env.MULTICAM_TEST_ENGINE);
  try {
    execFileSync('uv', ['--version'], { stdio: 'ignore' });
    return ['uv', 'run', 'python'];
  } catch {
    return ['python3'];
  }
}

export function engineAvailable(): boolean {
  const [cmd, ...args] = pythonCmd();
  try {
    execFileSync(cmd!, [...args, '-c', 'import multicam_api, multicam_engine'], {
      cwd: REPO,
      stdio: 'ignore',
      timeout: 60_000,
    });
    return true;
  } catch {
    return false;
  }
}

export interface RealEngine {
  dataDir: string;
  media: { cam1: string; cam2: string; wide: string };
  engineJson(): string | null;
  stop(): Promise<void>;
}

export async function startRealEngine(): Promise<RealEngine> {
  const [cmd, ...args] = pythonCmd();
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'plugin-core-'));
  const mediaDir = path.join(root, 'media');
  execFileSync(cmd!, [...args, 'scripts/make_demo_media.py', '--seconds', '30', mediaDir], {
    cwd: REPO,
    stdio: 'ignore',
    timeout: 120_000,
  });
  const dataDir = path.join(root, 'data');
  const child: ChildProcess = spawn(
    cmd!,
    [
      ...args,
      '-m',
      'multicam_api.main',
      '--headless',
      '--port',
      '0',
      '--idle-exit',
      '0',
      '--data-dir',
      dataDir,
      '--log-level',
      'warning',
    ],
    { cwd: REPO, stdio: ['ignore', 'ignore', 'inherit'] },
  );
  const file = path.join(dataDir, 'engine.json');
  const engineJson = () => (fs.existsSync(file) ? fs.readFileSync(file, 'utf8') : null);
  const deadline = Date.now() + 60_000;
  for (;;) {
    const text = engineJson();
    if (text) {
      const { port } = JSON.parse(text) as { port: number };
      try {
        if ((await fetch(`http://127.0.0.1:${port}/api/system/health`)).ok) break;
      } catch {
        // starting
      }
    }
    if (Date.now() > deadline) throw new Error('engine did not start');
    await new Promise((r) => setTimeout(r, 200));
  }
  return {
    dataDir,
    media: {
      cam1: path.join(mediaDir, 'cam1.mp4'),
      cam2: path.join(mediaDir, 'cam2.mp4'),
      wide: path.join(mediaDir, 'wide.mp4'),
    },
    engineJson,
    stop: async () => {
      child.kill('SIGTERM');
      await new Promise((r) => child.once('exit', r));
    },
  };
}
