import { execFileSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import path from 'node:path';

import { E2E_MEDIA_DIR, REPO_ROOT } from './paths';

/** Make the synthetic recording once (kept between runs). */
export default function globalSetup(): void {
  if (existsSync(path.join(E2E_MEDIA_DIR, 'wide.mp4'))) return;
  execFileSync(
    'uv',
    ['run', 'python', 'scripts/make_demo_media.py', E2E_MEDIA_DIR, '--seconds', '30'],
    { cwd: REPO_ROOT, stdio: 'inherit' },
  );
}
