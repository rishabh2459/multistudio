import fs from 'node:fs';
import path from 'node:path';

import { AutoEditController, type EditPlan } from '@multicam/plugin-core';
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
    expect(project.opened).toEqual([plan.sequence.name]);
    expect(r).toMatchObject({
      via: 'xml',
      sequenceName: plan.sequence.name,
      markers: plan.markers.length,
    });
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

  it('native "stacked": places every camera piece, then disables the ones not live', async () => {
    const { project } = podcast();
    const adapter = new PremiereAdapter(fakePpro(project), uxpHost, { nativeApply: true });
    const r = await adapter.applyPlan(plan, { method: 'stacked_enable' });
    expect(project.transactions).toHaveLength(2);
    const off = plan.video_tracks.flatMap((t) => t.pieces).filter((p) => !p.enabled).length;
    expect(project.transactions[1]!.actions.filter((a) => a.kind === 'setDisabled')).toHaveLength(
      off,
    );
    expect(r.warnings.join(' ')).toMatch(/two undo steps/);
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
    await c.apply();
    expect(c.getState().error).toBeNull();
    expect(c.getState().applied).toMatchObject({ via: 'xml', sequenceName: plan.sequence.name });
    expect(project.imported).toEqual(['/x/Demo.xml']);
    expect(project.transactions).toHaveLength(0); // markers came with the XML
  });
});
