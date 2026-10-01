/**
 * ResolveWiAdapter: DaVinci Resolve Studio glue for plugin-core (PLUGIN_PLAN 8.3).
 * Runs in the plugin's Electron main process, where the Resolve object lives; the
 * panel talks to it over IPC (bridge.ts). Same rules as the Resolve script
 * (apps/plugins/resolve-script/multicam_resolve/adapter.py).
 */
import {
  PluginError,
  placements,
  type ApplyOptions,
  type ApplyResult,
  type EditPlan,
  type HostAdapter,
  type HostCaps,
  type PlanMarker,
  type SessionClipIn,
  type SessionCreate,
} from '@multicam/plugin-core';

import type { ClipInfo, MediaPoolItem, Project, Resolve, Timeline } from './resolve-api';

/** AppendToTimeline's endFrame is the last frame (spike item, same as the script). */
export const END_INCLUSIVE = true;
const COLORS: Record<string, string> = {
  red: 'Red',
  yellow: 'Yellow',
  green: 'Green',
  blue: 'Blue',
};
const NTSC: [number, number][] = [
  [23.976, 24],
  [29.97, 30],
  [47.952, 48],
  [59.94, 60],
  [119.88, 120],
];

export function parseFps(value: string | number): { num: number; den: number } {
  const rate = Number(String(value).trim().split(/\s+/)[0]);
  for (const [ntsc, base] of NTSC)
    if (Math.abs(rate - ntsc) < 0.005) return { num: base * 1000, den: 1001 };
  if (Number.isInteger(rate)) return { num: rate, den: 1 };
  return { num: Math.round(rate * 1000), den: 1000 };
}

export function looksSynced(clips: SessionClipIn[]): boolean {
  if (clips.length < 2) return true;
  const offsets = new Set(clips.map((c) => (c.record_start_frame ?? 0) - (c.in_frame ?? 0)));
  return !(offsets.size === 1 && offsets.has(0));
}

export class ResolveWiAdapter implements HostAdapter {
  readonly host = 'resolve' as const;
  /** Timelines this adapter created, by id (markers are added to them later). */
  private readonly timelines = new Map<string, Timeline>();

  constructor(
    private readonly resolve: Resolve,
    private readonly os: 'mac' | 'windows' | 'linux' = 'mac',
  ) {}

  async capabilities(): Promise<HostCaps> {
    return {
      multicam: false,
      enableDisable: true,
      keyframes: false,
      markers: true,
      captions: false,
      xmlImport: 'fcpxml',
      maxNativeEvents: 1500,
    };
  }

  private async project(): Promise<Project> {
    const project = await (await this.resolve.GetProjectManager()).GetCurrentProject();
    if (!project) throw new PluginError('setup_required', 'Open a Resolve project first.');
    return project;
  }

  async readSelection(): Promise<SessionCreate> {
    const project = await this.project();
    const tl = await project.GetCurrentTimeline();
    if (!tl) {
      throw new PluginError(
        'setup_required',
        'No timeline is open.',
        'Open the timeline with your camera clips, then press Connect.',
      );
    }
    const fps = parseFps(
      (await tl.GetSetting('timelineFrameRate')) || (await project.GetSetting('timelineFrameRate')),
    );
    const width = Number(await project.GetSetting('timelineResolutionWidth')) || 1920;
    const height = Number(await project.GetSetting('timelineResolutionHeight')) || 1080;
    const start = Number(await tl.GetStartFrame());
    const clips = new Map<string, SessionClipIn>();
    for (const kind of ['video', 'audio'] as const) {
      const count = Number(await tl.GetTrackCount(kind));
      for (let track = 1; track <= count; track++) {
        for (const item of (await tl.GetItemListInTrack(kind, track)) ?? []) {
          const mpi = await item.GetMediaPoolItem();
          if (!mpi) continue;
          const path = String(await mpi.GetClipProperty('File Path'));
          if (!path || clips.has(path)) continue;
          if (
            kind === 'audio' &&
            !String(await mpi.GetClipProperty('Type'))
              .toLowerCase()
              .includes('audio')
          )
            continue;
          const left = Number(await item.GetLeftOffset());
          clips.set(path, {
            path,
            kind,
            host_ref: String(await mpi.GetUniqueId()),
            track,
            record_start_frame: Number(await item.GetStart()) - start,
            in_frame: left,
            out_frame: left + Number(await item.GetDuration()),
            label: null,
          });
        }
      }
    }
    const list = [...clips.values()];
    const name = String(await tl.GetName());
    if (!list.some((c) => c.kind === 'video')) {
      throw new PluginError(
        'setup_required',
        `"${name}" has no video clips.`,
        'Put each camera on its own video track.',
      );
    }
    return {
      host: { app: 'resolve', version: String(await this.resolve.GetVersionString()), os: this.os },
      host_sequence_id: String(await tl.GetUniqueId()),
      sequence: { fps, width, height, name },
      already_synced: looksSynced(list),
      clips: list,
    };
  }

