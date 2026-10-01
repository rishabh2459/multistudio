import fs from 'node:fs';
import path from 'node:path';

import type { EditPlan } from '../src/types';

export function loadPlan(): EditPlan {
  return JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures', 'plan.json'), 'utf8'));
}

type Handler = (
  method: string,
  url: URL,
  body: unknown,
) => { status?: number; body: unknown } | Promise<{ status?: number; body: unknown }>;

/** A fetch that routes to `handler` and records the calls. */
export function mockFetch(handler: Handler) {
  const calls: { method: string; url: string; body: unknown; headers: Record<string, string> }[] =
    [];
  const fn = async (input: string, init: RequestInit = {}) => {
    const method = init.method ?? 'GET';
    const body = typeof init.body === 'string' ? JSON.parse(init.body) : undefined;
    calls.push({
      method,
      url: input,
      body,
      headers: (init.headers ?? {}) as Record<string, string>,
    });
    const out = await handler(method, new URL(input), body);
    return new Response(JSON.stringify(out.body), {
      status: out.status ?? 200,
      headers: { 'Content-Type': 'application/json' },
    });
  };
  return { fetch: fn, calls };
}
