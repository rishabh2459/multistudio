import fs from 'node:fs';
import path from 'node:path';

import { AutoEditController, decideApply, type EditPlan } from '@multicam/plugin-core';
import { describe, expect, it } from 'vitest';

import { PremiereAdapter, fpsFromTimebase, looksSynced } from '../src/adapter';
import { PremiereEngineHost, fileUrl } from '../src/engine-host';
import { FakeProject, FakeSequence, fakePpro, uxpHost, type RecordedAction } from './mock-ppro';

const plan: EditPlan = JSON.parse(
  fs.readFileSync(
    path.join(__dirname, '../../../../packages/plugin-core/test/fixtures/plan.json'),
    'utf8',
  ),
);

function podcast(opts: { synced: boolean } = { synced: true }) {
  const project = new FakeProject();
  const seq = new FakeSequence('Ep 42');
  project.sequences.push(seq);
  project.active = seq;
  const cam1 = project.addClip('cam1.mp4', '/media/demo/cam1.mp4');
  const cam2 = project.addClip('cam2.mp4', '/media/demo/cam2.mp4');
  const wide = project.addClip('wide.mp4', '/media/demo/wide.mp4');
  const mic = project.addClip('zoom.wav', '/media/demo/zoom.wav');
  const len = 1200;
  project.place(seq, 'video', 0, cam1, 0, 0, len);
  project.place(seq, 'video', 1, cam2, 0, opts.synced ? 30 : 0, len);
  project.place(seq, 'video', 2, wide, opts.synced ? 15 : 0, 0, len);
  project.place(seq, 'audio', 0, cam1, 0, 0, len); // camera audio: not a separate mic
  project.place(seq, 'audio', 3, mic, 0, 0, len);
  return { project, seq };
}

