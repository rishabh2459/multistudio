import fs from 'node:fs';
import path from 'node:path';

import { AutoEditController, PluginError, placements, type EditPlan } from '@multicam/plugin-core';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';

import { END_INCLUSIVE, ResolveWiAdapter, parseFps } from '../src/adapter';
import { BridgeAdapter, BridgeEngineHost, makeHandler, type Invoke } from '../src/bridge';
import {
  engineAvailable,
  startRealEngine,
  type RealEngine,
} from '../../../../packages/plugin-core/test/real-engine';
import { FakeProject, fakeResolve, podcast } from './fake-resolve';

const plan: EditPlan = JSON.parse(
  fs.readFileSync(
    path.join(__dirname, '../../../../packages/plugin-core/test/fixtures/plan.json'),
    'utf8',
  ),
);
const demo = {
  cam1: '/media/demo/cam1.mp4',
  cam2: '/media/demo/cam2.mp4',
  wide: '/media/demo/wide.mp4',
};

describe('ResolveWiAdapter', () => {
  it('parses Resolve frame rates', () => {
    expect(parseFps('29.97')).toEqual({ num: 30000, den: 1001 });
    expect(parseFps('23.976 DF')).toEqual({ num: 24000, den: 1001 });
    expect(parseFps(25)).toEqual({ num: 25, den: 1 });
  });

  it('reads cameras, mics and positions from the current timeline', async () => {
    const sel = await new ResolveWiAdapter(
      fakeResolve(podcast(demo, { mic: '/media/demo/zoom.wav' })),
    ).readSelection();
    expect(sel.sequence).toEqual({
      fps: { num: 30000, den: 1001 },
      width: 1280,
      height: 720,
      name: 'Ep 42',
    });
    expect(
      sel.clips.map((c) => [
        c.path.split('/').pop(),
        c.kind,
        c.track,
        c.record_start_frame,
        c.in_frame,
      ]),
    ).toEqual([
      ['cam1.mp4', 'video', 1, 0, 0],
      ['cam2.mp4', 'video', 2, 0, 30],
      ['wide.mp4', 'video', 3, 15, 0],
      ['zoom.wav', 'audio', 4, 0, 0],
    ]);
    expect(sel.already_synced).toBe(true);
    expect(
      (await new ResolveWiAdapter(fakeResolve(podcast(demo, { synced: false }))).readSelection())
        .already_synced,
    ).toBe(false);
    await expect(new ResolveWiAdapter(fakeResolve(null)).readSelection()).rejects.toThrow(
      /Open a Resolve project/,
    );
  });

  for (const method of ['cuts', 'stacked_enable'] as const) {
    it(`native ${method}: one AppendToTimeline call with absolute record frames`, async () => {
      const project = podcast(demo);
      const r = await new ResolveWiAdapter(fakeResolve(project)).applyPlan(plan, { method });
      expect(r.via).toBe('native');
      expect(project.appends).toHaveLength(1);
      const ops = placements(plan, method);
      const infos = project.appends[0]!;
      expect(infos).toHaveLength(ops.length);
      const tl = project.current!;
      expect(tl.name).toBe(plan.sequence.name);
      expect(infos[1]!.recordFrame).toBe(tl.startFrame + ops[1]!.start);
      // Source frames at the clip's own rate (the wide camera is 25 fps on 29.97).
      const media = plan.media.find((m) => m.clip_id === ops[1]!.clipId)!;
      const ratio = media.fps.num / media.fps.den / (plan.sequence.fps.num / plan.sequence.fps.den);
      const srcFrames = Math.round((ops[1]!.end - ops[1]!.start) * ratio);
      if (END_INCLUSIVE) expect(infos[1]!.endFrame - infos[1]!.startFrame + 1).toBe(srcFrames);
      const video = tl.tracks.video.flat();
      const live = video.filter((i) => i.enabled).length;
      expect(live).toBe(method === 'cuts' ? video.length : plan.video_events.length);
    });
  }

  it('XML import + markers on the new timeline', async () => {
    const project = podcast(demo);
    const a = new ResolveWiAdapter(fakeResolve(project));
    const r = await a.importXml('/x/plan.fcpxml', plan);
    expect(project.importedXml).toEqual(['/x/plan.fcpxml']);
    expect(
      await a.addMarkers(r.sequenceId, [
        { frame: 60, duration: 1, color: 'yellow', kind: 'low_confidence', note: 'Check this cut' },
      ] as EditPlan['markers']),
    ).toBe(1);
  });
});

