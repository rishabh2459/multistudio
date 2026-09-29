'use client';

import { useQueryClient } from '@tanstack/react-query';
import { ScanFace } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { useStore } from 'zustand';

import { ErrorAlert } from '@/components/error-alert';
import { JobProgress } from '@/components/project/job-progress';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { api, ApiError, isFinished, type CutListOut, type Job, type Project } from '@/lib/api';
import { actionForKey, isTypingTarget, type EditorAction } from '@/lib/editor-keys';
import { createEditorStore, type EditorStore } from '@/lib/editor-store';
import { formatDuration, type Rational } from '@/lib/format';
import { latestJob } from '@/lib/jobs';
import { frameToSeconds, secondsToFrame } from '@/lib/media-time';
import { qk, useStartJob, useSystemInfo, useTimeline } from '@/lib/queries';
import {
  durationFrames,
  nextCut,
  previousCut,
  removeSegment,
  segmentIndexAt,
  split,
  switchAt,
} from '@/lib/timeline-edit';

import { Inspector } from './inspector';
import { ProgramMonitor } from './program-monitor';
import { Timeline } from './timeline';
import { Transport } from './transport';

export const AUTOSAVE_MS = 800;

/** Apply one keyboard action to the editor. */
export function runAction(
  store: EditorStore,
  action: EditorAction,
  cameraIds: string[],
  fps: Rational,
): void {
  const s = store.getState();
  const frame = Math.floor(s.playhead);
  switch (action.type) {
    case 'camera': {
      const clipId = cameraIds[action.index];
      if (clipId) s.edit((c) => switchAt(c, frame, clipId));
      break;
    }
    case 'togglePlay':
      s.setPlaying(!s.playing, 1);
      break;
    case 'play':
      s.setPlaying(true, s.playing && action.faster ? Math.min(4, s.rate * 2) : 1);
      break;
    case 'pause':
      s.setPlaying(false, 1);
      break;
    case 'back':
      s.seek(frame - secondsToFrame(action.seconds, fps));
      break;
    case 'step':
      s.setPlaying(false);
      s.seek(frame + action.frames);
      break;
    case 'jumpCut':
      s.seek(action.direction > 0 ? nextCut(s.cut, frame) : previousCut(s.cut, frame));
      break;
    case 'home':
      s.seek(0);
      break;
    case 'end':
      s.seek(durationFrames(s.cut) - 1);
      break;
    case 'split':
      s.edit((c) => split(c, frame));
      break;
    case 'delete':
      s.edit((c) => removeSegment(c, s.selected ?? segmentIndexAt(c, frame)));
      break;
    case 'undo':
      s.undo();
      break;
    case 'redo':
      s.redo();
      break;
    case 'zoom':
      s.setZoom(s.zoom * action.factor);
      break;
  }
}

/** Advance the playhead in real time while playing. */
function usePlaybackClock(store: EditorStore, fps: Rational) {
  const playing = useStore(store, (s) => s.playing);
  useEffect(() => {
    if (!playing) return;
    const perSecond = fps.num / fps.den;
    let last = performance.now();
    let raf = requestAnimationFrame(function tick(now) {
      const s = store.getState();
      const end = durationFrames(s.cut) - 1;
      const next = s.playhead + ((now - last) / 1000) * perSecond * s.rate;
      last = now;
      if (next >= end) {
        store.setState({ playhead: end, playing: false });
        return;
      }
      store.setState({ playhead: next });
      raf = requestAnimationFrame(tick);
    });
    return () => cancelAnimationFrame(raf);
  }, [playing, store, fps]);
}

/** Save the edit as a new cutlist version shortly after each change. */
function useAutosave(store: EditorStore, projectId: string) {
  const client = useQueryClient();
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined;
    let saving = false;

    const save = async () => {
      if (saving) return;
      const { cut } = store.getState();
      saving = true;
      store.getState().setSave({ state: 'saving' });
      try {
        const out = await api.saveCutlist(projectId, cut);
        client.setQueryData<CutListOut>(qk.cutlist(projectId), out);
        void client.invalidateQueries({ queryKey: qk.project(projectId) });
        // Edited again while saving? Stay dirty and save once more.
        if (store.getState().cut === cut)
          store.getState().setSave({ state: 'saved', version: out.version });
        else schedule();
      } catch (err) {
        const message = err instanceof ApiError ? err.detail : String(err);
        store.getState().setSave({ state: 'error', message });
      } finally {
        saving = false;
      }
    };
    const schedule = () => {
      clearTimeout(timer);
      store.getState().setSave({ state: 'dirty' });
      timer = setTimeout(() => void save(), AUTOSAVE_MS);
    };
    const unsubscribe = store.subscribe((s, prev) => {
      if (s.cut !== prev.cut) schedule();
    });
    const warn = (e: BeforeUnloadEvent) => {
      if (store.getState().save.state !== 'saved') e.preventDefault();
    };
    window.addEventListener('beforeunload', warn);
    return () => {
      unsubscribe();
      window.removeEventListener('beforeunload', warn);
      if (timer && store.getState().save.state === 'dirty') {
        clearTimeout(timer);
        void save(); // leaving the editor: save right away
      }
    };
  }, [store, projectId, client]);
}

