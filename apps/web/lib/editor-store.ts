/**
 * State of one open timeline editor: the edit with undo/redo history, the
 * playhead, playback, zoom, selection and save status. One store per project
 * page (createEditorStore), so nothing leaks between projects.
 */
import { createStore, type StoreApi } from 'zustand/vanilla';

import type { CutList } from './api';
import type { Aspect } from './framing';
import { durationFrames, sameEdit } from './timeline-edit';

export const MAX_HISTORY = 200;
export const ZOOM_MIN = 2; // px per second
export const ZOOM_MAX = 400;

export type SaveStatus =
  | { state: 'saved'; version: number }
  | { state: 'dirty' }
  | { state: 'saving' }
  | { state: 'error'; message: string };

export interface EditorState {
  cut: CutList;
  past: CutList[];
  future: CutList[];
  selected: number | null;
  playhead: number; // frame
  playing: boolean;
  rate: number; // 1, 2, 4
  zoom: number; // px per second
  aspect: Aspect; // which framing the editor shows and edits
  save: SaveStatus;

  /** Apply an edit (ignored if it changes nothing). */
  edit: (fn: (cut: CutList) => CutList) => void;
  undo: () => void;
  redo: () => void;
  select: (index: number | null) => void;
  seek: (frame: number) => void;
  setPlaying: (playing: boolean, rate?: number) => void;
  setZoom: (zoom: number) => void;
  setAspect: (aspect: Aspect) => void;
  setSave: (save: SaveStatus) => void;
}

export type EditorStore = StoreApi<EditorState>;

export function createEditorStore(initial: CutList, version: number, zoom = 40): EditorStore {
  return createStore<EditorState>()((set, get) => ({
    cut: initial,
    past: [],
    future: [],
    selected: null,
    playhead: 0,
    playing: false,
    rate: 1,
    zoom,
    aspect: '16:9',
    save: { state: 'saved', version },

    edit: (fn) => {
      const { cut, past } = get();
      const next = fn(cut);
      if (next === cut || sameEdit(next, cut)) return;
      set({
        cut: next,
        past: [...past, cut].slice(-MAX_HISTORY),
        future: [],
        selected: clampSelection(get().selected, next),
        save: { state: 'dirty' },
      });
    },
    undo: () => {
      const { past, cut, future } = get();
      const prev = past[past.length - 1];
      if (!prev) return;
      set({
        cut: prev,
        past: past.slice(0, -1),
        future: [cut, ...future],
        selected: clampSelection(get().selected, prev),
        save: { state: 'dirty' },
      });
    },
    redo: () => {
      const { past, cut, future } = get();
      const next = future[0];
      if (!next) return;
      set({
        cut: next,
        past: [...past, cut],
        future: future.slice(1),
        selected: clampSelection(get().selected, next),
        save: { state: 'dirty' },
      });
    },
    select: (index) => set({ selected: index }),
    seek: (frame) => {
      const end = Math.max(0, durationFrames(get().cut) - 1);
      set({ playhead: Math.min(Math.max(0, Math.round(frame)), end) });
    },
    setPlaying: (playing, rate) => set({ playing, rate: rate ?? get().rate }),
    setZoom: (value) => set({ zoom: Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, value)) }),
    setAspect: (aspect) => set({ aspect }),
    setSave: (save) => set({ save }),
  }));
}

function clampSelection(selected: number | null, cut: CutList): number | null {
  if (selected === null) return null;
  return Math.min(selected, cut.segments.length - 1);
}