describe('PremiereAdapter', () => {
  it('turns the sequence timebase into an exact frame rate', () => {
    expect(fpsFromTimebase('8475667200')).toEqual({ num: 30000, den: 1001 });
    expect(fpsFromTimebase('10160640000')).toEqual({ num: 25, den: 1 });
    expect(fpsFromTimebase('10594584000')).toEqual({ num: 24000, den: 1001 });
  });

  it('reads cameras, mics and their sync from the active sequence', async () => {
    const { project } = podcast();
    const sel = await new PremiereAdapter(fakePpro(project), uxpHost).readSelection();
    expect(sel.host).toEqual({ app: 'premiere', version: '26.1.0', os: 'mac' });
    expect(sel.host_sequence_id).toBe('guid:Ep 42');
    expect(sel.sequence).toEqual({
      fps: { num: 30000, den: 1001 },
      width: 1920,
      height: 1080,
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
  });

  it('clips just dropped at frame 0 are not treated as synced', async () => {
    const { project } = podcast({ synced: false });
    const sel = await new PremiereAdapter(fakePpro(project), uxpHost).readSelection();
    expect(sel.already_synced).toBe(false);
    expect(looksSynced([{ path: 'a', record_start_frame: 0, in_frame: 0 }])).toBe(true);
  });

  it('explains what to do without a sequence or without video', async () => {
    const project = new FakeProject();
    const adapter = new PremiereAdapter(fakePpro(project), uxpHost);
    await expect(adapter.readSelection()).rejects.toThrow(/No sequence is open/);
    project.active = new FakeSequence('Empty');
    await expect(adapter.readSelection()).rejects.toThrow(/has no video clips/);
  });

  it('imports the XML as a new sequence and opens it (one undo step)', async () => {
    const { project } = podcast();
    project.onImport = () => new FakeSequence(plan.sequence.name);
    const adapter = new PremiereAdapter(fakePpro(project), uxpHost);
    const r = await adapter.importXml('/x/Demo.xml', plan);
    expect(project.imported).toEqual(['/x/Demo.xml']);
    expect(project.importedInto).toEqual(['Multicam Studio']); // our own bin, made once
    expect(project.transactions.map((t) => t.actions[0]!.kind)).toEqual(['createBin']);
    expect(project.opened).toEqual([plan.sequence.name]);
    await adapter.readSelection(); // connect makes the bin up front ...
    await adapter.importXml('/x/Demo.xml', plan); // ... so applies are a single step
    expect(project.transactions).toHaveLength(1);
    expect(r).toMatchObject({
      via: 'xml',
      sequenceName: plan.sequence.name,
      markers: plan.markers.length,
    });
  });

  it('multicam: one import brings the stacked edit + the multicam source, and says why', async () => {
    const { project } = podcast();
    project.onImport = () => [
      new FakeSequence(plan.sequence.name),
      new FakeSequence(`${plan.sequence.name} - Multicam Source`),
    ];
    const adapter = new PremiereAdapter(fakePpro(project), uxpHost);
    const r = await adapter.importXml('/x/Demo-multicam.xml', plan, 'multicam');
    expect(project.opened).toEqual([plan.sequence.name]);
    expect(r.sequenceName).toBe(plan.sequence.name);
    expect(r.warnings.join(' ')).toMatch(/no plugin API for multicam/);
    expect(r.warnings.join(' ')).toMatch(/Multicam Source.*Multi-Camera > Enable/);
  });

  it('adds markers inside lockedAccess + one transaction', async () => {
    const { project, seq } = podcast();
    const adapter = new PremiereAdapter(fakePpro(project), uxpHost);
    const markers = [
      {
        frame: 300,
        duration: 1,
        color: 'yellow',
        kind: 'low_confidence',
        note: 'Check this cut (0.41)',
      },
      {
        frame: 900,
        duration: 1,
        color: 'yellow',
        kind: 'low_confidence',
        note: 'Check this cut (0.52)',
      },
    ] as EditPlan['markers'];
    expect(await adapter.addMarkers(seq.guid.toString(), markers, plan)).toBe(2);
    expect(project.transactions).toHaveLength(1);
    const [m] = project.transactions[0]!.actions as RecordedAction[];
    expect(m!.kind).toBe('marker');
    expect(m!.args.slice(0, 3)).toEqual([
      'Check this cut (0.41)',
      'Comment',
      String(300n * 8475667200n),
    ]);
  });

  it('native "cuts": in/out + overwrite per event in ONE transaction', async () => {
    const { project } = podcast();
    const adapter = new PremiereAdapter(fakePpro(project), uxpHost, { nativeApply: true });
    const r = await adapter.applyPlan(plan, { method: 'cuts' });
    expect(r.via).toBe('native');
    expect(project.transactions).toHaveLength(1);
    const actions = project.transactions[0]!.actions;
    const overwrites = actions.filter((a) => a.kind === 'overwrite');
    const videoOps = overwrites.filter((a) => (a.args[2] as number) >= 0);
    expect(videoOps).toHaveLength(plan.video_events.length);
    expect(videoOps.every((a) => a.args[2] === 0 && a.args[3] === -1)).toBe(true);
    expect(videoOps[1]!.args[1]).toBe(String(BigInt(plan.video_events[1]!.start) * 8475667200n));
    // every overwrite is preceded by its in/out, and in/out are cleared at the end
    actions.forEach(
      (a, i) => a.kind === 'overwrite' && expect(actions[i - 1]!.kind).toBe('setInOut'),
    );
    expect(actions.filter((a) => a.kind === 'clearInOut').length).toBe(3);
    expect(project.opened.at(-1)).toBe(plan.sequence.name);
  });

  it('stacked enable/disable never takes two undo steps: it goes through XML', async () => {
    const { project } = podcast();
    const adapter = new PremiereAdapter(fakePpro(project), uxpHost, { nativeApply: true });
    const caps = await adapter.capabilities();
    expect(caps.stackedOneUndo).toBe(false);
    expect(decideApply(plan, caps, { method: 'stacked_enable' })).toMatchObject({ via: 'xml' });
    await expect(adapter.applyPlan(plan, { method: 'stacked_enable' })).rejects.toThrow(
      /more than one undo step/,
    );
    expect(project.transactions).toHaveLength(0);
  });

  it('stacked apply in the panel = one XML import, nothing else touches the undo stack', async () => {
    const { project } = podcast();
    project.onImport = () => new FakeSequence(plan.sequence.name);
    const c = controllerWith(project, { nativeApply: true });
    await c.connect();
    const before = project.transactions.length; // the bin, made at connect
    await c.apply({ method: 'stacked_enable' });
    expect(c.getState().error).toBeNull();
    expect(c.getState().applied).toMatchObject({ via: 'xml' });
    expect(project.imported).toHaveLength(1);
    expect(project.transactions).toHaveLength(before);
  });

  it('native apply needs the media in the project', async () => {
    const project = new FakeProject();
    project.active = new FakeSequence('x');
    const adapter = new PremiereAdapter(fakePpro(project), uxpHost, { nativeApply: true });
    await expect(adapter.applyPlan(plan, { method: 'cuts' })).rejects.toThrow(
      /not in this project/,
    );
  });

  it('defaults to XML import (one undo step) unless native apply is on', async () => {
    const { project } = podcast();
    expect(
      (await new PremiereAdapter(fakePpro(project), uxpHost).capabilities()).maxNativeEvents,
    ).toBe(0);
    expect(
      (await new PremiereAdapter(fakePpro(project), uxpHost, { nativeApply: true }).capabilities())
        .maxNativeEvents,
    ).toBe(1500);
  });
});

describe('social clips in Premiere', () => {
  const clip = (aspect: '9:16' | '4:5' | '1:1' | '16:9') => ({
    aspect,
    name: `Ep 42 - Social - ${aspect.replace(':', 'x')}`,
    width: 1080,
    height: 1920,
    duration_frames: 900,
    plan,
    xml_path: `/exports/social/${aspect.replace(':', 'x')}.xml`,
    render_path: `/exports/social/${aspect.replace(':', 'x')}.mp4`,
  });

  it('reads the In/Out marks of the open sequence (none = null)', async () => {
    const { project, seq } = podcast();
    const adapter = new PremiereAdapter(fakePpro(project), uxpHost);
    seq.endF = 5000;
    expect(await adapter.readInOut()).toBeNull(); // no marks
    seq.inF = 900;
    seq.outF = 2700;
    expect(await adapter.readInOut()).toEqual({
      inFrame: 900,
      outFrame: 2700,
      sequenceName: 'Ep 42',
    });
  });

  it('imports every clip in ONE import into Multicam Studio/Social and queues renders', async () => {
    const { project } = podcast();
    const clips = [clip('9:16'), clip('4:5')];
    project.onImport = () => clips.map((c) => new FakeSequence(c.name));
    const adapter = new PremiereAdapter(fakePpro(project), uxpHost);
    const r = await adapter.importSocial(clips, {
      queueRenders: true,
      presetPath: '/presets/h264.epr',
      startQueue: true,
    });
    expect(project.imported).toEqual(clips.map((c) => c.xml_path));
    expect(project.importedInto).toEqual(['Social']);
    expect(project.bins.map((b) => b.name)).toEqual(['Multicam Studio']);
    expect(project.bins[0]!.children.map((b) => b.name)).toEqual(['Social']);
    expect(r.sequences.map((x) => x.aspect)).toEqual(['9:16', '4:5']);
    expect(r.bin).toBe('Multicam Studio/Social');
    expect(r.queued).toBe(2);
    expect(project.exports).toEqual(
      clips.map((c) => ({ sequence: c.name, output: c.render_path, preset: '/presets/h264.epr' })),
    );
    expect(project.batchStarted).toBe(true);
    expect(project.opened).toEqual([clips[0]!.name]);
  });

  it('says so when Media Encoder is missing or a clip did not come in', async () => {
    const { project } = podcast();
    const clips = [clip('1:1'), clip('16:9')];
    project.onImport = () => [new FakeSequence(clips[0]!.name)];
    project.amePresent = false;
    const r = await new PremiereAdapter(fakePpro(project), uxpHost).importSocial(clips, {
      queueRenders: true,
    });
    expect(r.queued).toBe(0);
    expect(r.warnings.join(' ')).toMatch(/did not appear/);
    expect(r.warnings.join(' ')).toMatch(/Media Encoder is not installed/);
  });

  it('panel: social clips from the In/Out marks, through the engine', async () => {
    const { project, seq } = podcast();
    seq.endF = 5000;
    seq.inF = 300;
    seq.outF = 1200;
    const clips = [clip('9:16')];
    project.onImport = () => clips.map((c) => new FakeSequence(c.name));
    const { fetch, engineHost, sent } = mockEngine({
      '/social': { clips, export_dir: '/exports/social', warnings: [] },
    });
    const c = new AutoEditController(new PremiereAdapter(fakePpro(project), uxpHost), engineHost, {
      client: { fetch },
    });
    await c.connect();
    await c.createSocial(
      { aspects: ['9:16'], watermark: { path: '/brand/logo.png', corner: 'top_right' } },
      { queueRenders: true },
    );
    expect(c.getState().error).toBeNull();
    const req = sent.find((x) => x.path.endsWith('/social'))!.body as Record<string, unknown>;
    expect(req).toMatchObject({ in_frame: 300, out_frame: 1200, aspects: ['9:16'] });
    expect(c.getState().social?.imported.sequences).toHaveLength(1);
    expect(c.getState().social?.imported.queued).toBe(1);
    expect(c.getState().phase).toBe('review'); // stays where it was
  });

  it('panel: asks for In/Out marks when there are none', async () => {
    const { project } = podcast();
    const c = controllerWith(project);
    await c.connect();
    await c.createSocial({ aspects: ['9:16'] });
    expect(c.getState().error?.hint).toMatch(/Mark In and Out/);
  });
});

describe('jump cuts in Premiere', () => {
  const removals = (approved: boolean[]) => ({
    cutlist_version: 3,
    duration_frames: 1200,
    removed_frames: approved.filter(Boolean).length * 20,
    removed_seconds: approved.filter(Boolean).length * 0.667,
    removals: approved.map((a, i) => ({
      index: i,
      start: 100 + i * 200,
      end: 120 + i * 200,
      kind: 'silence',
      approved: a,
      seconds: 0.667,
    })),
  });
  const rippled = {
    ...plan,
    sequence: { ...plan.sequence, name: `${plan.sequence.name} - Jump Cuts` },
  };

  it('find -> review -> apply: one XML import of the rippled edit', async () => {
    const { project } = podcast();
    project.onImport = () => new FakeSequence(rippled.sequence.name);
    let current = removals([true, true, true]);
    const { fetch, engineHost, sent } = mockEngine({
      '/jumpcuts': { job_id: 'j1', kind: 'jumpcut', events_url: '/x' },
    });
    const wrapped = async (url: string, init: RequestInit = {}) => {
      const u = new URL(url);
      if (u.pathname.endsWith('/removals')) {
        if (init.method === 'PATCH') {
          const body = JSON.parse(String(init.body)) as { reject?: number[] };
          current = removals(
            current.removals.map((r) => r.approved && !body.reject?.includes(r.index)),
          );
        }
        sent.push({ path: u.pathname, body: init.body ? JSON.parse(String(init.body)) : null });
        return new Response(JSON.stringify(current), { status: 200 });
      }
      if (u.pathname.endsWith('/editplan') && u.searchParams.get('ripple') === 'true') {
        sent.push({ path: u.pathname + u.search, body: null });
        return new Response(JSON.stringify(rippled), { status: 200 });
      }
      return fetch(url, init);
    };
    const c = new AutoEditController(new PremiereAdapter(fakePpro(project), uxpHost), engineHost, {
      client: { fetch: wrapped },
    });
    await c.connect();
    await c.findJumpCuts({ mode: 'db', threshold_db: -38 });
    expect(c.getState().error).toBeNull();
    expect(c.getState().phase).toBe('review');
    expect(c.getState().removals?.removals).toHaveLength(3);
    const req = sent.find((x) => x.path.endsWith('/jumpcuts'))!.body;
    expect(req).toEqual({ mode: 'db', threshold_db: -38 });

    await c.setRemovals({ reject: [1] });
    expect(c.getState().removals?.removals.map((r) => r.approved)).toEqual([true, false, true]);

    const before = project.transactions.length;
    await c.applyJumpCuts();
    expect(c.getState().error).toBeNull();
    expect(c.getState().phase).toBe('applied');
    expect(c.getState().applied?.sequenceName).toBe(rippled.sequence.name);
    const exp = sent.find((x) => x.path.includes('/export'))!.path;
    expect(exp).toContain('format=xmeml');
    expect(exp).toContain('ripple=true');
    expect(project.imported).toHaveLength(1);
    expect(project.transactions).toHaveLength(before); // one import, nothing else
  });

  it('refuses to apply without approved pauses', async () => {
    const { project } = podcast();
    const c = controllerWith(project);
    await c.connect();
    await c.applyJumpCuts();
    expect(c.getState().error?.message).toMatch(/no pauses approved/);
  });
});

describe('PremiereEngineHost', () => {
  it('reads engine.json from the app-data folder', async () => {
    const seen: string[] = [];
    const host = new PremiereEngineHost({
      ...uxpHost,
      readFile: async (p) => (seen.push(p), '{}'),
    });
    await host.readEngineFile();
    expect(seen).toEqual(['/Users/editor/Library/Application Support/Multicam Studio/engine.json']);
    expect(fileUrl('C:\\Users\\e\\AppData\\Roaming\\Multicam Studio\\engine.json')).toBe(
      'file:/C:/Users/e/AppData/Roaming/Multicam Studio/engine.json',
    );
    expect(fileUrl('/Users/e/x.json')).toBe('file:/Users/e/x.json');
  });
});

/** A fake engine answering the plugin API (handshake, session, plan, export). */
function mockEngine(extra: Record<string, unknown> = {}) {
  const session = {
    id: 's1',
    project_id: 'p',
    reused: true,
    host: { app: 'premiere', version: '', os: 'mac' },
    host_sequence_id: 'guid:Ep 42',
    already_synced: true,
    method: 'stacked_enable',
    state: 'ready',
    name: 'Ep 42',
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
  const sent: { path: string; body: unknown }[] = [];
  const fetch = async (url: string, init: RequestInit = {}) => {
    const u = new URL(url);
    sent.push({
      path: u.pathname + u.search,
      body: init.body ? JSON.parse(String(init.body)) : null,
    });
    if (u.pathname.endsWith('/events')) {
      const summary = {
        cutlist_version: 3,
        source: 'jumpcut',
        cuts: 7,
        duration_frames: 1,
        low_confidence_cuts: 0,
      };
      return new Response(`event: plan_ready\ndata: ${JSON.stringify(summary)}\n\n`, {
        status: 200,
        headers: { 'content-type': 'text/event-stream' },
      });
    }
    const custom = Object.entries(extra).find(([k]) => u.pathname.endsWith(k));
    const body = custom
      ? custom[1]
      : u.pathname.endsWith('/handshake')
        ? {
            api_version: '1.0.0',
            engine_version: 'x',
            capabilities: [],
            models: {},
            licence: {},
            data_dir: '',
            pid: 1,
          }
        : u.pathname.endsWith('/sessions')
          ? session
          : u.pathname.endsWith('/editplan')
            ? plan
            : u.pathname.endsWith('/export')
              ? { format: 'xmeml', path: '/x/Demo.xml', cutlist_version: 2, warnings: [] }
              : {};
    return new Response(JSON.stringify(body), { status: 200 });
  };
  const engineHost = {
    readEngineFile: async () => '{"port":47811,"token":"t","pid":1,"api":"1.0.0"}',
    openUrl: async () => undefined,
  };
  return { fetch, engineHost, sent };
}

function controllerWith(project: FakeProject, opts: { nativeApply?: boolean } = {}) {
  const { fetch, engineHost } = mockEngine();
  return new AutoEditController(new PremiereAdapter(fakePpro(project), uxpHost, opts), engineHost, {
    client: { fetch },
  });
}

describe('panel flow in Premiere (mock engine)', () => {
  it('connect -> review -> apply imports XML and keeps markers from the XML', async () => {
    const { project } = podcast();
    project.onImport = () => new FakeSequence(plan.sequence.name);
    const session = {
      id: 's1',
      project_id: 'p',
      reused: true,
      host: { app: 'premiere', version: '', os: 'mac' },
      host_sequence_id: 'guid:Ep 42',
      already_synced: true,
      method: 'stacked_enable',
      state: 'ready',
      name: 'Ep 42',
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
    const sent: unknown[] = [];
    const fetch = async (url: string, init: RequestInit = {}) => {
      const u = new URL(url);
      if (init.body) sent.push(JSON.parse(String(init.body)));
      const body = u.pathname.endsWith('/handshake')
        ? {
            api_version: '1.0.0',
            engine_version: 'x',
            capabilities: [],
            models: {},
            licence: {},
            data_dir: '',
            pid: 1,
          }
        : u.pathname.endsWith('/sessions')
          ? session
          : u.pathname.endsWith('/editplan')
            ? plan
            : u.pathname.endsWith('/export')
              ? { format: 'xmeml', path: '/x/Demo.xml', cutlist_version: 2, warnings: [] }
              : {};
      return new Response(JSON.stringify(body), { status: 200 });
    };
    const engineHost = {
      readEngineFile: async () => '{"port":47811,"token":"t","pid":1,"api":"1.0.0"}',
      openUrl: async () => undefined,
    };
    const c = new AutoEditController(new PremiereAdapter(fakePpro(project), uxpHost), engineHost, {
      client: { fetch },
    });
    await c.connect();
    expect(c.getState().phase).toBe('review');
    expect((sent[0] as { already_synced: boolean }).already_synced).toBe(true);
    const before = project.transactions.length; // the Multicam Studio bin
    await c.apply();
    expect(c.getState().error).toBeNull();
    expect(c.getState().applied).toMatchObject({ via: 'xml', sequenceName: plan.sequence.name });
    expect(project.imported).toEqual(['/x/Demo.xml']);
    expect(project.transactions).toHaveLength(before); // markers came with the XML
  });
});
