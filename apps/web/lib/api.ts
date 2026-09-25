/**
 * Typed client for the local API. Types come from schemas/openapi.json
 * (generated into @multicam/types/api by `make schemas`).
 */
import type { Schema } from '@multicam/types/api';

import { apiConfig, type ApiConfig, resourceUrl } from './config';

export type Health = Schema<'Health'>;
export type SystemInfo = Schema<'SystemInfo'>;
export type ProjectSummary = Schema<'ProjectSummary'>;
export type Project = Schema<'ProjectOut'>;
export type ProjectCreate = Schema<'ProjectCreate'>;
export type ProjectUpdate = Schema<'ProjectUpdate'>;
export type Clip = Schema<'ClipOut'>;
export type ClipCreate = Schema<'ClipCreate'>;
export type ClipUpdate = Schema<'ClipUpdate'>;
export type CutListOut = Schema<'CutListOut'>;
export type CutList = CutListOut['cutlist'];
export type Job = Schema<'JobOut'>;
export type JobKind = Schema<'JobKind'>;
export type JobStatus = Schema<'JobStatus'>;
export type Export = Schema<'ExportOut'>;
export type ClipRole = Schema<'ClipRole'>;
export type Preset = Schema<'Preset'>;

export const TOKEN_HEADER = 'X-Multicam-Token';

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly detail: string,
  ) {
    super(detail);
    this.name = 'ApiError';
  }
}

/** Turn FastAPI's error body into one readable sentence. */
export function errorDetail(body: unknown, fallback: string): string {
  if (body && typeof body === 'object' && 'detail' in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) {
      return detail
        .map((d) => {
          const item = d as { loc?: unknown[]; msg?: string };
          const where = (item.loc ?? []).filter((p) => p !== 'body').join('.');
          return where ? `${where}: ${item.msg ?? 'invalid'}` : (item.msg ?? 'invalid');
        })
        .join('; ');
    }
  }
  return fallback;
}

export async function request<T>(
  method: 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE',
  path: string,
  body?: unknown,
  config: ApiConfig = apiConfig(),
): Promise<T> {
  const headers: Record<string, string> = {};
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (config.token) headers[TOKEN_HEADER] = config.token;
  let response: Response;
  try {
    response = await fetch(config.base + path, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, `Cannot reach the Multicam Studio API at ${config.base}`);
  }
  if (response.status === 204) return undefined as T;
  const text = await response.text();
  const data: unknown = text ? JSON.parse(text) : undefined;
  if (!response.ok) {
    throw new ApiError(
      response.status,
      errorDetail(data, `${response.status} ${response.statusText}`),
    );
  }
  return data as T;
}

const enc = encodeURIComponent;

export const api = {
  health: () => request<Health>('GET', '/api/system/health'),
  info: (encoders = false) =>
    request<SystemInfo>('GET', `/api/system/info${encoders ? '?encoders=true' : ''}`),

  listProjects: () => request<ProjectSummary[]>('GET', '/api/projects'),
  createProject: (body: ProjectCreate) => request<Project>('POST', '/api/projects', body),
  getProject: (id: string) => request<Project>('GET', `/api/projects/${enc(id)}`),
  updateProject: (id: string, body: ProjectUpdate) =>
    request<Project>('PATCH', `/api/projects/${enc(id)}`, body),
  deleteProject: (id: string) => request<void>('DELETE', `/api/projects/${enc(id)}`),

  addClip: (projectId: string, body: ClipCreate) =>
    request<Clip>('POST', `/api/projects/${enc(projectId)}/clips`, body),
  updateClip: (clipId: string, body: ClipUpdate) =>
    request<Clip>('PATCH', `/api/clips/${enc(clipId)}`, body),
  deleteClip: (clipId: string) => request<void>('DELETE', `/api/clips/${enc(clipId)}`),

  /** Latest cutlist, or null if the project has none yet. */
  getCutlist: async (projectId: string): Promise<CutListOut | null> => {
    try {
      return await request<CutListOut>('GET', `/api/projects/${enc(projectId)}/cutlist`);
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) return null;
      throw err;
    }
  },

  startJob: (projectId: string, kind: JobKind, params: Record<string, unknown> = {}) =>
    request<Job>('POST', `/api/projects/${enc(projectId)}/jobs`, { kind, params }),
  listJobs: (projectId: string) => request<Job[]>('GET', `/api/projects/${enc(projectId)}/jobs`),
  getJob: (jobId: string) => request<Job>('GET', `/api/jobs/${enc(jobId)}`),
  cancelJob: (jobId: string) => request<Job>('POST', `/api/jobs/${enc(jobId)}/cancel`),
  retryJob: (jobId: string) => request<Job>('POST', `/api/jobs/${enc(jobId)}/retry`),

  listExports: (projectId: string) =>
    request<Export[]>('GET', `/api/projects/${enc(projectId)}/exports`),
  exportFileUrl: (exportId: string) => resourceUrl(`/api/exports/${enc(exportId)}/file`),
  jobEventsUrl: (jobId: string) => resourceUrl(`/api/jobs/${enc(jobId)}/events`),
  projectEventsUrl: (projectId: string) => resourceUrl(`/api/projects/${enc(projectId)}/events`),
};

export const FINISHED: readonly JobStatus[] = ['succeeded', 'failed', 'cancelled'];

export function isFinished(job: Pick<Job, 'status'>): boolean {
  return FINISHED.includes(job.status);
}