function EditorWorkspace({
  project,
  initial,
  jobs,
}: {
  project: Project;
  initial: CutListOut;
  jobs: Job[];
}) {
  const [store] = useState(() => createEditorStore(initial.cutlist, initial.version));
  const timeline = useTimeline(project.id);
  const startJob = useStartJob(project.id);
  const fps = initial.cutlist.fps;
  const clips = project.clips;
  const cameraIds = useMemo(() => clips.map((c) => c.id), [clips]);
  const timings = useMemo(
    () => new Map((timeline.data?.clips ?? []).map((c) => [c.clip_id, c])),
    [timeline.data],
  );
  const proxyJob = latestJob(jobs, ['proxy']);
  const reframeJob = latestJob(jobs, ['reframe']);
  const reframing = reframeJob !== undefined && !isFinished(reframeJob);
  const saved = useStore(store, (s) => s.save.state === 'saved');
  const info = useSystemInfo();
  const faceModel = info.data?.face_model_available ?? true;
  const audioClipId =
    project.reference_clip_id ?? timeline.data?.clips.find((c) => c.has_audio)?.clip_id ?? null;

  usePlaybackClock(store, fps);
  useAutosave(store, project.id);

  // Previews: start the proxy job once if they are missing.
  const asked = useRef(false);
  useEffect(() => {
    if (!timeline.data || timeline.data.proxies_ready || asked.current) return;
    if (proxyJob && !isFinished(proxyJob)) return;
    asked.current = true;
    startJob.mutate({ kind: 'proxy' });
  }, [timeline.data, proxyJob, startJob]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (isTypingTarget(e.target)) return;
      const action = actionForKey(e);
      if (!action) return;
      e.preventDefault();
      runAction(store, action, cameraIds, fps);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [store, cameraIds, fps]);

  const seconds = frameToSeconds(durationFrames(initial.cutlist), fps);

  return (
    <div className="flex flex-col gap-4" data-testid="editor">
      {proxyJob && !isFinished(proxyJob) && <JobProgress job={proxyJob} />}
      <div className="flex flex-wrap items-center gap-3">
        <Button
          size="sm"
          variant="outline"
          disabled={!saved || reframing || startJob.isPending}
          title={saved ? undefined : 'Wait until your changes are saved'}
          onClick={() => startJob.mutate({ kind: 'reframe' })}
        >
          <ScanFace /> Auto framing
        </Button>
        <span className="text-xs text-muted-foreground">
          {faceModel
            ? 'Follows faces and adds punch-ins. Shots you framed by hand are kept.'
            : 'Face model not installed: shots use a centred crop.'}
        </span>
      </div>
      {reframeJob && reframing && <JobProgress job={reframeJob} />}
      <ErrorAlert error={timeline.error ?? startJob.error} />
      <div className="grid gap-4 lg:grid-cols-[1fr_18rem]">
        <ProgramMonitor
          store={store}
          clips={clips}
          timings={timings}
          fps={fps}
          audioClipId={audioClipId}
        />
        <Card>
          <CardContent className="pt-5">
            <Inspector store={store} clips={clips} timings={timings} fps={fps} />
          </CardContent>
        </Card>
      </div>
      <Transport store={store} fps={fps} />
      <Timeline store={store} clips={clips} timings={timings} fps={fps} />
      <p className="text-xs text-muted-foreground">
        Length {formatDuration(seconds)} · changes are saved automatically as new versions; the
        export uses the latest one.
      </p>
    </div>
  );
}

export function EditorView({
  project,
  cutlist,
  jobs,
  onNext,
}: {
  project: Project;
  cutlist: CutListOut | null;
  jobs: Job[];
  onNext: () => void;
}) {
  // Reopen the editor on versions made by jobs (auto framing), not on its own saves.
  const auto = cutlist && cutlist.source !== 'manual' ? cutlist.version : null;
  const [base, setBase] = useState(auto);
  if (auto !== null && auto !== base) setBase(auto);

  if (!cutlist) {
    return <ErrorAlert error={new Error('Run the auto edit first.')} />;
  }
  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between gap-4">
        <div>
          <CardTitle>Edit</CardTitle>
          <CardDescription>
            Check every cut. Press a camera number (or click a camera) to switch from the playhead;
            drag cuts on the Program lane.
          </CardDescription>
        </div>
        <Button onClick={onNext}>Continue to export</Button>
      </CardHeader>
      <CardContent>
        <EditorWorkspace
          key={`${project.id}-${base ?? 'edit'}`}
          project={project}
          initial={cutlist}
          jobs={jobs}
        />
      </CardContent>
    </Card>
  );
}
