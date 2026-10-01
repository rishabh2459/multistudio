// Make the installable .ccx (a zip of manifest + html + dist + icons).
import { execFileSync } from 'node:child_process';
import { mkdirSync, readFileSync, rmSync } from 'node:fs';

const { version } = JSON.parse(readFileSync('manifest.json', 'utf8'));
mkdirSync('release', { recursive: true });
const out = `release/multicam-studio-premiere-${version}.ccx`;
rmSync(out, { force: true });
execFileSync('zip', ['-r', '-X', out, 'manifest.json', 'index.html', 'dist', 'icons'], {
  stdio: 'inherit',
});
console.log(
  `wrote ${out} (unsigned: install with the UXP Developer Tool, or sign for Creative Cloud in PL9)`,
);
