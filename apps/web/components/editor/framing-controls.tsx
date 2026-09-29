'use client';

import { RotateCcw } from 'lucide-react';
import { useStore } from 'zustand';

import { Button } from '@/components/ui/button';
import type { TimelineClip } from '@/lib/api';
import type { EditorStore } from '@/lib/editor-store';
import {
  ASPECT_SIZE,
  centerAt,
  clampCenter,
  cropSize,
  effectiveReframe,
  type Aspect,
  type Reframe,
} from '@/lib/framing';
import { setReframe } from '@/lib/timeline-edit';
import { cn } from '@/lib/utils';

export const ZOOM_RANGE: [number, number] = [1, 3];

function Slider({
  id,
  label,
  value,
  min,
  max,
  step,
  display,
  disabled,
  onChange,
}: {
  id: string;
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  display: string;
  disabled?: boolean;
  onChange: (value: number) => void;
}) {
  return (
    <div className="grid grid-cols-[3.5rem_1fr_2.75rem] items-center gap-2 text-xs">
      <label htmlFor={id} className="text-muted-foreground">
        {label}
      </label>
      <input
        id={id}
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(Number(e.target.value))}
        className="accent-primary"
      />
      <span className="text-right font-mono tabular-nums">{display}</span>
    </div>
  );
}

/**
 * Framing of the selected shot for the chosen output shape: zoom and crop
 * position. Any change makes the shot's framing manual, so "Auto framing"
 * keeps it.
 */
export function FramingControls({
  store,
  index,
  timing,
}: {
  store: EditorStore;
  index: number;
  timing: TimelineClip | undefined;
}) {
  const aspect = useStore(store, (s) => s.aspect);
  const seg = useStore(store, (s) => s.cut.segments[index]);
  const playhead = useStore(store, (s) => Math.floor(s.playhead));
  if (!seg) return null;

  const srcW = timing?.width ?? 1920;
  const srcH = timing?.height ?? 1080;
  const current = effectiveReframe(seg, aspect);
  const shown: Reframe = current ?? { cx: 0.5, cy: 0.5, scale: 1, path: null, manual: false };
  const [ow, oh] = ASPECT_SIZE[aspect];
  const [cw, ch] = cropSize(srcW, srcH, ow, oh, shown.scale);
  const at = Math.min(Math.max(playhead, seg.start_frame), seg.end_frame - 1);
  const [cx, cy] = clampCenter(...centerAt(shown, at), cw, ch);
  const auto = current !== null && !current.manual && (current.path?.length ?? 0) > 0;
  const stored = aspect === '16:9' ? seg.reframe : seg.reframe_vertical;

  const apply = (patch: Partial<Pick<Reframe, 'cx' | 'cy' | 'scale'>>) => {
    const scale = patch.scale ?? shown.scale;
    const [w, h] = cropSize(srcW, srcH, ow, oh, scale);
    const [x, y] = clampCenter(patch.cx ?? cx, patch.cy ?? cy, w, h);
    store.getState().edit((c) => setReframe(c, index, aspect, { ...shown, cx: x, cy: y, scale }));
  };

  return (
    <div className="flex flex-col gap-2" data-testid="framing">
      <div className="flex items-center justify-between gap-2">
        <h4 className="text-sm font-medium">
          Framing
          <span className="ml-2 text-xs font-normal text-muted-foreground">
            {stored?.manual
              ? 'manual'
              : auto
                ? 'auto · follows face'
                : stored
                  ? 'auto'
                  : 'full frame'}
          </span>
        </h4>
        <div role="group" aria-label="Output shape" className="flex rounded-md border p-0.5">
          {(['16:9', '9:16'] as Aspect[]).map((a) => (
            <button
              key={a}
              type="button"
              aria-pressed={aspect === a}
              className={cn(
                'rounded px-2 py-0.5 text-xs',
                aspect === a ? 'bg-primary text-primary-foreground' : 'text-muted-foreground',
              )}
              onClick={() => store.getState().setAspect(a)}
            >
              {a}
            </button>
          ))}
        </div>
      </div>
      <Slider
        id="frame-zoom"
        label="Zoom"
        value={shown.scale}
        min={ZOOM_RANGE[0]}
        max={ZOOM_RANGE[1]}
        step={0.05}
        display={`${shown.scale.toFixed(2)}×`}
        onChange={(scale) => apply({ scale })}
      />
      <Slider
        id="frame-x"
        label="Left/right"
        value={cx}
        min={0}
        max={1}
        step={0.005}
        display={`${Math.round(cx * 100)}%`}
        disabled={cw >= 0.999}
        onChange={(v) => apply({ cx: v })}
      />
      <Slider
        id="frame-y"
        label="Up/down"
        value={cy}
        min={0}
        max={1}
        step={0.005}
        display={`${Math.round(cy * 100)}%`}
        disabled={ch >= 0.999}
        onChange={(v) => apply({ cy: v })}
      />
      <Button
        size="sm"
        variant="ghost"
        className="self-start"
        disabled={!stored}
        onClick={() => store.getState().edit((c) => setReframe(c, index, aspect, null))}
      >
        <RotateCcw /> Reset framing
      </Button>
    </div>
  );
}
