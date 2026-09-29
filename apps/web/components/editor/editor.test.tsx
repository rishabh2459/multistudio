import { fireEvent, render, screen, waitFor } from '@testing-library/react';

import type { CutListOut, Job, TimelineClip } from '@/lib/api';
import { createEditorStore } from '@/lib/editor-store';
import { useSettings } from '@/lib/settings-store';
import { mockFetch } from '@/test/fetch';
import { makeClip, makeCutlist, makeJob, makeProject, T0 } from '@/test/fixtures';
import { renderWithClient } from '@/test/render';

import { EditorView, runAction } from './editor-view';
import { Inspector } from './inspector';
import { ProgramMonitor, syncVideo } from './program-monitor';
import { tickStep, Timeline } from './timeline';

const FPS = { num: 30, den: 1 };
const clips = [
  makeClip({ id: 'a', speaker_label: 'Host' }),
  makeClip({ id: 'b', speaker_label: 'Guest', name: 'cam2.mp4' }),
];
const timing = (id: string, over: Partial<TimelineClip> = {}): TimelineClip => ({
  clip_id: id,
  speed: 1,
  media_offset_s: 0,
  audio_offset_s: 0,
  duration_s: 60,
  fps: FPS,
  has_audio: false,
  has_proxy: false,
  width: 1920,
  height: 1080,
  ...over,
});
const timings = new Map([
  ['a', timing('a')],
  ['b', timing('b', { media_offset_s: 1 })],
]);
const cut = () =>
  makeCutlist([
    ['a', 0, 300],
    ['b', 300, 900],
  ]);

beforeEach(() => {
  useSettings.getState().reset();
  useSettings.getState().update({ apiUrl: 'http://api.test' });
});
afterEach(() => vi.unstubAllGlobals());

describe('Timeline', () => {
  it('shows shots on the program lane and a lane per camera', () => {
    const store = createEditorStore(cut(), 1);
    renderWithClient(<Timeline store={store} clips={clips} timings={timings} fps={FPS} />);
    const shots = screen.getAllByTestId('shot');
    expect(shots).toHaveLength(2);
    expect(shots[1]).toHaveAccessibleName(/Shot 2: Guest at 00:00:10:00/);
    expect(screen.getAllByTestId('camera-lane')).toHaveLength(2);
    expect(screen.getAllByRole('separator')).toHaveLength(1);
    fireEvent.click(shots[1]!);
    expect(store.getState().selected).toBe(1);
    expect(shots[1]).toHaveAttribute('aria-pressed', 'true');
  });

  it('picks readable ruler steps', () => {
    expect(tickStep(40)).toBe(2);
    expect(tickStep(2)).toBe(60);
    expect(tickStep(400)).toBe(1);
  });
});

describe('ProgramMonitor', () => {
  it('shows the camera on air and switches from the playhead on click', () => {
    const store = createEditorStore(cut(), 1);
    store.getState().seek(450);
    render(
      <ProgramMonitor store={store} clips={clips} timings={timings} fps={FPS} audioClipId="a" />,
    );
    expect(screen.getByRole('button', { name: /camera 2/ })).toHaveAttribute(
      'aria-current',
      'true',
    );
    fireEvent.click(screen.getByRole('button', { name: /camera 1/ }));
    expect(store.getState().cut.segments.map((s) => [s.clip_id, s.start_frame])).toEqual([
      ['a', 0],
      ['b', 300],
      ['a', 450],
    ]);
    expect(screen.getAllByText('Preparing preview…')).toHaveLength(2);
  });

  it('keeps videos in sync without seeking on every frame', () => {
    const video = {
      paused: true,
      currentTime: 10,
      playbackRate: 1,
      pause: vi.fn(),
      play: vi.fn(async () => undefined),
    };
    const v = video as unknown as HTMLVideoElement;
    syncVideo(v, 10.01, true, false, 1, 1 / 60);
    expect(video.currentTime).toBe(10); // within half a frame: no seek
    syncVideo(v, 12, true, false, 1, 1 / 60);
    expect(video.currentTime).toBe(12);
    syncVideo(v, 12.1, true, true, 1.0001, 1 / 60);
    expect(video.play).toHaveBeenCalled();
    expect(video.currentTime).toBe(12); // small drift while playing is tolerated
    video.paused = false;
    syncVideo(v, 20, false, true, 1, 1 / 60);
    expect(video.pause).toHaveBeenCalled();
  });
});

