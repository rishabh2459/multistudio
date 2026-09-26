'use client';

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type MouseEvent as ReactMouseEvent,
  type PointerEvent,
} from 'react';
import { useStore } from 'zustand';

import { cameraColor } from '@/components/project/cutlist-summary';
import type { Clip, TimelineClip } from '@/lib/api';
import { clipDisplayName } from '@/lib/cutlist';
import type { EditorStore } from '@/lib/editor-store';
import type { Rational } from '@/lib/format';
import { frameToSeconds, secondsToFrame } from '@/lib/media-time';
import { useWaveform } from '@/lib/queries';
import { frameToTimecode } from '@/lib/timecode';
import { durationFrames, moveCut, switchAt } from '@/lib/timeline-edit';
import { cn } from '@/lib/utils';

import { WaveformCanvas } from './waveform-canvas';

const GUTTER = 132; // px, lane labels
const RULER_H = 24;
const PROGRAM_H = 36;
const LANE_H = 48;
const WAVE_RATE = 50;
const TICK_STEPS = [1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 1200];

export function tickStep(zoom: number, minPx = 80): number {
  return TICK_STEPS.find((s) => s * zoom >= minPx) ?? TICK_STEPS[TICK_STEPS.length - 1]!;
}

interface Viewport {
  left: number;
  width: number;
}

function Ruler({ seconds, zoom, fps }: { seconds: number; zoom: number; fps: Rational }) {
  const step = tickStep(zoom);
  const ticks: number[] = [];
  for (let t = 0; t <= seconds; t += step) ticks.push(t);
  return (
    <div className="relative border-b bg-muted/40" style={{ height: RULER_H }}>
      {ticks.map((t) => (
        <div
          key={t}
          className="absolute top-0 h-full border-l border-border pl-1 text-[10px] leading-6 text-muted-foreground"
          style={{ left: t * zoom }}
        >
          {frameToTimecode(secondsToFrame(t, fps), fps).slice(0, 8)}
        </div>
      ))}
    </div>
  );
}

function Playhead({ store, fps, height }: { store: EditorStore; fps: Rational; height: number }) {
  const playhead = useStore(store, (s) => s.playhead);
  const zoom = useStore(store, (s) => s.zoom);
  return (
    <div
      data-testid="playhead"
      className="pointer-events-none absolute top-0 z-20 w-px bg-red-500"
      style={{ left: frameToSeconds(playhead, fps) * zoom, height }}
    >
      <div className="-ml-1.5 size-3 rotate-45 bg-red-500" />
    </div>
  );
}

function CameraLane({
  clip,
  number,
  clips,
  timing,
  store,
  fps,
  viewport,
}: {
  clip: Clip;
  number: number;
  clips: Clip[];
  timing: TimelineClip | undefined;
  store: EditorStore;
  fps: Rational;
  viewport: Viewport;
}) {
  const cut = useStore(store, (s) => s.cut);
  const zoom = useStore(store, (s) => s.zoom);
  const wave = useWaveform(clip.id, WAVE_RATE, !!timing?.has_audio);
  const color = cameraColor(clips, clip.id);
  const recStart = timing ? Math.max(0, -timing.media_offset_s / timing.speed) : 0;
  const recEnd = timing ? (timing.duration_s - timing.media_offset_s) / timing.speed : 0;

  function onDoubleClick(e: ReactMouseEvent<HTMLDivElement>) {
    const rect = e.currentTarget.getBoundingClientRect();
    const frame = secondsToFrame((e.clientX - rect.left) / zoom, fps);
    store.getState().seek(frame);
    store.getState().edit((c) => switchAt(c, frame, clip.id));
  }

  return (
    <div
      data-testid="camera-lane"
      aria-label={`Camera ${number}: ${clipDisplayName(clip)}`}
      className="relative border-b bg-muted/60"
      style={{ height: LANE_H }}
      onDoubleClick={onDoubleClick}
      title="Double-click: switch to this camera from here"
    >
      {timing && (
        <div
          className="absolute inset-y-0 bg-background"
          style={{ left: recStart * zoom, width: Math.max(0, recEnd - recStart) * zoom }}
        />
      )}
      {cut.segments
        .filter((s) => s.clip_id === clip.id)
        .map((s) => (
          <div
            key={s.start_frame}
            className={cn('absolute inset-y-0 opacity-30', color)}
            style={{
              left: frameToSeconds(s.start_frame, fps) * zoom,
              width: frameToSeconds(s.end_frame - s.start_frame, fps) * zoom,
            }}
          />
        ))}
      {timing && (
        <WaveformCanvas
          peaks={wave.data?.peaks}
          rate={wave.data?.rate ?? WAVE_RATE}
          timing={timing}
          zoom={zoom}
          left={viewport.left}
          width={viewport.width}
          height={LANE_H}
        />
      )}
    </div>
  );
}

