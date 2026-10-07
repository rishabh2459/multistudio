/**
 * Typed client for the engine's Plugin API v1 (`/api/plugin/v1`).
 *
 * Uses only `fetch`, so it runs in UXP (Premiere), Electron (Resolve WI) and Node.
 */
import { PluginError } from './errors';
import type { JumpCutIn, RemovalsOut, RemovalsPatch, SocialIn, SocialOut } from './extras';
import type {
  EditPlan,
  ErrorCode,
  ExportFileOut,
  FeedbackOut,
  Handshake,
  PlanMethod,
  PresetOut,
  RunIn,
  RunOut,
  SessionCreate,
  SessionOut,
  SessionSetup,
} from './types';

export const API_PREFIX = '/api/plugin/v1';
/** This plugin speaks Plugin API 1.x. */
export const SUPPORTED_API_MAJOR = 1;
export const TOKEN_HEADER = 'X-Multicam-Token';

export interface EngineEndpoint {
  baseUrl: string; // http://127.0.0.1:47811
  token: string;
}

export type FetchLike = (input: string, init?: RequestInit) => Promise<Response>;

export interface ClientOptions {
  fetch?: FetchLike;
  /** ms before a plain request is abandoned (not used for event streams). */
  timeoutMs?: number;
}

export class PluginClient {
  private readonly doFetch: FetchLike;
  private readonly timeoutMs: number;

  constructor(
    readonly endpoint: EngineEndpoint,
    opts: ClientOptions = {},
  ) {
    this.doFetch = opts.fetch ?? ((input, init) => fetch(input, init));
    this.timeoutMs = opts.timeoutMs ?? 30_000;
  }

  url(path: string): string {
    return `${this.endpoint.baseUrl}${path.startsWith('/api') ? path : API_PREFIX + path}`;
  }

  headers(json = false): Record<string, string> {
    return {
      [TOKEN_HEADER]: this.endpoint.token,
      ...(json ? { 'Content-Type': 'application/json' } : {}),
    };
  }

  async request<T>(method: string, path: string, body?: unknown): Promise<T> {
    const controller = typeof AbortController === 'undefined' ? null : new AbortController();
    const timer = controller ? setTimeout(() => controller.abort(), this.timeoutMs) : null;
    let res: Response;
    try {
      res = await this.doFetch(this.url(path), {
        method,
        headers: this.headers(body !== undefined),
        ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
        ...(controller ? { signal: controller.signal } : {}),
      });
    } catch (err) {
      throw new PluginError(
        'engine_unreachable',
        `cannot reach the engine at ${this.endpoint.baseUrl} (${(err as Error).message})`,
      );
    } finally {
      if (timer) clearTimeout(timer);
    }
    if (res.ok) return (await res.json()) as T;
    throw await errorFrom(res);
  }

  /** Raw request with the token (event streams); network errors are not wrapped. */
  raw(path: string, init: RequestInit = {}): Promise<Response> {
    return this.doFetch(this.url(path), {
      ...init,
      headers: { ...this.headers(), ...(init.headers as Record<string, string> | undefined) },
    });
  }

  handshake(): Promise<Handshake> {
    return this.request('GET', '/handshake');
  }

  /** Handshake + version check: refuses an engine with another major API version. */
  async connect(): Promise<Handshake> {
    const hs = await this.handshake();
    const major = Number((hs.api_version ?? '0').split('.')[0]);
    if (major !== SUPPORTED_API_MAJOR) {
      throw new PluginError(
        'engine_incompatible',
        `the engine speaks plugin API ${hs.api_version}; this plugin needs ${SUPPORTED_API_MAJOR}.x`,
      );
    }
    return hs;
  }

  createSession(body: SessionCreate): Promise<SessionOut> {
    return this.request('POST', '/sessions', body);
  }

  getSession(id: string): Promise<SessionOut> {
    return this.request('GET', `/sessions/${id}`);
  }

  setup(id: string, body: SessionSetup): Promise<SessionOut> {
    return this.request('PATCH', `/sessions/${id}/setup`, body);
  }

  run(id: string, body: RunIn = {}): Promise<RunOut> {
    return this.request('POST', `/sessions/${id}/run`, body);
  }

  editPlan(
    id: string,
    opts: { host?: string; version?: number; method?: PlanMethod; ripple?: boolean } = {},
  ): Promise<EditPlan> {
    const q = new URLSearchParams();
    if (opts.host) q.set('host', opts.host);
    if (opts.version) q.set('version', String(opts.version));
    if (opts.method) q.set('method', opts.method);
    if (opts.ripple) q.set('ripple', 'true');
    const qs = q.toString();
    return this.request('GET', `/sessions/${id}/editplan${qs ? `?${qs}` : ''}`);
  }

  exportFile(
    id: string,
    format: 'fcpxml' | 'fcpxml_multicam' | 'xmeml' | 'edl',
    version?: number,
    method?: PlanMethod,
    opts: { ripple?: boolean } = {},
  ): Promise<ExportFileOut> {
    const q = new URLSearchParams({ format });
    if (version) q.set('version', String(version));
    if (method) q.set('method', method);
    if (opts.ripple) q.set('ripple', 'true');
    return this.request('GET', `/sessions/${id}/export?${q.toString()}`);
  }

  feedback(id: string, plan: EditPlan, note?: string): Promise<FeedbackOut> {
    return this.request('POST', `/sessions/${id}/feedback`, { plan, ...(note ? { note } : {}) });
  }

  presets(): Promise<PresetOut[]> {
    return this.request('GET', '/presets');
  }

  /** Social clips: one plan (+ xmeml) per aspect ratio for an in/out range. */
  social(id: string, body: SocialIn): Promise<SocialOut> {
    return this.request('POST', `/sessions/${id}/social`, body);
  }

  /** Start silence detection (a job: follow its events_url). */
  jumpCuts(id: string, body: JumpCutIn = {}): Promise<RunOut> {
    return this.request('POST', `/sessions/${id}/jumpcuts`, body);
  }

  removals(id: string, version?: number): Promise<RemovalsOut> {
    return this.request('GET', `/sessions/${id}/removals${version ? `?version=${version}` : ''}`);
  }

  updateRemovals(id: string, patch: RemovalsPatch): Promise<RemovalsOut> {
    return this.request('PATCH', `/sessions/${id}/removals`, patch);
  }
}

async function errorFrom(res: Response): Promise<PluginError> {
  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    // not JSON
  }
  if (res.status === 401) {
    return new PluginError('unauthorized', 'the engine refused the token', '', 401);
  }
  if (body && typeof body === 'object' && 'code' in body) {
    const b = body as { code: string; message?: string; hint?: string };
    return new PluginError(b.code as ErrorCode, b.message ?? b.code, b.hint ?? '', res.status);
  }
  const detail =
    body && typeof body === 'object' && 'detail' in body
      ? String((body as { detail: unknown }).detail)
      : '';
  return new PluginError('host_error', detail || `engine answered ${res.status}`, '', res.status);
}
