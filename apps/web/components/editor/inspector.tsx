'use client';

import { Merge, Scissors, Trash2 } from 'lucide-react';
import { useStore } from 'zustand';

import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Select } from '@/components/ui/select';
import type { Clip, TimelineClip } from '@/lib/api';
import { clipDisplayName } from '@/lib/cutlist';
import { SHORTCUTS } from '@/lib/editor-keys';
import type { EditorStore } from '@/lib/editor-store';
import type { Rational } from '@/lib/format';
import { frameToSeconds } from '@/lib/media-time';
import { frameToTimecode } from '@/lib/timecode';
import {
  mergeWithNext,
  removeSegment,
  segmentIndexAt,
  setCamera,
  split,
} from '@/lib/timeline-edit';

import { FramingControls } from './framing-controls';

export function Inspector({
  store,
  clips,
  timings,
  fps,
}: {
  store: EditorStore;
  clips: Clip[];
  timings?: Map<string, TimelineClip>;
  fps: Rational;
}) {
  const cut = useStore(store, (s) => s.cut);
  const selected = useStore(store, (s) => s.selected);
  const playhead = useStore(store, (s) => Math.floor(s.playhead));
  const index = selected ?? segmentIndexAt(cut, playhead);
  const seg = cut.segments[index];
  const s = store.getState;
  if (!seg) return null;

  return (
    <div className="flex flex-col gap-4 text-sm" data-testid="inspector">
      <div>
        <h3 className="font-medium">
          Shot {index + 1} of {cut.segments.length}
          {seg.source === 'manual' && (
            <span className="ml-2 text-xs font-normal text-muted-foreground">edited</span>
          )}
        </h3>
        <p className="font-mono text-xs text-muted-foreground">
          {frameToTimecode(seg.start_frame, fps)} → {frameToTimecode(seg.end_frame, fps)} (
          {frameToSeconds(seg.end_frame - seg.start_frame, fps).toFixed(1)} s)
        </p>
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="shot-camera">Camera</Label>
        <Select
          id="shot-camera"
          value={seg.clip_id}
          onChange={(e) => s().edit((c) => setCamera(c, index, e.target.value))}
        >
          {clips.map((clip, i) => (
            <option key={clip.id} value={clip.id}>
              {i + 1} · {clipDisplayName(clip)}
            </option>
          ))}
        </Select>
      </div>
      <div className="flex flex-wrap gap-2">
        <Button
          size="sm"
          variant="outline"
          onClick={() => s().edit((c) => split(c, Math.floor(s().playhead)))}
        >
          <Scissors /> Cut at playhead
        </Button>
        <Button
          size="sm"
          variant="outline"
          disabled={index >= cut.segments.length - 1}
          onClick={() => s().edit((c) => mergeWithNext(c, index))}
        >
          <Merge /> Merge with next
        </Button>
        <Button
          size="sm"
          variant="outline"
          disabled={cut.segments.length < 2}
          onClick={() => s().edit((c) => removeSegment(c, index))}
        >
          <Trash2 /> Remove shot
        </Button>
      </div>
      <FramingControls store={store} index={index} timing={timings?.get(seg.clip_id)} />
      <dl className="grid grid-cols-[6rem_1fr] gap-x-2 gap-y-1 text-xs">
        {SHORTCUTS.map(([keys, what]) => (
          <div key={keys} className="contents">
            <dt className="font-mono text-muted-foreground">{keys}</dt>
            <dd>{what}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
