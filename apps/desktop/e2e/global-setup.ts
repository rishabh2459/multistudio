import { execFileSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import path from 'node:path';

import { MEDIA_DIR, REPO_ROOT } from './paths';

/** Synthetic 3-camera recording, made once. */
export default function globalSetup(): void {
  if (existsSync(path.join(MEDIA_DIR, 'wide.mp4'))) return;
  execFileSync(
    'uv',
    ['run', 'python', 'scripts/make_demo_media.py', MEDIA_DIR, '--seconds', '30'],
    { cwd: REPO_ROOT, stdio: 'inherit' },
  );
}