function ProgramLane({ store, clips, fps }: { store: EditorStore; clips: Clip[]; fps: Rational }) {
  const cut = useStore(store, (s) => s.cut);
  const zoom = useStore(store, (s) => s.zoom);
  const selected = useStore(store, (s) => s.selected);
  const [drag, setDrag] = useState<{ index: number; frame: number } | null>(null);
  const laneRef = useRef<HTMLDivElement>(null);

  const frameAt = useCallback(
    (clientX: number) => {
      const rect = laneRef.current!.getBoundingClientRect();
      return secondsToFrame((clientX - rect.left) / zoom, fps);
    },
    [zoom, fps],
  );

  function startDrag(index: number, e: PointerEvent<HTMLDivElement>) {
    e.stopPropagation();
    e.currentTarget.setPointerCapture(e.pointerId);
    setDrag({ index, frame: cut.segments[index]!.start_frame });
  }

  return (
    <div
      ref={laneRef}
      data-testid="program-lane"
      className="relative border-b"
      style={{ height: PROGRAM_H }}
    >
      {cut.segments.map((s, i) => {
        const clip = clips.find((c) => c.id === s.clip_id);
        const number = clips.findIndex((c) => c.id === s.clip_id) + 1;
        return (
          <button
            key={`${s.start_frame}-${s.clip_id}`}
            type="button"
            data-testid="shot"
            aria-pressed={selected === i}
            aria-label={`Shot ${i + 1}: ${clip ? clipDisplayName(clip) : 'camera'} at ${frameToTimecode(s.start_frame, fps)}`}
            className={cn(
              'absolute inset-y-1 overflow-hidden rounded-sm border border-background/60 px-1 text-left text-[10px] font-medium text-white',
              cameraColor(clips, s.clip_id),
              selected === i && 'ring-2 ring-foreground ring-offset-1',
            )}
            style={{
              left: frameToSeconds(s.start_frame, fps) * zoom,
              width: Math.max(1, frameToSeconds(s.end_frame - s.start_frame, fps) * zoom),
            }}
            onClick={(e) => {
              store.getState().select(i);
              store.getState().seek(frameAt(e.clientX));
            }}
          >
            {number > 0 ? number : '?'}
          </button>
        );
      })}
      {cut.segments.slice(1).map((s, k) => {
        const index = k + 1;
        const x = frameToSeconds(drag?.index === index ? drag.frame : s.start_frame, fps) * zoom;
        return (
          <div
            key={`cut-${s.start_frame}`}
            role="separator"
            aria-label={`Cut ${index} at ${frameToTimecode(s.start_frame, fps)}`}
            className="absolute inset-y-0 z-10 w-2 -translate-x-1/2 cursor-ew-resize touch-none hover:bg-foreground/30"
            style={{ left: x }}
            onPointerDown={(e) => startDrag(index, e)}
            onPointerMove={(e) =>
              drag?.index === index && setDrag({ index, frame: frameAt(e.clientX) })
            }
            onPointerUp={(e) => {
              if (drag?.index !== index) return;
              const frame = frameAt(e.clientX);
              setDrag(null);
              store.getState().edit((c) => moveCut(c, index, frame));
            }}
          />
        );
      })}
    </div>
  );
}

export function Timeline({
  store,
  clips,
  timings,
  fps,
}: {
  store: EditorStore;
  clips: Clip[];
  timings: Map<string, TimelineClip>;
  fps: Rational;
}) {
  const cut = useStore(store, (s) => s.cut);
  const zoom = useStore(store, (s) => s.zoom);
  const playing = useStore(store, (s) => s.playing);
  const scrollRef = useRef<HTMLDivElement>(null);
  const [viewport, setViewport] = useState<Viewport>({ left: 0, width: 800 });
  const seconds = frameToSeconds(durationFrames(cut), fps);
  const height = RULER_H + PROGRAM_H + LANE_H * clips.length;

  const measure = useCallback(() => {
    const el = scrollRef.current;
    if (el) setViewport({ left: el.scrollLeft, width: Math.max(1, el.clientWidth - GUTTER) });
  }, []);

  useEffect(() => {
    measure();
    window.addEventListener('resize', measure);
    return () => window.removeEventListener('resize', measure);
  }, [measure, zoom]);

  // Keep the playhead in view while playing.
  useEffect(() => {
    if (!playing) return;
    return store.subscribe((s) => {
      const el = scrollRef.current;
      if (!el) return;
      const x = frameToSeconds(s.playhead, fps) * s.zoom;
      const visible = el.clientWidth - GUTTER;
      if (x < el.scrollLeft || x > el.scrollLeft + visible - 40) el.scrollLeft = x - visible * 0.2;
    });
  }, [playing, store, fps]);

  function seekFromEvent(e: ReactMouseEvent<HTMLDivElement>) {
    const rect = e.currentTarget.getBoundingClientRect();
    store.getState().seek(secondsToFrame((e.clientX - rect.left) / zoom, fps));
  }

  return (
    <div className="flex overflow-hidden rounded-lg border" data-testid="timeline">
      <div className="shrink-0 border-r bg-card text-xs" style={{ width: GUTTER }}>
        <div style={{ height: RULER_H }} className="border-b" />
        <div style={{ height: PROGRAM_H }} className="flex items-center border-b px-2 font-medium">
          Program
        </div>
        {clips.map((clip, i) => (
          <div
            key={clip.id}
            style={{ height: LANE_H }}
            className="flex items-center gap-2 border-b px-2"
          >
            <span
              className={cn(
                'flex size-5 items-center justify-center rounded text-[10px] font-bold text-white',
                cameraColor(clips, clip.id),
              )}
            >
              {i + 1}
            </span>
            <span className="truncate" title={clip.path}>
              {clipDisplayName(clip)}
            </span>
          </div>
        ))}
      </div>
      <div ref={scrollRef} className="relative flex-1 overflow-x-auto" onScroll={measure}>
        <div className="relative" style={{ width: seconds * zoom + 200, height }}>
          <div onClick={seekFromEvent} className="cursor-pointer">
            <Ruler seconds={seconds} zoom={zoom} fps={fps} />
          </div>
          <ProgramLane store={store} clips={clips} fps={fps} />
          {clips.map((clip, i) => (
            <div key={clip.id} onClick={seekFromEvent}>
              <CameraLane
                clip={clip}
                number={i + 1}
                clips={clips}
                timing={timings.get(clip.id)}
                store={store}
                fps={fps}
                viewport={viewport}
              />
            </div>
          ))}
          <Playhead store={store} fps={fps} height={height} />
        </div>
      </div>
    </div>
  );
}
