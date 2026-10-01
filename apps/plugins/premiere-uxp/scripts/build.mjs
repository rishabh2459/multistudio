// Bundle the panel for UXP: one IIFE file, React included, `require` left to UXP.
import { build } from 'esbuild';

await build({
  entryPoints: ['src/main.tsx'],
  bundle: true,
  outfile: 'dist/index.js',
  format: 'iife',
  platform: 'browser',
  target: 'es2020',
  jsx: 'automatic',
  external: ['uxp', 'premierepro', 'os', 'fs'],
  define: { 'process.env.NODE_ENV': '"production"' },
  minify: true,
  sourcemap: 'linked',
  logLevel: 'info',
});