  private async mediaItems(project: Project, plan: EditPlan): Promise<Map<string, MediaPoolItem>> {
    const pool = await project.GetMediaPool();
    const byPath = new Map<string, MediaPoolItem>();
    const walk = async (folder: Awaited<ReturnType<typeof pool.GetRootFolder>>): Promise<void> => {
      for (const clip of (await folder.GetClipList()) ?? []) {
        const path = String(await clip.GetClipProperty('File Path'));
        if (path && !byPath.has(path)) byPath.set(path, clip);
      }
      for (const sub of (await folder.GetSubFolderList()) ?? []) await walk(sub);
    };
    await walk(await pool.GetRootFolder());
    const missing = plan.media.filter((m) => !byPath.has(m.path)).map((m) => m.path);
    if (missing.length) {
      for (const clip of (await pool.ImportMedia(missing)) ?? [])
        byPath.set(String(await clip.GetClipProperty('File Path')), clip);
    }
    const out = new Map<string, MediaPoolItem>();
    for (const m of plan.media) {
      const item = byPath.get(m.path);
      if (!item)
        throw new PluginError('media_offline', `cannot import ${m.name}`, 'Relink the media.');
      out.set(m.clip_id, item);
    }
    return out;
  }

  async applyPlan(plan: EditPlan, opts: ApplyOptions): Promise<ApplyResult> {
    const project = await this.project();
    const pool = await project.GetMediaPool();
    const items = await this.mediaItems(project, plan);
    const tl = await pool.CreateEmptyTimeline(plan.sequence.name);
    if (!tl)
      throw new PluginError(
        'host_error',
        'Resolve could not create the timeline (is the name taken?)',
      );
    await project.SetCurrentTimeline(tl);
    const ops = placements(plan, opts.method);
    for (const kind of ['video', 'audio'] as const) {
      const need = Math.max(0, ...ops.filter((o) => o.kind === kind).map((o) => o.track));
      while (Number(await tl.GetTrackCount(kind)) < need) {
        if (!(await (kind === 'video' ? tl.AddTrack('video') : tl.AddTrack('audio', 'stereo'))))
          break;
      }
    }
    const seq = plan.sequence.fps.num / plan.sequence.fps.den;
    const rates = new Map(plan.media.map((m) => [m.clip_id, m.fps.num / m.fps.den]));
    const start = Number(await tl.GetStartFrame());
    const infos: ClipInfo[] = ops.map((op) => {
      const srcFrames = Math.max(
        1,
        Math.round(((op.end - op.start) * rates.get(op.clipId)!) / seq),
      );
      return {
        mediaPoolItem: items.get(op.clipId)!,
        startFrame: op.sourceInFrame,
        endFrame: op.sourceInFrame + srcFrames - (END_INCLUSIVE ? 1 : 0),
        trackIndex: op.track,
        recordFrame: start + op.start,
        mediaType: op.kind === 'video' ? 1 : 2,
      };
    });
    opts.onProgress?.(0.3, `placing ${infos.length} clips`);
    const placed = (await pool.AppendToTimeline(infos)) ?? [];
    const warnings: string[] = [];
    if (placed.length !== infos.length)
      warnings.push(`Resolve placed ${placed.length} of ${infos.length} clips`);
    if (opts.method === 'stacked_enable') {
      for (let i = 0; i < Math.min(ops.length, placed.length); i++) {
        const op = ops[i]!;
        const item = placed[i]!;
        if (op.kind !== 'video' || op.enabled) continue;
        if (!item.SetClipEnabled) {
          warnings.push('This Resolve cannot disable clips from a plugin.');
          break;
        }
        await item.SetClipEnabled(false);
      }
    }
    const id = String(await tl.GetUniqueId());
    this.timelines.set(id, tl);
    return {
      sequenceId: id,
      sequenceName: String(await tl.GetName()),
      via: 'native',
      markers: 0,
      warnings,
    };
  }

  async importXml(path: string, plan: EditPlan): Promise<ApplyResult> {
    const project = await this.project();
    const pool = await project.GetMediaPool();
    const tl = await pool.ImportTimelineFromFile(path, {
      timelineName: plan.sequence.name,
      importSourceClips: true,
    });
    if (!tl) throw new PluginError('host_error', `Resolve could not import ${path}`);
    await project.SetCurrentTimeline(tl);
    const id = String(await tl.GetUniqueId());
    this.timelines.set(id, tl);
    return {
      sequenceId: id,
      sequenceName: String(await tl.GetName()),
      via: 'xml',
      markers: plan.markers.length,
      warnings: [],
    };
  }

  async addMarkers(sequenceId: string, markers: PlanMarker[]): Promise<number> {
    const tl = this.timelines.get(sequenceId);
    if (!tl) throw new PluginError('host_error', 'the new timeline was not found');
    let added = 0;
    for (const m of markers) {
      const note = m.note ?? '';
      if (
        await tl.AddMarker(
          m.frame,
          COLORS[m.color ?? 'yellow'] ?? 'Yellow',
          note.slice(0, 60) || 'Check this cut',
          note,
          m.duration ?? 1,
          '',
        )
      )
        added++;
    }
    return added;
  }
}
