/**
 * Following a run: Server-Sent Events over `fetch` streaming (UXP has no
 * EventSource), with automatic fallback to polling the session when the host
 * cannot stream or the stream drops (same pattern as the app UI, D50).
 */
import type { PluginClient } from './client';
import { PluginError } from './errors';
import type { ErrorCode, PlanSummary, SessionOut } from './types';

export interface ProgressEvent {
  job_id: string;
  status: string;
  stage: string;
  progress: number;
  message: string;
}

export type RunEvent =
  | { type: 'progress'; data: ProgressEvent }
  | { type: 'plan_ready'; data: PlanSummary }
  | { type: 'step_done'; data: { job_id: string } }
  | { type: 'error'; data: { code: ErrorCode; message: string; hint: string } };

/** Incremental SSE parser: feed text chunks, get complete events. */
export class SseParser {
  private buffer = '';
  private event = 'message';
  private data: string[] = [];

  push(chunk: string): { event: string; data: string }[] {
    this.buffer += chunk.replace(/\r\n?/g, '\n');
    const out: { event: string; data: string }[] = [];
    let nl: number;
    while ((nl = this.buffer.indexOf('\n')) >= 0) {
      const line = this.buffer.slice(0, nl);
      this.buffer = this.buffer.slice(nl + 1);
      if (line === '') {
        if (this.data.length) out.push({ event: this.event, data: this.data.join('\n') });
        this.event = 'message';
        this.data = [];
      } else if (line.startsWith(':')) {
        // comment / ping
      } else {
        const colon = line.indexOf(':');
        const field = colon < 0 ? line : line.slice(0, colon);
        const value = colon < 0 ? '' : line.slice(colon + 1).replace(/^ /, '');
        if (field === 'event') this.event = value;
        else if (field === 'data') this.data.push(value);
      }
    }
    return out;
  }
}

export interface FollowOptions {
  onEvent?: (ev: RunEvent) => void;
  /** Force polling (hosts without streaming fetch). */
  poll?: boolean;
  pollMs?: number;
  signal?: AbortSignal;
  /** For tests. */
  sleep?: (ms: number) => Promise<void>;
}

const defaultSleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

/**
 * Resolve with the plan summary once the run finished, reject with a
 * PluginError if it failed. Streams when possible, polls otherwise.
 */
export async function followRun(
  client: PluginClient,
  sessionId: string,
  jobId: string,
  opts: FollowOptions = {},
): Promise<PlanSummary | null> {
  if (!opts.poll) {
    try {
      const result = await streamRun(client, sessionId, jobId, opts);
      if (result !== undefined) return result;
    } catch (err) {
      if (err instanceof PluginError && err.code !== 'engine_unreachable') throw err;
      // stream not supported or dropped: fall back to polling
    }
  }
  return pollRun(client, sessionId, jobId, opts);
}

/** undefined = stream ended without a final event (caller polls). */
async function streamRun(
  client: PluginClient,
  sessionId: string,
  jobId: string,
  opts: FollowOptions,
): Promise<PlanSummary | null | undefined> {
  const path = `/sessions/${sessionId}/events?job_id=${encodeURIComponent(jobId)}`;
  let res: Response;
  try {
    res = await client.raw(path, {
      headers: { Accept: 'text/event-stream' },
      ...(opts.signal ? { signal: opts.signal } : {}),
    });
  } catch (err) {
    throw new PluginError('engine_unreachable', (err as Error).message);
  }
  if (!res.ok || !res.body || typeof res.body.getReader !== 'function') return undefined;
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  const parser = new SseParser();
  for (;;) {
    const { done, value } = await reader.read();
    if (done) return undefined;
    for (const raw of parser.push(decoder.decode(value, { stream: true }))) {
      const ev = toRunEvent(raw.event, raw.data);
      if (!ev) continue;
      opts.onEvent?.(ev);
      if (ev.type === 'plan_ready') {
        void reader.cancel().catch(() => undefined);
        return ev.data;
      }
      if (ev.type === 'step_done') {
        void reader.cancel().catch(() => undefined);
        return null;
      }
      if (ev.type === 'error') {
        void reader.cancel().catch(() => undefined);
        throw new PluginError(ev.data.code, ev.data.message, ev.data.hint);
      }
    }
  }
}

function toRunEvent(event: string, data: string): RunEvent | null {
  if (!['progress', 'plan_ready', 'step_done', 'error'].includes(event)) return null;
  try {
    return { type: event, data: JSON.parse(data) } as RunEvent;
  } catch {
    return null;
  }
}

async function pollRun(
  client: PluginClient,
  sessionId: string,
  jobId: string,
  opts: FollowOptions,
): Promise<PlanSummary | null> {
  const sleep = opts.sleep ?? defaultSleep;
  let failures = 0;
  for (;;) {
    if (opts.signal?.aborted) throw new PluginError('host_error', 'cancelled');
    let s: SessionOut;
    try {
      s = await client.getSession(sessionId);
      failures = 0;
    } catch (err) {
      if (++failures >= 5) throw err;
      await sleep(opts.pollMs ?? 1_000);
      continue;
    }
    const job = s.job;
    if (job && job.id === jobId) {
      opts.onEvent?.({
        type: 'progress',
        data: {
          job_id: job.id,
          status: job.status,
          stage: job.stage,
          progress: job.progress,
          message: job.message,
        },
      });
      if (job.status === 'succeeded') {
        if (s.plan) opts.onEvent?.({ type: 'plan_ready', data: s.plan });
        return s.plan ?? null;
      }
      if (job.status === 'failed' || job.status === 'cancelled') {
        throw new PluginError('job_failed', job.error ?? `the job ${job.status}`);
      }
    }
    await sleep(opts.pollMs ?? 1_000);
  }
}
