import { afterAll, beforeAll, describe, expect, it } from 'vitest';

import { AutoEditController, type FlowState, type Phase } from '../src/session';
import type { SessionCreate } from '../src/types';
import { FakeHost, fakeEngineHost } from './fake-host';
import { loadPlan, mockFetch } from './helpers';
import { engineAvailable, startRealEngine, type RealEngine } from './real-engine';

function selection(
  media: { cam1: string; cam2: string; wide: string },
  id = 'seq-flow',
): SessionCreate {
  return {
    host: { app: 'premiere', version: '26.1', os: 'mac' },
    host_sequence_id: id,
    sequence: { fps: { num: 30000, den: 1001 }, width: 1280, height: 720, name: 'Ep 1' },
    clips: [
      { path: media.cam1, kind: 'video', host_ref: 'pp:1', track: 1, label: null },
      { path: media.cam2, kind: 'video', host_ref: 'pp:2', track: 2, label: null },
      { path: media.wide, kind: 'video', host_ref: 'pp:3', track: 3, label: null },
    ],
  } as SessionCreate;
}

function phases(controller: AutoEditController): Phase[] {
  const seen: Phase[] = [];
  controller.subscribe((s: FlowState) => {
    if (seen.at(-1) !== s.phase) seen.push(s.phase);
  });
  return seen;
}

const hasEngine = engineAvailable();

describe.skipIf(!hasEngine)('auto edit flow against the real engine', () => {
  let engine: RealEngine;
  beforeAll(async () => {
    engine = await startRealEngine();
  });
  afterAll(async () => {
    await engine?.stop();
  });

  it('connect -> setup -> run -> review -> apply, one undo step', async () => {
    const host = new FakeHost(selection(engine.media));
    const c = new AutoEditController(host, fakeEngineHost(engine.engineJson));
    const seen = phases(c);

    await c.connect();
    let s = c.getState();
    expect(s.error).toBeNull();
    expect(s.phase).toBe('setup');
    // auto-setup guessed the wide camera from its file name
    expect(s.session!.clips.map((x) => x.role)).toEqual(['speaker', 'speaker', 'wide']);
    expect(s.session!.speakers.length).toBe(2);

    await c.updateSetup({ preset: 'dynamic' });
    await c.run({ vad: 'energy' });
    s = c.getState();
    expect(s.error).toBeNull();
    expect(s.phase).toBe('review');
    expect(s.plan!.video_events.length).toBeGreaterThan(1);
    expect(s.plan!.host).toBe('premiere');
    expect(new Set(s.plan!.media.map((m) => m.host_ref))).toEqual(
      new Set(['pp:1', 'pp:2', 'pp:3']),
    );

    await c.apply();
    s = c.getState();
    expect(s.phase).toBe('applied');
    expect(s.applied!.via).toBe('native');
    expect(host.sequences).toHaveLength(1);
    const live = host.sequences[0]!.items.filter((i) => i.kind === 'video' && i.enabled);
    expect(live).toHaveLength(s.plan!.video_events.length);
    host.undo();
    expect(host.sequences).toHaveLength(0); // the whole apply is one undo step

    // re-cut with another preset: decide only, new version
    const before = s.plan!.cutlist_version;
    await c.recut('punchy');
    expect(c.getState().phase).toBe('review');
    expect(c.getState().plan!.cutlist_version).toBe(before + 1);

    // XML fallback path (Rule C) goes through the engine's export
    await c.apply({ viaXml: true });
    expect(c.getState().applied!.via).toBe('xml');
    expect(host.calls.some((x) => x.startsWith('importXml:') && x.endsWith('.xml'))).toBe(true);

    expect(seen.slice(0, 5)).toEqual(['connecting', 'setup', 'running', 'review', 'applying']);
  });

  it('a second panel on the same sequence reuses the session and its plan', async () => {
    const host = new FakeHost(selection(engine.media));
    const c = new AutoEditController(host, fakeEngineHost(engine.engineJson));
    await c.connect();
    expect(c.getState().session!.reused).toBe(true);
    expect(c.getState().phase).toBe('review'); // plan already there
  });

  it('polling works when the host cannot stream', async () => {
    const host = new FakeHost(selection(engine.media, 'seq-poll'));
    const c = new AutoEditController(host, fakeEngineHost(engine.engineJson), {
      poll: true,
      pollMs: 50,
    });
    await c.connect();
    await c.run({ vad: 'energy' });
    expect(c.getState().error).toBeNull();
    expect(c.getState().phase).toBe('review');
  });
});