describe('Resolve frame math', () => {
  it('sound-only mics: source frames from the sample position at the clip rate', async () => {
    const micId = '00000000-0000-0000-0000-00000000a1c0';
    const p: EditPlan = structuredClone(plan);
    p.media.push({
      ...p.media[0]!,
      clip_id: micId,
      path: '/media/demo/zoom.wav',
      name: 'zoom.wav',
      label: 'zoom',
      fps: { num: 100, den: 1 },
      width: 0,
      height: 0,
      angle: null,
      video_track: null,
      audio_track: p.audio_tracks.length + 1,
      sample_rate: 48000,
    });
    p.audio_tracks.push({
      index: p.audio_tracks.length + 1,
      clip_id: micId,
      gain_db: 0,
      pieces: [
        {
          start: 0,
          end: 300,
          clip_id: micId,
          source_in_frame: 1000,
          source_in_sample: 480000,
          source_in_ticks: 0,
        },
      ],
    });
    const project = podcast(demo);
    await new ResolveWiAdapter(fakeResolve(project)).applyPlan(p, { method: 'cuts' });
    const mic = project.appends[0]!.find((i) =>
      (i.mediaPoolItem as unknown as { path: string }).path.endsWith('.wav'),
    )!;
    expect([mic.startFrame, mic.endFrame - mic.startFrame + 1, mic.mediaType]).toEqual([
      300, 300, 2,
    ]);
  });

  it('does not disable by position when Resolve skipped a clip', async () => {
    const project = podcast(demo);
    const real = project.GetMediaPool.bind(project);
    project.GetMediaPool = async () => {
      const pool = await real();
      const append = pool.AppendToTimeline.bind(pool);
      return { ...pool, AppendToTimeline: async (infos) => ((await append(infos)) ?? []).slice(1) };
    };
    const r = await new ResolveWiAdapter(fakeResolve(project)).applyPlan(plan, {
      method: 'stacked_enable',
    });
    expect(r.warnings.some((w) => w.includes('Not disabling'))).toBe(true);
    expect(project.current!.tracks.video.flat().every((i) => i.enabled)).toBe(true);
  });
});

describe('IPC bridge', () => {
  it('forwards whitelisted calls and keeps error codes', async () => {
    const project = new FakeProject();
    const handler = makeHandler(new ResolveWiAdapter(fakeResolve(project)), {
      readEngineFile: async () => '{}',
      openUrl: async () => undefined,
    });
    const invoke: Invoke = (t, m, a) => handler(t, m, structuredClone(a));
    const bridge = new BridgeAdapter(invoke);
    expect((await bridge.capabilities()).xmlImport).toBe('fcpxml');
    const err = await bridge.readSelection().catch((e: unknown) => e);
    expect(err).toBeInstanceOf(PluginError);
    expect((err as PluginError).code).toBe('setup_required');
    expect(await handler('host', 'constructor', [])).toMatchObject({
      ok: false,
      error: { code: 'invalid_request' },
    });
    expect(await new BridgeEngineHost(invoke).readEngineFile()).toBe('{}');
  });
});

const hasEngine = engineAvailable();

describe.skipIf(!hasEngine)('Resolve panel flow against the real engine', () => {
  let engine: RealEngine;
  beforeAll(async () => {
    engine = await startRealEngine();
  });
  afterAll(async () => {
    await engine?.stop();
  });

  it('connect -> run -> apply (native, through the bridge) -> XML fallback', async () => {
    const project = podcast(engine.media, { synced: false, name: 'Resolve Ep' });
    const handler = makeHandler(new ResolveWiAdapter(fakeResolve(project)), {
      readEngineFile: async () => engine.engineJson(),
      openUrl: async () => undefined,
    });
    // structuredClone = what Electron IPC does to arguments; Resolve objects stay in main.
    const invoke: Invoke = async (t, m, a) =>
      structuredClone(await handler(t, m, structuredClone(a)));
    const c = new AutoEditController(new BridgeAdapter(invoke), new BridgeEngineHost(invoke));
    await c.connect();
    expect(c.getState().error).toBeNull();
    expect(c.getState().session!.already_synced).toBe(false);
    await c.run({ vad: 'energy' });
    expect(c.getState().phase).toBe('review');
    await c.apply();
    expect(c.getState().error).toBeNull();
    expect(c.getState().applied!.warnings).toEqual([]);
    expect(c.getState().applied!.via).toBe('native');
    expect(project.current!.name).toBe(c.getState().plan!.sequence.name);
    await c.recut('punchy');
    await c.apply({ viaXml: true });
    expect(c.getState().applied!.via).toBe('xml');
    expect(project.importedXml.at(-1)).toMatch(/\.fcpxml$/);
  });
});
