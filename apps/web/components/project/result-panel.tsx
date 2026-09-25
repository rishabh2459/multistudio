'use client';

import { Download, Film, FolderOpen } from 'lucide-react';
import { useState } from 'react';

import { ErrorAlert } from '@/components/error-alert';
import { Badge } from '@/components/ui/badge';
import { Button, buttonVariants } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select } from '@/components/ui/select';
import { api, isFinished, type CutList, type Export, type Job, type Project } from '@/lib/api';
import { clipDisplayName } from '@/lib/cutlist';
import { desktop } from '@/lib/desktop';
import { formatBytes, formatRelative, joinPath, slug } from '@/lib/format';
import { latestJob } from '@/lib/jobs';
import { useExports, useStartJob, useSystemInfo } from '@/lib/queries';
import { useSettings } from '@/lib/settings-store';

import { CutlistTimeline } from './cutlist-summary';
import { JobProgress } from './job-progress';

export const RENDER_PRESET_LABELS: Record<string, string> = {
  'youtube-1080p': 'YouTube 1080p',
  'youtube-4k': 'YouTube 4K',
  master: 'Master (high quality, large)',
  draft: 'Draft (fast preview)',
};

/** Output file for a render, or undefined to let the engine choose. */
export function outputPath(
  folder: string,
  projectName: string,
  preset: string,
): string | undefined {
  if (!folder.trim()) return undefined;
  return joinPath(folder.trim(), `${slug(projectName) || 'video'}-${preset}.mp4`);
}

function RenderOptions({ project, busy }: { project: Project; busy: boolean }) {
  const settings = useSettings();
  const [encodersWanted, setEncodersWanted] = useState(settings.encoder !== 'auto');
  const info = useSystemInfo(encodersWanted);
  const start = useStartJob(project.id);
  const [preset, setPreset] = useState(settings.renderPreset);
  const [encoder, setEncoder] = useState(settings.encoder);
  const [audio, setAudio] = useState('mix');
  const [folder, setFolder] = useState(settings.outputFolder);
  const presets = info.data?.render_presets ?? Object.keys(RENDER_PRESET_LABELS);
  const encoders = info.data?.encoders_h264 ?? [];

  async function pickFolder() {
    const picked = await desktop()?.pickFolder?.({ title: 'Save videos in' });
    if (picked) setFolder(picked);
  }

  function render() {
    const output_path = outputPath(folder, project.name, preset);
    start.mutate({
      kind: 'render',
      params: {
        preset,
        encoder,
        ...(output_path ? { output_path } : {}),
        ...(audio !== 'mix' ? { audio_clip_id: audio } : {}),
      },
    });
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="render-preset">Quality</Label>
          <Select id="render-preset" value={preset} onChange={(e) => setPreset(e.target.value)}>
            {presets.map((p) => (
              <option key={p} value={p}>
                {RENDER_PRESET_LABELS[p] ?? p}
              </option>
            ))}
          </Select>
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="render-encoder">Encoder</Label>
          <Select
            id="render-encoder"
            value={encoder}
            onFocus={() => setEncodersWanted(true)}
            onChange={(e) => setEncoder(e.target.value)}
          >
            <option value="auto">Automatic (fastest available)</option>
            {encoders.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </Select>
          {encodersWanted && info.isFetching && (
            <p className="text-xs text-muted-foreground">Testing the encoders on this computer…</p>
          )}
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="render-audio">Sound</Label>
          <Select id="render-audio" value={audio} onChange={(e) => setAudio(e.target.value)}>
            <option value="mix">Mix of all cameras</option>
            {project.clips
              .filter((c) => c.media?.audio_codec)
              .map((c) => (
                <option key={c.id} value={c.id}>
                  Only {clipDisplayName(c)}
                </option>
              ))}
          </Select>
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="render-folder">Save in</Label>
          <div className="flex gap-2">
            <Input
              id="render-folder"
              value={folder}
              placeholder="Project folder (default)"
              onChange={(e) => setFolder(e.target.value)}
            />
            {desktop()?.pickFolder && (
              <Button
                variant="outline"
                size="icon"
                aria-label="Choose folder"
                onClick={() => void pickFolder()}
              >
                <FolderOpen />
              </Button>
            )}
          </div>
        </div>
      </div>
      <Button className="self-start" disabled={busy || start.isPending} onClick={render}>
        <Film /> Export video
      </Button>
      <ErrorAlert error={start.error} />
    </div>
  );
}

function ExportItem({ item }: { item: Export }) {
  const bridge = desktop();
  return (
    <li className="flex flex-wrap items-center gap-2 border-t py-3 text-sm first:border-t-0">
      <span className="min-w-0 flex-1 truncate font-mono text-xs" title={item.path}>
        {item.path}
      </span>
      {item.preset && (
        <Badge variant="secondary">{RENDER_PRESET_LABELS[item.preset] ?? item.preset}</Badge>
      )}
      {item.exists ? (
        <span className="text-muted-foreground">
          {item.size_bytes !== null ? formatBytes(item.size_bytes) : ''} ·{' '}
          {formatRelative(item.created_at)}
        </span>
      ) : (
        <Badge variant="warning">File not found</Badge>
      )}
      {item.exists && bridge?.showInFolder && (
        <Button size="sm" variant="ghost" onClick={() => void bridge.showInFolder?.(item.path)}>
          <FolderOpen /> Show
        </Button>
      )}
      {item.exists && (
        <a
          href={api.exportFileUrl(item.id)}
          download
          className={buttonVariants({ size: 'sm', variant: 'ghost' })}
        >
          <Download /> Download
        </a>
      )}
    </li>
  );
}

export function ResultPanel({
  project,
  jobs,
  cutlist,
}: {
  project: Project;
  jobs: Job[];
  cutlist: CutList | null;
}) {
  const exports = useExports(project.id);
  const renderJob = latestJob(jobs, ['render']);
  const busy = jobs.some((j) => !isFinished(j));
  const latest = exports.data?.find((e) => e.exists && e.kind === 'video');

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader>
          <CardTitle>Export</CardTitle>
          <CardDescription>
            {cutlist
              ? `${cutlist.segments.length} shots, ready to render.`
              : 'Run the auto edit first.'}
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {cutlist && <CutlistTimeline cutlist={cutlist} clips={project.clips} />}
          {cutlist && <RenderOptions project={project} busy={busy} />}
          {renderJob && <JobProgress job={renderJob} />}
        </CardContent>
      </Card>

      {latest && (
        <Card>
          <CardHeader>
            <CardTitle>Latest video</CardTitle>
          </CardHeader>
          <CardContent>
            <video
              key={latest.id}
              data-testid="result-video"
              controls
              preload="metadata"
              src={api.exportFileUrl(latest.id)}
              className="aspect-video w-full rounded-lg bg-black"
            />
          </CardContent>
        </Card>
      )}

      {exports.data && exports.data.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Exports</CardTitle>
          </CardHeader>
          <CardContent>
            <ul aria-label="Exports">
              {exports.data.map((item) => (
                <ExportItem key={item.id} item={item} />
              ))}
            </ul>
          </CardContent>
        </Card>
      )}
      <ErrorAlert error={exports.error} />
    </div>
  );
}