describe('keyboard actions', () => {
  it('switches cameras, cuts, deletes, undoes', () => {
    const store = createEditorStore(cut(), 1);
    const s = () => store.getState();
    s().seek(600);
    runAction(store, { type: 'camera', index: 0 }, ['a', 'b'], FPS);
    expect(s().cut.segments).toHaveLength(3);
    runAction(store, { type: 'undo' }, ['a', 'b'], FPS);
    expect(s().cut.segments).toHaveLength(2);
    runAction(store, { type: 'split' }, ['a', 'b'], FPS);
    expect(s().cut.segments).toHaveLength(3);
    runAction(store, { type: 'jumpCut', direction: -1 }, ['a', 'b'], FPS);
    expect(s().playhead).toBe(300);
    runAction(store, { type: 'back', seconds: 5 }, ['a', 'b'], FPS);
    expect(s().playhead).toBe(150);
    runAction(store, { type: 'delete' }, ['a', 'b'], FPS); // shot 1 removed: camera b throughout
    expect(s().cut.segments.map((x) => x.clip_id)).toEqual(['b']);
    runAction(store, { type: 'play', faster: true }, ['a', 'b'], FPS);
    runAction(store, { type: 'play', faster: true }, ['a', 'b'], FPS);
    expect([s().playing, s().rate]).toEqual([true, 2]);
    runAction(store, { type: 'camera', index: 7 }, ['a', 'b'], FPS); // no 8th camera
    expect(s().cut.segments).toHaveLength(1);
  });
});

describe('EditorView', () => {
  it('saves each change as a new version and starts the previews', async () => {
    const project = makeProject({ clips, reference_clip_id: 'a', cutlist_version: 1 });
    const initial: CutListOut = { version: 1, source: 'auto', created_at: T0, cutlist: cut() };
    const calls = mockFetch({
      'GET /api/projects/proj-1/timeline': {
        fps: FPS,
        duration_frames: 900,
        clips: [timing('a'), timing('b')],
        proxies_ready: false,
      },
      'POST /api/projects/proj-1/jobs': makeJob({ kind: 'proxy', status: 'queued' }),
      'PUT /api/projects/proj-1/cutlist': { ...initial, version: 2, source: 'manual' },
      'GET /api/projects/proj-1': project,
    });
    const jobs: Job[] = [];
    renderWithClient(
      <EditorView project={project} cutlist={initial} jobs={jobs} onNext={() => undefined} />,
    );
    await waitFor(() =>
      expect(
        calls.some((c) => c.method === 'POST' && (c.body as { kind: string }).kind === 'proxy'),
      ).toBe(true),
    );
    fireEvent.keyDown(window, { key: '2', code: 'Digit2' }); // playhead 0: shot 1 -> camera 2
    expect(screen.getByTestId('save-status')).toHaveTextContent('Unsaved changes');
    await waitFor(
      () => expect(screen.getByTestId('save-status')).toHaveTextContent('Saved (version 2)'),
      {
        timeout: 3000,
      },
    );
    const put = calls.find((c) => c.method === 'PUT');
    expect((put!.body as { cutlist: ReturnType<typeof cut> }).cutlist.segments).toEqual([
      expect.objectContaining({ clip_id: 'b', start_frame: 0, end_frame: 900, source: 'manual' }),
    ]);
  });
});

describe('framing', () => {
  it('edits zoom and position per output shape and resets', () => {
    const store = createEditorStore(cut(), 1);
    renderWithClient(<Inspector store={store} clips={clips} timings={timings} fps={FPS} />);
    const seg = () => store.getState().cut.segments[0]!;

    fireEvent.change(screen.getByLabelText('Zoom'), { target: { value: '2' } });
    expect(seg().reframe).toMatchObject({ scale: 2, manual: true, path: null });
    expect(seg().reframe_vertical).toBeNull();
    expect(screen.getByTestId('framing')).toHaveTextContent('manual');

    fireEvent.click(screen.getByRole('button', { name: '9:16' }));
    expect(store.getState().aspect).toBe('9:16');
    fireEvent.change(screen.getByLabelText('Left/right'), { target: { value: '0' } });
    // Clamped so the crop stays inside the frame.
    expect(seg().reframe_vertical!.cx).toBeCloseTo(0.1582, 3);

    fireEvent.click(screen.getByRole('button', { name: /Reset framing/ }));
    expect(seg().reframe_vertical).toBeNull();
    expect(seg().reframe?.scale).toBe(2);
  });

  it('shows the zoom on the shot and crops the live preview', () => {
    const store = createEditorStore(cut(), 1);
    store.getState().edit((c) => ({
      ...c,
      segments: c.segments.map((x, i) =>
        i === 0
          ? { ...x, reframe: { cx: 0.5, cy: 0.5, scale: 1.3, path: null, manual: false } }
          : x,
      ),
    }));
    const withProxy = new Map([...timings].map(([k, v]) => [k, { ...v, has_proxy: true }]));
    renderWithClient(<Timeline store={store} clips={clips} timings={withProxy} fps={FPS} />);
    expect(screen.getAllByTestId('shot-zoom')[0]).toHaveTextContent('1.3×');
    renderWithClient(
      <ProgramMonitor store={store} clips={clips} timings={withProxy} fps={FPS} audioClipId="a" />,
    );
    expect(screen.getByTestId('framed-preview')).toBeInTheDocument();
  });
});
