/** TanStack Query hooks: one place for cache keys, fetching and invalidation. */
import { useMutation, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useRef } from 'react';

import {
  api,
  isFinished,
  type ClipCreate,
  type ClipUpdate,
  type Job,
  type JobKind,
  type ProjectCreate,
  type ProjectUpdate,
} from './api';
import { mergeJob, parseJobEvent, useEventSource } from './sse';
import { useSettings } from './settings-store';

export const qk = {
  health: (base: string) => ['health', base] as const,
  info: (encoders: boolean) => ['info', encoders] as const,
  projects: ['projects'] as const,
  project: (id: string) => ['project', id] as const,
  cutlist: (id: string) => ['cutlist', id] as const,
  jobs: (id: string) => ['jobs', id] as const,
  exports: (id: string) => ['exports', id] as const,
};

/** Polling interval while a job runs and the event stream is down. */
export const POLL_MS = 1000;

export function useHealth() {
  const apiUrl = useSettings((s) => s.apiUrl);
  return useQuery({
    queryKey: qk.health(apiUrl),
    queryFn: api.health,
    refetchInterval: 10_000,
    retry: false,
  });
}

export function useSystemInfo(encoders = false) {
  return useQuery({
    queryKey: qk.info(encoders),
    queryFn: () => api.info(encoders),
    staleTime: encoders ? Number.POSITIVE_INFINITY : 30_000, // encoder test is slow
  });
}

export function useProjects() {
  return useQuery({ queryKey: qk.projects, queryFn: api.listProjects });
}

export function useProject(id: string) {
  return useQuery({ queryKey: qk.project(id), queryFn: () => api.getProject(id), enabled: !!id });
}

export function useCutlist(id: string) {
  return useQuery({ queryKey: qk.cutlist(id), queryFn: () => api.getCutlist(id), enabled: !!id });
}

export function useExports(id: string) {
  return useQuery({ queryKey: qk.exports(id), queryFn: () => api.listExports(id), enabled: !!id });
}

/** Refresh everything a finished job may have changed. */
export function invalidateProject(client: QueryClient, projectId: string): Promise<void> {
  return Promise.all([
    client.invalidateQueries({ queryKey: qk.project(projectId) }),
    client.invalidateQueries({ queryKey: qk.cutlist(projectId) }),
    client.invalidateQueries({ queryKey: qk.exports(projectId) }),
    client.invalidateQueries({ queryKey: qk.projects }),
  ]).then(() => undefined);
}

/**
 * The project's jobs, newest first, kept live: the event stream pushes changes
 * into the cache; without it we poll while something is running. When a job
 * finishes, the project, cutlist and exports are refetched.
 */
export function useLiveJobs(projectId: string) {
  const client = useQueryClient();
  const onEvent = useCallback(
    (data: string) => {
      const job = parseJobEvent(data);
      if (job) client.setQueryData<Job[]>(qk.jobs(projectId), (old) => mergeJob(old, job));
    },
    [client, projectId],
  );
  const { connected } = useEventSource(
    projectId ? api.projectEventsUrl(projectId) : null,
    'job',
    onEvent,
  );
  const query = useQuery({
    queryKey: qk.jobs(projectId),
    queryFn: () => api.listJobs(projectId),
    enabled: !!projectId,
    refetchInterval: (q) =>
      !connected && (q.state.data ?? []).some((j) => !isFinished(j)) ? POLL_MS : false,
  });

  const lastStatus = useRef(new Map<string, Job['status']>());
  useEffect(() => {
    const seen = lastStatus.current;
    let changed = false;
    for (const job of query.data ?? []) {
      const before = seen.get(job.id);
      if (before !== undefined && !FINISHED_SET.has(before) && isFinished(job)) changed = true;
      seen.set(job.id, job.status);
    }
    if (changed) void invalidateProject(client, projectId);
  }, [query.data, client, projectId]);

  return { ...query, live: connected };
}

const FINISHED_SET = new Set<Job['status']>(['succeeded', 'failed', 'cancelled']);

// ------------------------------------------------------------------ mutations
export function useCreateProject() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: ProjectCreate) => api.createProject(body),
    onSuccess: () => client.invalidateQueries({ queryKey: qk.projects }),
  });
}

export function useUpdateProject(projectId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: ProjectUpdate) => api.updateProject(projectId, body),
    onSuccess: (project) => {
      client.setQueryData(qk.project(projectId), project);
      void client.invalidateQueries({ queryKey: qk.projects });
    },
  });
}

export function useDeleteProject() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.deleteProject(id),
    onSuccess: () => client.invalidateQueries({ queryKey: qk.projects }),
  });
}

export function useAddClip(projectId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: ClipCreate) => api.addClip(projectId, body),
    onSettled: () => invalidateProject(client, projectId),
  });
}

export function useUpdateClip(projectId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ clipId, body }: { clipId: string; body: ClipUpdate }) =>
      api.updateClip(clipId, body),
    onSettled: () => invalidateProject(client, projectId),
  });
}

export function useDeleteClip(projectId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (clipId: string) => api.deleteClip(clipId),
    onSettled: () => invalidateProject(client, projectId),
  });
}

function useJobMutation<A>(projectId: string, fn: (arg: A) => Promise<Job>) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: (job) => client.setQueryData<Job[]>(qk.jobs(projectId), (old) => mergeJob(old, job)),
  });
}

export function useStartJob(projectId: string) {
  return useJobMutation(projectId, ({ kind, params }: { kind: JobKind; params?: object }) =>
    api.startJob(projectId, kind, { ...params }),
  );
}

export function useCancelJob(projectId: string) {
  return useJobMutation(projectId, (jobId: string) => api.cancelJob(jobId));
}

export function useRetryJob(projectId: string) {
  return useJobMutation(projectId, (jobId: string) => api.retryJob(jobId));
}