describe('errors and fallbacks (mock engine)', () => {
  const hs = {
    engine_version: 'x',
    api_version: '1.0.0',
    capabilities: [],
    models: { vad: true, face: true, asr: false },
    licence: { status: 'dev' },
    data_dir: '/d',
    pid: 1,
  };
  const engineJson = () => JSON.stringify({ port: 1, token: 't', pid: 1, api: '1.0.0' });
  const plan = loadPlan();
  const session = {
    id: 's1',
    project_id: 'p1',
    reused: true,
    host: { app: 'premiere', version: '', os: '' },
    host_sequence_id: 'x',
    already_synced: false,
    method: 'stacked_enable',
    state: 'ready',
    name: 'Demo',
    clips: [],
    speakers: [],
    cameras: [],
    layout_custom: false,
    preset: 'balanced',
    switch: {},
    switch_custom: false,
    job: null,
    plan: {
      cutlist_version: 2,
      source: 'auto',
      cuts: 7,
      duration_frames: 1,
      low_confidence_cuts: 0,
    },
    warnings: [],
  };
  const engine = mockFetch((method, url) => {
    if (url.pathname.endsWith('/handshake')) return { body: hs };
    if (url.pathname.endsWith('/sessions') && method === 'POST') return { body: session };
    if (url.pathname.endsWith('/editplan')) return { body: plan };
    if (url.pathname.endsWith('/export'))
      return { body: { format: 'xmeml', path: '/x/plan.xml', cutlist_version: 2, warnings: [] } };
    if (url.pathname.endsWith('/run'))
      return {
        status: 422,
        body: {
          code: 'media_offline',
          message: 'offline media: cam2.mp4',
          hint: 'relink the media',
        },
      };
    return { status: 404, body: { code: 'not_found', message: 'nope', hint: '' } };
  });

  it('no engine: error with a Start engine path', async () => {
    const c = new AutoEditController(
      new FakeHost(selection({ cam1: 'a', cam2: 'b', wide: 'c' })),
      fakeEngineHost(() => null),
    );
    await c.connect();
    expect(c.getState()).toMatchObject({
      phase: 'error',
      resume: 'idle',
      error: { code: 'engine_unreachable' },
    });
    expect(c.getState().error!.hint).toMatch(/Start/);
    c.dismissError();
    expect(c.getState().phase).toBe('idle');
  });

  it('engine errors keep the user where they were, with the hint', async () => {
    const c = new AutoEditController(
      new FakeHost(selection({ cam1: 'a', cam2: 'b', wide: 'c' })),
      fakeEngineHost(engineJson),
      { client: { fetch: engine.fetch } },
    );
    await c.connect();
    expect(c.getState().phase).toBe('review');
    await c.run();
    expect(c.getState()).toMatchObject({
      phase: 'error',
      resume: 'review',
      error: { code: 'media_offline', hint: 'relink the media' },
    });
    c.dismissError();
    expect(c.getState().phase).toBe('review');
  });

  it('native apply failure falls back to XML import (Rule C) and adds markers', async () => {
    const host = new FakeHost(selection({ cam1: 'a', cam2: 'b', wide: 'c' }));
    host.failNative = 'track items are locked';
    const c = new AutoEditController(host, fakeEngineHost(engineJson), {
      client: { fetch: engine.fetch },
    });
    await c.connect();
    await c.apply();
    const s = c.getState();
    expect(s.phase).toBe('applied');
    expect(s.applied!.via).toBe('xml');
    expect(s.applied!.warnings[0]).toMatch(/track items are locked/);
    expect(host.calls).toContain('importXml:/x/plan.xml');
  });

  it('refuses illegal transitions', () => {
    const c = new AutoEditController(
      new FakeHost(selection({ cam1: 'a', cam2: 'b', wide: 'c' })),
      fakeEngineHost(engineJson),
    );
    c.backToSetup(); // no session: ignored
    expect(c.getState().phase).toBe('idle');
  });
});
