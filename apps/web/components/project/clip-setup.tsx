'use client';

import { FolderOpen, Link2, Plus, Star, Trash2 } from 'lucide-react';
import { useState, type FormEvent } from 'react';

import { ErrorAlert } from '@/components/error-alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select } from '@/components/ui/select';
import { ApiError, type Clip, type ClipRole, type Project } from '@/lib/api';
import { clipDurationS, clipReadiness } from '@/lib/cutlist';
import { desktop } from '@/lib/desktop';
import { formatDuration, formatFps } from '@/lib/format';
import { useAddClip, useDeleteClip, useUpdateClip, useUpdateProject } from '@/lib/queries';

const READINESS = {
  ok: null,
  missing: { variant: 'destructive', text: 'File missing' },
  changed: { variant: 'warning', text: 'File changed' },
  'no-audio': { variant: 'warning', text: 'No audio' },
} as const;

function ClipMeta({ clip }: { clip: Clip }) {
  const duration = clipDurationS(clip);
  if (!clip.media || duration === null) return <span>Not read yet</span>;
  return (
    <span>
      {formatDuration(duration)} · {clip.media.width}×{clip.media.height} ·{' '}
      {formatFps(clip.media.fps)} fps{clip.media.is_vfr ? ' (variable)' : ''}
    </span>
  );
}

function RelinkForm({ clip, projectId }: { clip: Clip; projectId: string }) {
  const update = useUpdateClip(projectId);
  const [path, setPath] = useState('');
  const conflict = update.error instanceof ApiError && update.error.status === 409;

  function relink(newPath: string, force = false) {
    if (newPath) update.mutate({ clipId: clip.id, body: { path: newPath, force } });
  }

  async function pick() {
    const [file] = (await desktop()?.pickFiles?.({ title: `Find ${clip.name}` })) ?? [];
    if (file) {
      setPath(file);
      relink(file);
    }
  }

  return (
    <div className="mt-3 flex flex-col gap-2 rounded-md bg-muted/60 p-3">
      <p className="text-sm">The file was moved or changed. Point to where it is now:</p>
      <div className="flex gap-2">
        {desktop()?.pickFiles ? (
          <Button size="sm" variant="outline" onClick={() => void pick()}>
            <FolderOpen /> Find file…
          </Button>
        ) : (
          <>
            <Input
              aria-label={`New path for ${clip.name}`}
              placeholder="/full/path/to/file.mp4"
              value={path}
              onChange={(e) => setPath(e.target.value)}
            />
            <Button size="sm" disabled={!path || update.isPending} onClick={() => relink(path)}>
              <Link2 /> Relink
            </Button>
          </>
        )}
      </div>
      {conflict ? (
        <div className="flex flex-col gap-2">
          <ErrorAlert error={update.error} title="This looks like a different file" />
          <Button size="sm" variant="outline" onClick={() => relink(path, true)}>
            Use it anyway
          </Button>
        </div>
      ) : (
        <ErrorAlert error={update.error} />
      )}
    </div>
  );
}

