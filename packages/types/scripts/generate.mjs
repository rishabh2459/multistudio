// Generate TypeScript types from the Python-owned contracts:
//   schemas/multicam.schema.json -> src/generated/models.ts  (engine data model)
//   schemas/openapi.json         -> src/generated/api.ts     (local HTTP API)
// Usage: node scripts/generate.mjs [--check]
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { compile } from 'json-schema-to-typescript';
import openapiTS, { astToString } from 'openapi-typescript';

const check = process.argv.includes('--check');
const here = (rel) => fileURLToPath(new URL(rel, import.meta.url));

function banner(source) {
  return [
    '/* eslint-disable */',
    '/**',
    ` * AUTO-GENERATED from ${source} — do not edit by hand.`,
    ' * Regenerate with: make schemas',
    ' */',
  ].join('\n');
}

async function modelsTs() {
  const schema = JSON.parse(await readFile(here('../../../schemas/multicam.schema.json'), 'utf8'));
  return compile(schema, 'MulticamSchemas', {
    bannerComment: banner('schemas/multicam.schema.json (engine/src/multicam_engine/models)'),
    additionalProperties: false,
    unreachableDefinitions: true,
    strictIndexSignatures: true,
    format: true,
  });
}

async function apiTs() {
  const spec = JSON.parse(await readFile(here('../../../schemas/openapi.json'), 'utf8'));
  // A field with a default stays optional in request bodies (the API fills it in).
  const ast = await openapiTS(spec, { defaultNonNullable: false });
  return `${banner('schemas/openapi.json (apps/api)')}\n\n${astToString(ast)}`;
}

const outputs = [
  [here('../src/generated/models.ts'), await modelsTs()],
  [here('../src/generated/api.ts'), await apiTs()],
];

let stale = 0;
for (const [path, text] of outputs) {
  if (check) {
    const current = await readFile(path, 'utf8').catch(() => '');
    if (current !== text) {
      console.error(`${path} is out of date. Run: make schemas`);
      stale += 1;
    } else {
      console.log(`${path.split('/').pop()} up to date`);
    }
  } else {
    await mkdir(dirname(path), { recursive: true });
    await writeFile(path, text);
    console.log(`wrote ${path}`);
  }
}
process.exit(stale ? 1 : 0);
