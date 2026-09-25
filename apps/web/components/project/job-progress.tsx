'use client';

import { RotateCcw, Square } from 'lucide-react';

import { ErrorAlert } from '@/components/error-alert';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { isFinished, type Job } from '@/lib/api';
import { formatPercent } from '@/lib/format';
import { etaText, KIND_LABELS, stageLabel } from '@/lib/jobs';
import { useCancelJob, useRetryJob } from '@/lib/queries';

/** Progress of one job, with Cancel while it runs and Retry when it failed. */
export function JobProgress({ job }: { job: Job }) {
  const cancel = useCancelJob(job.project_id);
  const retry = useRetryJob(job.project_id);
  const running = !isFinished(job);
  const eta = etaText(job.message);

  if (job.status === 'succeeded') return null;
  return (
    <div data-testid="job-progress" className="flex flex-col gap-2 rounded-lg border p-4">
      <div className="flex items-center gap-3">
        <span className="font-medium">{KIND_LABELS[job.kind]}</span>
        <span className="text-sm text-muted-foreground" aria-live="polite">
          {job.status === 'failed'
            ? 'Failed'
            : job.status === 'cancelled'
              ? 'Cancelled'
              : `${stageLabel(job)} · ${formatPercent(job.progress)}`}
        </span>
        <div className="ml-auto">
          {running ? (
            <Button
              size="sm"
              variant="outline"
              disabled={cancel.isPending}
              onClick={() => cancel.mutate(job.id)}
            >
              <Square /> Cancel
            </Button>
          ) : (
            <Button size="sm" disabled={retry.isPending} onClick={() => retry.mutate(job.id)}>
              <RotateCcw /> Try again
            </Button>
          )}
        </div>
      </div>
      {running && <Progress value={job.progress} />}
      {running && (job.message || eta) && (
        <p className="text-xs text-muted-foreground">{eta ?? job.message}</p>
      )}
      {job.status === 'failed' && job.error && (
        <ErrorAlert error={new Error(job.error)} title="The job failed" />
      )}
      <ErrorAlert error={cancel.error ?? retry.error} />
    </div>
  );
}