function ClipRow({ clip, project }: { clip: Clip; project: Project }) {
  const update = useUpdateClip(project.id);
  const remove = useDeleteClip(project.id);
  const setReference = useUpdateProject(project.id);
  const [label, setLabel] = useState(clip.speaker_label ?? '');
  const readiness = READINESS[clipReadiness(clip)];

  function saveLabel() {
    const next = label.trim() || null;
    if (next !== (clip.speaker_label ?? null)) {
      update.mutate({ clipId: clip.id, body: { speaker_label: next } });
    }
  }

  return (
    <li data-testid="clip-row" className="border-b py-4 last:border-b-0">
      <div className="flex flex-wrap items-start gap-4">
        <div className="min-w-48 flex-1">
          <div className="flex items-center gap-2">
            <span className="font-medium" title={clip.path}>
              {clip.name}
            </span>
            {clip.is_reference && (
              <Badge variant="secondary" title="Other cameras are synced to this one">
                <Star className="size-3" aria-hidden /> Reference
              </Badge>
            )}
            {readiness && <Badge variant={readiness.variant}>{readiness.text}</Badge>}
          </div>
          <p className="text-xs text-muted-foreground">
            <ClipMeta clip={clip} />
          </p>
        </div>
        <div className="flex w-36 flex-col gap-1">
          <Label htmlFor={`role-${clip.id}`} className="text-xs text-muted-foreground">
            Camera shows
          </Label>
          <Select
            id={`role-${clip.id}`}
            value={clip.role}
            onChange={(e) =>
              update.mutate({ clipId: clip.id, body: { role: e.target.value as ClipRole } })
            }
          >
            <option value="speaker">One person</option>
            <option value="wide">Everyone (wide)</option>
            <option value="broll">B-roll (manual)</option>
          </Select>
        </div>
        {clip.role === 'speaker' && (
          <div className="flex w-44 flex-col gap-1">
            <Label htmlFor={`label-${clip.id}`} className="text-xs text-muted-foreground">
              Speaker name
            </Label>
            <Input
              id={`label-${clip.id}`}
              value={label}
              maxLength={100}
              placeholder="e.g. Host"
              onChange={(e) => setLabel(e.target.value)}
              onBlur={saveLabel}
              onKeyDown={(e) => e.key === 'Enter' && e.currentTarget.blur()}
            />
          </div>
        )}
        <div className="flex items-center gap-1 self-end">
          {!clip.is_reference && (
            <Button
              size="sm"
              variant="ghost"
              title="Sync the other cameras to this one"
              disabled={setReference.isPending}
              onClick={() => setReference.mutate({ reference_clip_id: clip.id })}
            >
              <Star /> Make reference
            </Button>
          )}
          <Button
            size="icon"
            variant="ghost"
            aria-label={`Remove ${clip.name}`}
            disabled={remove.isPending}
            onClick={() => remove.mutate(clip.id)}
          >
            <Trash2 />
          </Button>
        </div>
      </div>
      {(clip.file_status === 'missing' || clip.file_status === 'changed') && (
        <RelinkForm clip={clip} projectId={project.id} />
      )}
      {!(update.error instanceof ApiError && update.error.status === 409) && (
        <ErrorAlert error={update.error ?? remove.error ?? setReference.error} />
      )}
    </li>
  );
}

/** Split pasted text into paths: one per line, quotes stripped. */
export function parsePaths(text: string): string[] {
  return text
    .split(/\r?\n/)
    .map((line) => line.trim().replace(/^['"]|['"]$/g, ''))
    .filter(Boolean);
}

function AddClips({ projectId }: { projectId: string }) {
  const add = useAddClip(projectId);
  const [text, setText] = useState('');
  const [errors, setErrors] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);

  async function addPaths(paths: string[]) {
    setBusy(true);
    const failed: string[] = [];
    for (const path of paths) {
      try {
        await add.mutateAsync({ path });
      } catch (err) {
        failed.push(err instanceof Error ? err.message : String(err));
      }
    }
    setErrors(failed);
    setBusy(false);
    if (failed.length === 0) setText('');
  }

  async function pick() {
    const files = await desktop()?.pickFiles?.({ title: 'Add camera files', multiple: true });
    if (files?.length) await addPaths(files);
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    void addPaths(parsePaths(text));
  }

  return (
    <div className="flex flex-col gap-3">
      {desktop()?.pickFiles ? (
        <Button onClick={() => void pick()} disabled={busy} className="self-start">
          <Plus /> {busy ? 'Adding…' : 'Add camera files'}
        </Button>
      ) : (
        <form onSubmit={submit} className="flex flex-col gap-2">
          <Label htmlFor="clip-paths">File paths (one per line)</Label>
          <textarea
            id="clip-paths"
            rows={3}
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={'/Users/me/Recordings/cam1.mp4\n/Users/me/Recordings/cam2.mp4'}
            className="w-full rounded-md border border-input bg-transparent px-3 py-2 font-mono text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          />
          <Button type="submit" disabled={busy || !text.trim()} className="self-start">
            <Plus /> {busy ? 'Adding…' : 'Add clips'}
          </Button>
        </form>
      )}
      {errors.map((message) => (
        <ErrorAlert key={message} error={new Error(message)} title="Could not add a file" />
      ))}
    </div>
  );
}

export function ClipSetup({ project, onNext }: { project: Project; onNext: () => void }) {
  const speakers = project.clips.filter((c) => c.role === 'speaker').length;
  const ready = project.clips.length >= 2;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Cameras</CardTitle>
        <CardDescription>
          Add one file per camera. Files stay where they are; nothing is copied.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {project.clips.length > 0 && (
          <ul aria-label="Clips">
            {project.clips.map((clip) => (
              <ClipRow key={clip.id} clip={clip} project={project} />
            ))}
          </ul>
        )}
        <AddClips projectId={project.id} />
        <div className="flex items-center justify-between border-t pt-4">
          <p className="text-sm text-muted-foreground">
            {ready
              ? speakers === 0
                ? 'Mark at least one camera as "One person" so there is someone to cut to.'
                : `${project.clips.length} cameras ready.`
              : 'Add at least two cameras to continue.'}
          </p>
          <Button onClick={onNext} disabled={!ready || speakers === 0}>
            Continue
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
