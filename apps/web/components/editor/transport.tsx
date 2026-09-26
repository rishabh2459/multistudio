'use client';

import { Pause, Play, Redo2, SkipBack, SkipForward, Undo2, ZoomIn } from 'lucide-react';
import { useStore } from 'zustand';

import { Button } from '@/components/ui/button';
import type { EditorStore, SaveStatus } from '@/lib/editor-store';
import { ZOOM_MAX, ZOOM_MIN } from '@/lib/editor-store';
import type { Rational } from '@/lib/format';
import { frameToTimecode } from '@/lib/timecode';
import { durationFrames, nextCut, previousCut } from '@/lib/timeline-edit';

export function saveLabel(save: SaveStatus): string {
  switch (save.state) {
    case 'saved':
      return `Saved (version ${save.version})`;
    case 'dirty':
      return 'Unsaved changes…';
    case 'saving':
      return 'Saving…';
    case 'error':
      return `Not saved: ${save.message}`;
  }
}

export function Transport({ store, fps }: { store: EditorStore; fps: Rational }) {
  const playhead = useStore(store, (s) => Math.floor(s.playhead));
  const playing = useStore(store, (s) => s.playing);
  const rate = useStore(store, (s) => s.rate);
  const zoom = useStore(store, (s) => s.zoom);
  const canUndo = useStore(store, (s) => s.past.length > 0);
  const canRedo = useStore(store, (s) => s.future.length > 0);
  const save = useStore(store, (s) => s.save);
  const total = useStore(store, (s) => durationFrames(s.cut));
  const s = store.getState;
  const logZoom = Math.log(zoom);

  return (
    <div className="flex flex-wrap items-center gap-2" data-testid="transport">
      <Button
        size="icon"
        variant="outline"
        aria-label="Previous cut"
        onClick={() => s().seek(previousCut(s().cut, Math.floor(s().playhead)))}
      >
        <SkipBack />
      </Button>
      <Button
        size="icon"
        aria-label={playing ? 'Pause' : 'Play'}
        onClick={() => s().setPlaying(!playing, 1)}
      >
        {playing ? <Pause /> : <Play />}
      </Button>
      <Button
        size="icon"
        variant="outline"
        aria-label="Next cut"
        onClick={() => s().seek(nextCut(s().cut, Math.floor(s().playhead)))}
      >
        <SkipForward />
      </Button>
      <span className="font-mono text-sm tabular-nums" data-testid="timecode">
        {frameToTimecode(playhead, fps)}
      </span>
      <span className="font-mono text-xs text-muted-foreground tabular-nums">
        / {frameToTimecode(total, fps)}
      </span>
      {playing && rate !== 1 && <span className="text-xs font-semibold">{rate}×</span>}
      <div className="mx-2 flex items-center gap-1">
        <Button
          size="icon"
          variant="ghost"
          aria-label="Undo"
          disabled={!canUndo}
          onClick={() => s().undo()}
        >
          <Undo2 />
        </Button>
        <Button
          size="icon"
          variant="ghost"
          aria-label="Redo"
          disabled={!canRedo}
          onClick={() => s().redo()}
        >
          <Redo2 />
        </Button>
      </div>
      <label className="flex items-center gap-2 text-xs text-muted-foreground">
        <ZoomIn className="size-4" aria-hidden />
        <input
          type="range"
          aria-label="Zoom"
          min={Math.log(ZOOM_MIN)}
          max={Math.log(ZOOM_MAX)}
          step={0.01}
          value={logZoom}
          onChange={(e) => s().setZoom(Math.exp(Number(e.target.value)))}
        />
      </label>
      <span
        className="ml-auto text-xs text-muted-foreground"
        aria-live="polite"
        data-testid="save-status"
      >
        {saveLabel(save)}
      </span>
    </div>
  );
}
