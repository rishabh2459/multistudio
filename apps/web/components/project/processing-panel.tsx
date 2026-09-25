'use client';

import { AlertTriangle, Sparkles, Wand2 } from 'lucide-react';
import { useState } from 'react';

import { ErrorAlert } from '@/components/error-alert';
import { PRESET_HELP } from '@/components/new-project-form';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Select } from '@/components/ui/select';
import { isFinished, type CutList, type Job, type Preset, type Project } from '@/lib/api';
import { clipDisplayName, LOW_SYNC_CONFIDENCE } from '@/lib/cutlist';
import { formatDuration, formatOffsetMs, formatPercent } from '@/lib/format';
import { jobWarnings, latestAnalysisJob, latestJob, speakerTimes, vadBackend } from '@/lib/jobs';
import { useStartJob } from '@/lib/queries';

import { CutlistSummary } from './cutlist-summary';
import { JobProgress } from './job-progress';

type Vad = 'auto' | 'silero' | 'energy';
const PRESETS: Preset[] = ['calm', 'balanced', 'dynamic'];
const EDIT_KINDS = ['auto', 'probe', 'sync', 'analyze', 'decide'] as const;

export function SyncTable({ project }: { project: Project }) {
  const synced = project.clips.filter((c) => c.sync);
  if (synced.length === 0) return null;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm" aria-label="Sync results">
        <thead className="text-left text-xs text-muted-foreground">
          <tr>
            <th className="py-2 font-medium">Camera</th>
            <th className="py-2 font-medium">Offset</th>
            <th className="py-2 font-medium">Clock drift</th>
            <th className="py-2 font-medium">Confidence</th>
          </tr>
        </thead>
        <tbody>
          {project.clips.map((clip) => {
            const sync = clip.sync;
            if (!sync) return null;
            const reference = clip.id === sync.reference_clip_id;
            const low = !reference && sync.confidence < LOW_SYNC_CONFIDENCE;
            return (
              <tr key={clip.id} className="border-t">
                <td className="py-2">{clipDisplayName(clip)}</td>
                <td className="py-2 tabular-nums">
                  {reference
                    ? 'reference'
                    : formatOffsetMs((sync.offset_samples / sync.sample_rate) * 1000)}
                </td>
                <td className="py-2 tabular-nums">
                  {reference ? '—' : `${(sync.drift_ppm ?? 0).toFixed(1)} ppm`}
                </td>
                <td className="py-2">
                  {reference ? (
                    '—'
                  ) : low ? (
                    <Badge variant="warning" title="Check that this camera recorded the same audio">
                      <AlertTriangle className="size-3" aria-hidden />
                      {formatPercent(sync.confidence)} – check
                    </Badge>
                  ) : (
                    <Badge variant="success">{formatPercent(sync.confidence)}</Badge>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function SpeakerTimes({ job, project }: { job: Job | undefined; project: Project }) {
  const speakers = speakerTimes(job);
  if (speakers.length === 0) return null;
  const max = Math.max(...speakers.map((s) => s.speakingS), 1);
  const backend = vadBackend(job);
  return (
    <div className="flex flex-col gap-2">
      <h3 className="text-sm font-medium">
        Speaking time
        {backend && (
          <span className="ml-2 font-normal text-muted-foreground">(detected with {backend})</span>
        )}
      </h3>
      <ul className="flex flex-col gap-1.5">
        {speakers.map((s) => {
          const clip = project.clips.find((c) => c.id === s.clipId);
          const name = clip ? clipDisplayName(clip) : s.label;
          return (
            <li
              key={s.clipId}
              className="grid grid-cols-[8rem_1fr_4rem] items-center gap-2 text-sm"
            >
              <span className="truncate">{name}</span>
              <div className="h-2 rounded-full bg-muted">
                <div
                  className="h-full rounded-full bg-primary"
                  style={{ width: `${(s.speakingS / max) * 100}%` }}
                />
              </div>
              <span className="text-right tabular-nums text-muted-foreground">
                {formatDuration(s.speakingS)}
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export function ProcessingPanel({
  project,
  jobs,
  cutlist,
  onNext,
}: {
  project: Project;
  jobs: Job[];
  cutlist: CutList | null;
  onNext: () => void;
}) {
  const start = useStartJob(project.id);
  const [vad, setVad] = useState<Vad>('auto');
  const [preset, setPreset] = useState<Preset>(project.preset);
  const current = latestJob(jobs, [...EDIT_KINDS]);
  const busy = current !== undefined && !isFinished(current);
  const warnings = current?.status === 'succeeded' ? jobWarnings(current) : [];

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader>
          <CardTitle>Auto edit</CardTitle>
          <CardDescription>
            Lines up the cameras by sound, finds who is speaking and picks the shots.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="edit-preset">Editing style</Label>
              <Select
                id="edit-preset"
                value={preset}
                onChange={(e) => setPreset(e.target.value as Preset)}
              >
                <option value="calm">Calm</option>
                <option value="balanced">Balanced</option>
                <option value="dynamic">Dynamic</option>
              </Select>
              <p className="text-xs text-muted-foreground">{PRESET_HELP[preset]}</p>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="vad">Speech detection</Label>
              <Select id="vad" value={vad} onChange={(e) => setVad(e.target.value as Vad)}>
                <option value="auto">Automatic</option>
                <option value="silero">AI model (most accurate)</option>
                <option value="energy">Loudness only (fastest)</option>
              </Select>
            </div>
          </div>
          <Button
            className="self-start"
            disabled={busy || start.isPending}
            onClick={() => start.mutate({ kind: 'auto', params: { vad, preset } })}
          >
            <Wand2 /> {cutlist ? 'Run again' : 'Start auto edit'}
          </Button>
          <ErrorAlert error={start.error} />
          {current && <JobProgress job={current} />}
          {warnings.length > 0 && (
            <Alert variant="warning">
              <AlertTitle>Please check</AlertTitle>
              <AlertDescription>
                <ul className="list-disc pl-4">
                  {warnings.map((w) => (
                    <li key={w}>{w}</li>
                  ))}
                </ul>
              </AlertDescription>
            </Alert>
          )}
        </CardContent>
      </Card>

      {project.clips.some((c) => c.sync) && (
        <Card>
          <CardHeader>
            <CardTitle>Sync</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-6">
            <SyncTable project={project} />
            <SpeakerTimes job={latestAnalysisJob(jobs)} project={project} />
          </CardContent>
        </Card>
      )}

      {cutlist && (
        <Card>
          <CardHeader>
            <CardTitle>The edit</CardTitle>
            <CardDescription>
              Try another style: only the cuts change, nothing is analyzed again.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <CutlistSummary cutlist={cutlist} clips={project.clips} />
            <div className="flex flex-wrap items-center gap-2">
              {PRESETS.map((p) => (
                <Button
                  key={p}
                  size="sm"
                  variant="outline"
                  disabled={busy || start.isPending}
                  onClick={() => start.mutate({ kind: 'decide', params: { preset: p } })}
                >
                  <Sparkles /> {p[0]!.toUpperCase() + p.slice(1)}
                </Button>
              ))}
              <Button className="ml-auto" onClick={onNext} disabled={busy}>
                Continue to export
              </Button>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
