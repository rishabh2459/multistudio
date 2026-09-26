/**
 * Build an installer for this machine (macOS: dmg + zip for its CPU; Windows:
 * NSIS x64). Checks the pieces first:
 *   apps/web/out                      pnpm --filter @multicam/web build   (run if missing)
 *   packaging/dist/multicam-api/       pnpm --filter @multicam/desktop backend
 */
import { spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const desktop = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const root = path.resolve(desktop, '../..');
const win = process.platform === 'win32';

function run(cmd, args, cwd = desktop) {
  console.log(`$ ${cmd} ${args.join(' ')}`);
  const res = spawnSync(cmd, args, { cwd, stdio: 'inherit', shell: win });
  if (res.status !== 0) process.exit(res.status ?? 1);
}

const backend = path.join(root, 'packaging/dist/multicam-api', `multicam-api${win ? '.exe' : ''}`);
if (!existsSync(backend)) {
  console.error(
    `\nThe standalone backend is missing (${backend}).\n` +
      'Build it first:  pnpm --filter @multicam/desktop backend\n',
  );
  process.exit(1);
}
if (!existsSync(path.join(root, 'apps/web/out/index.html'))) {
  run('pnpm', ['--filter', '@multicam/web', 'build'], root);
}
run('pnpm', ['run', 'build']);

const platform = { darwin: '--mac', win32: '--win', linux: '--linux' }[process.platform];
const arch = { arm64: '--arm64', x64: '--x64' }[process.arch];
if (!platform || !arch) {
  console.error(`Unsupported build machine: ${process.platform}/${process.arch}`);
  process.exit(1);
}
// The backend is built for this CPU, so the installer is too.
run('pnpm', ['exec', 'electron-builder', platform, arch, '--publish', 'never']);
console.log(`\nInstallers are in ${path.join(desktop, 'release')}`);
