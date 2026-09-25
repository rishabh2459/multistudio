/** Helpers to read job state and results (pure, unit-tested). */
import type { Job, JobKind } from './api';

const STAGE_LABELS: Record<string, string> = {
  queued: 'Waiting',
  starting: 'Starting',
  probe: 'Reading clips',
  sync: 'Syncing audio',
  analyze: 'Detecting speakers',
  decide: 'Choosing cameras',
  'render:audio': 'Mixing audio',
  'render:video': 'Rendering video',
  'render:join': 'Joining parts',
  'render:done': 'Finishing',
  done: 'Done',
};

export const KIND_LABELS: Record<JobKind, string> = {
  probe: 'Read clips',
  sync: 'Sync',
  analyze: 'Speaker detection',
  decide: 'Camera cuts',
  auto: 'Auto edit',
  render: 'Render',
};

export function stageLabel(job: Pick<Job, 'stage' | 'status'>): string {
  if (job.status === 'queued') return STAGE_LABELS.queued!;
  return STAGE_LABELS[job.stage] ?? job.stage;
}

export interface SpeakerTime {
  clipId: string;
  label: string;
  speakingS: number;
}

function record(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

/** The analyze step's result, from an `analyze` job or the analyze part of `auto`. */
function analyzeResult(job: Job): Record<string, unknown> | null {
  const result = record(job.result);
  if (!result) return null;
  if (job.kind === 'analyze') return result;
  if (job.kind === 'auto') return record(result.analyze);
  return null;
}

export function speakerTimes(job: Job | undefined): SpeakerTime[] {
  const analyze = job ? analyzeResult(job) : null;
  const speakers = analyze?.speakers;
  if (!Array.isArray(speakers)) return [];
  return speakers.flatMap((s) => {
    const item = record(s);
    if (!item || typeof item.clip_id !== 'string') return [];
    return [
      {
        clipId: item.clip_id,
        label: typeof item.label === 'string' ? item.label : '',
        speakingS: typeof item.speaking_s === 'number' ? item.speaking_s : 0,
      },
    ];
  });
}

export function vadBackend(job: Job | undefined): string | null {
  const analyze = job ? analyzeResult(job) : null;
  return typeof analyze?.vad_backend === 'string' ? analyze.vad_backend : null;
}

export function jobWarnings(job: Job | undefined): string[] {
  const warnings = record(job?.result)?.warnings;
  return Array.isArray(warnings) ? warnings.filter((w): w is string => typeof w === 'string') : [];
}

export function renderOutputPath(job: Job | undefined): string | null {
  const path = record(job?.result)?.path;
  return job?.kind === 'render' && typeof path === 'string' ? path : null;
}

/** Newest job of the given kinds (jobs are newest-first). */
export function latestJob(jobs: readonly Job[] | undefined, kinds: JobKind[]): Job | undefined {
  return jobs?.find((j) => kinds.includes(j.kind));
}

/** Newest succeeded job that carries speaker times. */
export function latestAnalysisJob(jobs: readonly Job[] | undefined): Job | undefined {
  return jobs?.find((j) => j.status === 'succeeded' && speakerTimes(j).length > 0);
}

/** "ETA 42 s" from the render message ("120/900 frames, ETA 42 s"). */
export function etaText(message: string): string | null {
  const match = /ETA (\d+) s/.exec(message);
  if (!match) return null;
  const s = Number(match[1]);
  if (s < 60) return `about ${s} s left`;
  const m = Math.round(s / 60);
  return `about ${m} min left`;
}
