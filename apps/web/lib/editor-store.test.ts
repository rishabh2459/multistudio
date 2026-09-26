import { makeCutlist } from '@/test/fixtures';

import { createEditorStore, MAX_HISTORY, ZOOM_MAX } from './editor-store';
import { setCamera, split } from './timeline-edit';

const cut = () =>
  makeCutlist([
    ['a', 0, 100],
    ['b', 100, 200],
  ]);

describe('editor store', () => {
  it('records edits for undo / redo and marks the edit unsaved', () => {
    const store = createEditorStore(cut(), 3);
    const s = () => store.getState();
    expect(s().save).toEqual({ state: 'saved', version: 3 });
    s().edit((c) => split(c, 50));
    expect(s().cut.segments).toHaveLength(3);
    expect(s().save.state).toBe('dirty');
    s().edit((c) => setCamera(c, 2, 'a'));
    s().undo();
    expect(s().cut.segments).toHaveLength(3);
    s().undo();
    expect(s().cut.segments).toHaveLength(2);
    s().undo(); // nothing left
    s().redo();
    expect(s().cut.segments).toHaveLength(3);
    s().edit((c) => split(c, 150)); // a new edit clears the redo stack
    expect(s().future).toHaveLength(0);
  });

  it('ignores edits that change nothing', () => {
    const store = createEditorStore(cut(), 1);
    store.getState().edit((c) => split(c, 100));
    expect(store.getState().past).toHaveLength(0);
    expect(store.getState().save.state).toBe('saved');
  });

  it('caps history, clamps the playhead, zoom and selection', () => {
    const store = createEditorStore(cut(), 1);
    const s = () => store.getState();
    for (let i = 0; i < MAX_HISTORY + 20; i++) s().edit((c) => setCamera(c, 0, i % 2 ? 'a' : 'c'));
    expect(s().past.length).toBe(MAX_HISTORY);
    s().seek(1e9);
    expect(s().playhead).toBe(199);
    s().seek(-4);
    expect(s().playhead).toBe(0);
    s().setZoom(1e6);
    expect(s().zoom).toBe(ZOOM_MAX);
    s().select(1);
    s().edit((c) => setCamera(c, 1, s().cut.segments[0]!.clip_id)); // merges into 1 shot
    expect(s().selected).toBe(0);
  });
});
