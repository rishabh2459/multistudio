// Bundle main (Node/Electron), preload and renderer for Resolve's Electron.
import { build } from 'esbuild';

const common = {
  bundle: true,
  minify: true,
  sourcemap: 'linked',
  logLevel: 'info',
  target: 'es2022',
};
await build({
  ...common,
  entryPoints: ['src/main.ts'],
  outfile: 'dist/main.js',
  platform: 'node',
  format: 'cjs',
  external: ['electron'],
});
await build({
  ...common,
  entryPoints: ['src/preload.ts'],
  outfile: 'dist/preload.js',
  platform: 'node',
  format: 'cjs',
  external: ['electron'],
});
await build({
  ...common,
  entryPoints: ['src/renderer.tsx'],
  outfile: 'dist/renderer.js',
  platform: 'browser',
  format: 'iife',
  jsx: 'automatic',
  define: { 'process.env.NODE_ENV': '"production"' },
});
