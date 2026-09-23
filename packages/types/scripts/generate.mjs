// Generate src/generated/models.ts from schemas/multicam.schema.json.
// Usage: node scripts/generate.mjs [--check]
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { compile } from 'json-schema-to-typescript';

const schemaPath = fileURLToPath(new URL('../../../schemas/multicam.schema.json', import.meta.url));
const outPath = fileURLToPath(new URL('../src/generated/models.ts', import.meta.url));
const check = process.argv.includes('--check');

const schema = JSON.parse(await readFile(schemaPath, 'utf8'));
const banner = [
  '/* eslint-disable */',
  '/**',
  ' * AUTO-GENERATED from schemas/multicam.schema.json — do not edit by hand.',
  ' * Source of truth: engine/src/multicam_engine/models (Python).',
  ' * Regenerate with: make schemas',
  ' */',
].join('\n');

const ts = await compile(schema, 'MulticamSchemas', {
  bannerComment: banner,
  additionalProperties: false,
  unreachableDefinitions: true,
  strictIndexSignatures: true,
  format: true,
});

if (check) {
  const current = await readFile(outPath, 'utf8').catch(() => '');
  if (current !== ts) {
    console.error(`${outPath} is out of date. Run: make schemas`);
    process.exit(1);
  }
  console.log('types up to date');
} else {
  await mkdir(dirname(outPath), { recursive: true });
  await writeFile(outPath, ts);
  console.log(`wrote ${outPath}`);
}
