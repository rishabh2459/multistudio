'use client';

import { useEffect, useRef } from 'react';
import { useStore } from 'zustand';

import { cameraColor } from '@/components/project/cutlist-summary';
import { api, type Clip, type TimelineClip } from '@/lib/api';
import { clipDisplayName } from '@/lib/cutlist';
import type { EditorStore } from '@/lib/editor-store';
import type { Rational } from '@/lib/format';
import { frameToSeconds, isRecording, mediaTime } from '@/lib/media-time';
import { segmentIndexAt, switchAt } from '@/lib/timeline-edit';
import { cn } from '@/lib/utils';

/** Keep a <video> showing media time `target` (seek only when it drifts). */
export function syncVideo(
  video: HTMLVideoElement,
  target: number,
  recording: boolean,
  playing: boolean,
  rate: number,
  tolerance: number,
): void {
  if (!recording) {
    if (!video.paused) video.pause();
    return;
  }
  if (playing) {
    if (Math.abs(video.playbackRate - rate) > 1e-3) video.playbackRate = rate;
    if (Math.abs(video.currentTime - target) > 0.25) video.currentTime = target;
    if (video.paused) void video.play().catch(() => undefined);
  } else {
    if (!video.paused) video.pause();
    if (Math.abs(video.currentTime - target) > tolerance) video.currentTime = target;
  }
}

/**
 * Multi-angle preview: every camera plays its proxy in sync with the playhead;
 * the camera that is on air at the playhead is shown large. Click a camera (or
 * press its number) to switch to it from the playhead.
 */
export function ProgramMonitor({
  store,
  clips,
  timings,
  fps,
  audioClipId,
}: {
  store: EditorStore;
  clips: Clip[];
  timings: Map<string, TimelineClip>;
  fps: Rational;
  audioClipId: string | null;
}) {
  const videos = useRef(new Map<string, HTMLVideoElement>());
  const onAir = useStore(store, (s) => s.cut.segments[segmentIndexAt(s.cut, s.playhead)]?.clip_id);
  const playhead = useStore(store, (s) => Math.floor(s.playhead));
  const t = frameToSeconds(playhead, fps);

  useEffect(() => {
    const tolerance = fps.den / fps.num / 2;
    const apply = () => {
      const s = store.getState();
      const time = frameToSeconds(s.playhead, fps);
      for (const [clipId, video] of videos.current) {
        const timing = timings.get(clipId);
        if (!timing) continue;
        syncVideo(
          video,
          mediaTime(timing, time),
          isRecording(timing, time),
          s.playing,
          s.rate * timing.speed,
          tolerance,
        );
      }
    };
    apply();
    return store.subscribe(apply);
  }, [store, timings, fps]);

  return (
    <div className="grid grid-cols-3 gap-2 lg:grid-cols-4" data-testid="program-monitor">
      {clips.map((clip, i) => {
        const timing = timings.get(clip.id);
        const live = clip.id === onAir;
        const recording = timing ? isRecording(timing, t) : false;
        return (
          <button
            key={clip.id}
            type="button"
            aria-label={`Switch to camera ${i + 1} (${clipDisplayName(clip)})`}
            aria-current={live ? 'true' : undefined}
            className={cn(
              'relative overflow-hidden rounded-md border bg-black text-left',
              live
                ? 'order-first col-span-3 row-span-2 border-red-500 lg:col-span-4'
                : 'hover:border-foreground/50',
            )}
            style={{ aspectRatio: '16 / 9' }}
            onClick={() =>
              store
                .getState()
                .edit((c) => switchAt(c, Math.floor(store.getState().playhead), clip.id))
            }
          >
            {timing?.has_proxy ? (
              <video
                ref={(el) => {
                  if (el) videos.current.set(clip.id, el);
                  else videos.current.delete(clip.id);
                }}
                src={api.proxyUrl(clip.id)}
                muted={clip.id !== audioClipId}
                playsInline
                preload="auto"
                className="size-full object-contain"
              />
            ) : (
              <div className="flex size-full items-center justify-center text-xs text-white/70">
                {timing ? 'Preparing preview…' : 'File not available'}
              </div>
            )}
            {timing && !recording && (
              <div className="absolute inset-0 flex items-center justify-center bg-black/70 text-xs text-white/80">
                Not recording here
              </div>
            )}
            <span
              className={cn(
                'absolute left-1.5 top-1.5 flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] font-semibold text-white',
                cameraColor(clips, clip.id),
              )}
            >
              {i + 1} · {clipDisplayName(clip)}
              {live && <span className="ml-1 rounded bg-red-600 px-1">LIVE</span>}
            </span>
          </button>
        );
      })}
    </div>
  );
}
