import './dom';

import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { AutoEditController } from '../src/session';
import { AutoEditPanel } from '../src/ui';
import { FakeHost, fakeEngineHost } from './fake-host';
import { loadPlan, mockFetch } from './helpers';

const plan = loadPlan();
const hs = {
  engine_version: 'x',
  api_version: '1.0.0',
  capabilities: [],
  models: { vad: true, face: true, asr: false },
  licence: { status: 'dev' },
  data_dir: '/d',
  pid: 1,
};
const clip = (id: string, name: string, role: string) => ({
  clip_id: id,
  path: `/m/${name}`,
  name,
  kind: 'video',
  role,
  label: role === 'speaker' ? name.split('.')[0] : null,
  host_ref: null,
  track: null,
  file_status: 'ok',
  synced: false,
  sync_confidence: null,
});
function session(reused: boolean, preset = 'balanced') {
  return {
    id: 's1',
    project_id: 'p1',
    reused,
    host: { app: 'premiere', version: '', os: '' },
    host_sequence_id: 'x',
    already_synced: false,
    method: 'stacked_enable',
    state: reused ? 'ready' : 'setup',
    name: 'Demo',
    clips: [
      clip('c1', 'cam1.mp4', 'speaker'),
      clip('c2', 'cam2.mp4', 'speaker'),
      clip('c3', 'wide.mp4', 'wide'),
    ],
    speakers: [
      { id: 'a', name: 'cam1' },
      { id: 'b', name: 'cam2' },
    ],
    cameras: [
      { clip_id: 'c1', shot: 'solo', covers: ['a'] },
      { clip_id: 'c2', shot: 'solo', covers: ['b'] },
      { clip_id: 'c3', shot: 'wide', covers: ['a', 'b'] },
    ],
    layout_custom: false,
    preset,
    switch: {
      min_shot_s: 2,
      switch_delay_s: 0.6,
      wide_frequency: 0.3,
      lead_s: 0.1,
      bridge_gap_s: 1,
      crosstalk_to_wide_s: 2,
      silence_to_wide_s: 4,
    },
    switch_custom: false,
    job: null,
    plan: reused
      ? { cutlist_version: 2, source: 'auto', cuts: 7, duration_frames: 1, low_confidence_cuts: 0 }
      : null,
    warnings: [],
  };
}

function setupEngine() {
  let current = session(false);
  const engine = mockFetch((method, url, body) => {
    const p = url.pathname;
    if (p.endsWith('/handshake')) return { body: hs };
    if (p.endsWith('/sessions') && method === 'POST') return { body: current };
    if (p.endsWith('/setup')) {
      current = { ...current, ...(body as object & { preset?: string }) } as typeof current;
      return { body: current };
    }
    if (p.endsWith('/run'))
      return { status: 202, body: { job_id: 'j1', kind: 'auto', events_url: '' } };
    if (p.endsWith('/events')) return { status: 404, body: {} }; // force the polling path
    if (p.endsWith('/sessions/s1')) {
      current = session(true, current.preset);
      return {
        body: {
          ...current,
          job: {
            id: 'j1',
            status: 'succeeded',
            stage: 'done',
            progress: 1,
            message: 'done',
            error: null,
          },
        },
      };
    }
    if (p.endsWith('/editplan')) return { body: plan };
    return { status: 404, body: { code: 'not_found', message: p, hint: '' } };
  });
  return engine;
}

afterEach(() => cleanup());

describe('AutoEditPanel', () => {
  it('walks connect -> setup -> review -> applied', async () => {
    const engine = setupEngine();
    const host = new FakeHost({} as never);
    const c = new AutoEditController(
      host,
      fakeEngineHost(() => '{"port":1,"token":"t","pid":1,"api":"1.0.0"}'),
      {
        client: { fetch: engine.fetch },
        pollMs: 1,
      },
    );
    render(<AutoEditPanel controller={c} hostLabel="Premiere Pro" />);
    expect(screen.getByText('Multicam Studio for Premiere Pro')).toBeTruthy();

    await act(async () => {
      fireEvent.click(screen.getByText('Connect'));
    });
    expect(c.getState().phase).toBe('setup');
    expect(screen.getByLabelText('Role of wide.mp4')).toBeTruthy();
    expect((screen.getByLabelText('Speaker on cam1.mp4') as HTMLInputElement).value).toBe('cam1');

    await act(async () => {
      fireEvent.change(screen.getByLabelText('Speaker on cam1.mp4'), {
        target: { value: 'Rishabh' },
      });
    });
    await act(async () => {
      fireEvent.change(screen.getByLabelText('Editing style'), { target: { value: 'punchy' } });
    });
    expect(
      engine.calls.some(
        (x) => x.url.endsWith('/setup') && (x.body as { preset?: string }).preset === 'punchy',
      ),
    ).toBe(true);

    await act(async () => {
      fireEvent.click(screen.getByText('Auto Edit'));
    });
    const named = engine.calls.find(
      (x) => x.url.endsWith('/setup') && JSON.stringify(x.body).includes('Rishabh'),
    );
    expect(named).toBeTruthy();
    expect(c.getState().phase).toBe('review');
    expect(screen.getByLabelText('plan preview').textContent).toMatch(/7 cuts/);
    expect(screen.getAllByRole('img')).toHaveLength(3); // one lane per camera

    await act(async () => {
      fireEvent.click(screen.getByText('Apply to timeline'));
    });
    expect(c.getState().phase).toBe('applied');
    expect(screen.getByText(/Undo removes it in one step/)).toBeTruthy();
    expect(host.sequences).toHaveLength(1);
  });

  it('shows Start engine when the engine is not running', async () => {
    const c = new AutoEditController(
      new FakeHost({} as never),
      fakeEngineHost(() => null),
    );
    render(<AutoEditPanel controller={c} />);
    await act(async () => {
      fireEvent.click(screen.getByText('Connect'));
    });
    expect(screen.getByRole('alert').textContent).toMatch(/not running/);
    expect(screen.getByText('Start engine')).toBeTruthy();
  });
});
