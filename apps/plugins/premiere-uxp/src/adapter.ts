/**
 * PremiereAdapter: Premiere Pro (UXP) glue for plugin-core (PLUGIN_PLAN 8.2).
 *
 * - readSelection: clips of the active sequence (video tracks = cameras, audio-only
 *   media on audio tracks = separate mics), with their sequence positions so the
 *   engine can skip audio sync when the sequence is already synced.
 * - apply: XML import (xmeml) into a new sequence = one undo step (PL4 default).
 *   Native apply through SequenceEditor is behind `nativeApply` (beta, PL5) until
 *   the PL4 spike confirms the DOM in Premiere.
 * - markers: low-confidence cuts as Comment markers.
 */
import {
  PluginError,
  frameToTicks,
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

import type {
  ClipProjectItem,
  ClipTrackItem,
  PremierePro,
  Project,
  ProjectItem,
  Track,
  UxpHost,
} from './ppro';

export const TICKS_PER_SECOND = 254_016_000_000n;

export interface PremiereOptions {
  /** Build the edit with SequenceEditor actions instead of XML import (beta). */
  nativeApply?: boolean;
}

function gcd(a: bigint, b: bigint): bigint {
  while (b) [a, b] = [b, a % b];
  return a;
}

/** Sequence timebase (ticks per frame) -> exact frame rate. */
export function fpsFromTimebase(ticksPerFrame: string): { num: number; den: number } {
  const tpf = BigInt(ticksPerFrame);
  if (tpf <= 0n) throw new PluginError('host_error', `bad sequence timebase ${ticksPerFrame}`);
  const g = gcd(TICKS_PER_SECOND, tpf);
  return { num: Number(TICKS_PER_SECOND / g), den: Number(tpf / g) };
}

function ticksToFrames(ticks: string, ticksPerFrame: bigint): number {
  const t = BigInt(ticks);
  return Number((t + ticksPerFrame / 2n) / ticksPerFrame);
}

export class PremiereAdapter implements HostAdapter {
  readonly host = 'premiere' as const;

  constructor(
    private readonly ppro: PremierePro,
    private readonly uxp: UxpHost,
    private readonly opts: PremiereOptions = {},
  ) {}

  async capabilities(): Promise<HostCaps> {
    return {
      multicam: false, // angle switching is not in the UXP DOM yet: XML (K1)
      enableDisable: true,
      keyframes: false, // reframe keyframes arrive in PL5
      markers: true,
      captions: false,
      xmlImport: 'xmeml',
      // 0 = always import XML (one undo step) unless native apply is switched on.
      maxNativeEvents: this.opts.nativeApply ? 1500 : 0,
    };
  }

  private async project(): Promise<Project> {
    const project = await this.ppro.Project.getActiveProject();
    if (!project) throw new PluginError('setup_required', 'Open a Premiere project first.');
    return project;
  }

  // ---------------------------------------------------------------- selection
  async readSelection(): Promise<SessionCreate> {
    const project = await this.project();
    const seq = await project.getActiveSequence();
    if (!seq) {
      throw new PluginError(
        'setup_required',
        'No sequence is open.',
        'Open the sequence with your camera clips (synced or not), then press Connect.',
      );
    }
    const timebase = await seq.getTimebase();
    const tpf = BigInt(timebase);
    const fps = fpsFromTimebase(timebase);
    const size = await seq.getFrameSize();
    const clipType = this.ppro.Constants.TrackItemType.CLIP;

    const clips = new Map<string, SessionClipIn>();
    const readTrack = async (
      kind: 'video' | 'audio',
      count: number,
      get: (i: number) => Promise<Track>,
    ) => {
      for (let i = 0; i < count; i++) {
        const track = await get(i);
        for (const item of track.getTrackItems(clipType, false)) {
          const projectItem = await item.getProjectItem();
          const clip = this.ppro.ClipProjectItem.cast(projectItem);
          if (await clip.isSequence()) continue; // nested sequences are not media
          const path = await clip.getMediaFilePath();
          if (!path) continue;
          // First item of each file decides its sync; camera audio is not a mic.
          if (clips.has(path)) continue;
          const [start, inPoint, end] = await Promise.all([
            item.getStartTime(),
            item.getInPoint(),
            item.getEndTime(),
          ]);
          const startF = ticksToFrames(start.ticks, tpf);
          const inF = ticksToFrames(inPoint.ticks, tpf);
          clips.set(path, {
            path,
            kind,
            host_ref: projectItem.getId?.() ?? path,
            track: i + 1,
            record_start_frame: startF,
            in_frame: inF,
            out_frame: inF + ticksToFrames(end.ticks, tpf) - startF,
            label: null,
          });
        }
      }
    };
    await readTrack('video', await seq.getVideoTrackCount(), (i) => seq.getVideoTrack(i));
    await readTrack('audio', await seq.getAudioTrackCount(), (i) => seq.getAudioTrack(i));

    const list = [...clips.values()];
    if (!list.some((c) => c.kind === 'video')) {
      throw new PluginError(
        'setup_required',
        `"${seq.name}" has no video clips.`,
        'Put each camera on its own video track (one clip per camera is enough).',
      );
    }
    return {
      host: { app: 'premiere', version: this.uxp.appVersion, os: this.uxp.platform() },
      host_sequence_id: seq.guid.toString(),
      sequence: {
        fps,
        width: Math.round(size.width),
        height: Math.round(size.height),
        name: seq.name,
      },
      already_synced: looksSynced(list),
      clips: list,
    };
  }

  // ---------------------------------------------------------------- apply
  async importXml(path: string, plan: EditPlan): Promise<ApplyResult> {
    const project = await this.project();
    const before = new Set((await project.getSequences()).map((s) => s.guid.toString()));
    const bin = await project.getInsertionBin();
    const ok = await project.importFiles([path], true, bin, false);
    if (!ok) throw new PluginError('host_error', `Premiere could not import ${path}`);
    const created = (await project.getSequences()).filter((s) => !before.has(s.guid.toString()));
    const seq = created.find((s) => s.name === plan.sequence.name) ?? created.at(-1);
    if (!seq) throw new PluginError('host_error', 'the imported XML created no sequence');
    await project.openSequence(seq);
    return {
      sequenceId: seq.guid.toString(),
      sequenceName: seq.name,
      via: 'xml',
      markers: plan.markers.length, // the XML carries them
      warnings: [],
    };
  }

  async applyPlan(plan: EditPlan, opts: ApplyOptions): Promise<ApplyResult> {
    const project = await this.project();
    const { TickTime } = this.ppro;
    const fps = plan.sequence.fps;
    const items = await this.projectItemsByPath(project, plan);
    const seq = await project.createSequence(plan.sequence.name);
    const editor = this.ppro.SequenceEditor.getEditor(seq);
    const ops = placements(plan, opts.method);
    const warnings: string[] = [
      'Native apply is in beta: check the sequence settings match the plan ' +
        `(${plan.sequence.width}×${plan.sequence.height}, ${(fps.num / fps.den).toFixed(3)} fps).`,
    ];
    let ok = false;
    opts.onProgress?.(0.1, `placing ${ops.length} clips`);
    project.lockedAccess(() => {
      ok = project.executeTransaction((compound) => {
        for (const op of ops) {
          const item = items.get(op.clipId)!;
          const clip = this.ppro.ClipProjectItem.cast(item);
          const inT = BigInt(Math.round(op.sourceInTicks));
          const outT = inT + BigInt(frameToTicks(op.end - op.start, fps));
          compound.addAction(
            clip.createSetInOutPointsAction(
              TickTime.createWithTicks(inT.toString()),
              TickTime.createWithTicks(outT.toString()),
            ),
          );
          const at = TickTime.createWithTicks(frameToTicks(op.start, fps));
          compound.addAction(
            op.kind === 'video'
              ? editor.createOverwriteItemAction(item, at, op.track - 1, -1)
              : editor.createOverwriteItemAction(item, at, -1, op.track - 1),
          );
        }
        for (const item of new Set(items.values())) {
          compound.addAction(this.ppro.ClipProjectItem.cast(item).createClearInOutPointsAction());
        }
      }, `Multicam Studio: ${plan.sequence.name}`);
    });
    if (!ok) throw new PluginError('host_error', 'Premiere refused the edit transaction');

    if (opts.method === 'stacked_enable') {
      opts.onProgress?.(0.7, 'disabling cameras that are not live');
      const off = new Set(
        ops.filter((o) => o.kind === 'video' && !o.enabled).map((o) => `${o.track}:${o.start}`),
      );
      const tpf = BigInt(frameToTicks(1, fps));
      const disable: ClipTrackItem[] = [];
      const count = await seq.getVideoTrackCount();
      for (let i = 0; i < count; i++) {
        const track = await seq.getVideoTrack(i);
        for (const item of track.getTrackItems(this.ppro.Constants.TrackItemType.CLIP, false)) {
          const start = ticksToFrames((await item.getStartTime()).ticks, tpf);
          if (off.has(`${i + 1}:${start}`)) disable.push(item);
        }
      }
      if (disable.some((d) => !d.createSetDisabledAction)) {
        warnings.push(
          'This Premiere cannot disable clips from a plugin: all cameras stay enabled.',
        );
      } else if (disable.length) {
        project.lockedAccess(() => {
          project.executeTransaction((compound) => {
            for (const d of disable) compound.addAction(d.createSetDisabledAction!(true));
          }, `Multicam Studio: ${plan.sequence.name} (cameras)`);
        });
        warnings.push('Native stacked apply uses two undo steps (place, then disable).');
      }
    }
    await project.openSequence(seq);
    opts.onProgress?.(1, 'done');
    return {
      sequenceId: seq.guid.toString(),
      sequenceName: seq.name,
      via: 'native',
      markers: 0,
      warnings,
    };
  }

  /** Project items of the plan's media: by host_ref (our id) or by file path. */
  private async projectItemsByPath(
    project: Project,
    plan: EditPlan,
  ): Promise<Map<string, ProjectItem>> {
    const byPath = new Map<string, ProjectItem>();
    const walk = async (folder: { getItems?: () => Promise<ProjectItem[]> }) => {
      for (const item of (await folder.getItems?.()) ?? []) {
        const sub = item as unknown as { getItems?: () => Promise<ProjectItem[]> };
        if (typeof sub.getItems === 'function') {
          await walk(sub);
          continue;
        }
        try {
          const path = await (
            this.ppro.ClipProjectItem.cast(item) as ClipProjectItem
          ).getMediaFilePath();
          if (path && !byPath.has(path)) byPath.set(path, item);
        } catch {
          // not a clip (e.g. a sequence or a bin)
        }
      }
    };
    await walk(await project.getRootItem());
    const out = new Map<string, ProjectItem>();
    const missing: string[] = [];
    for (const m of plan.media) {
      const item = byPath.get(m.path);
      if (item) out.set(m.clip_id, item);
      else missing.push(m.name);
    }
    if (missing.length) {
      throw new PluginError(
        'media_offline',
        `not in this project: ${missing.join(', ')}`,
        'Import the files, or apply by XML import.',
      );
    }
    return out;
  }

  // ---------------------------------------------------------------- markers
  async addMarkers(sequenceId: string, markers: PlanMarker[], plan: EditPlan): Promise<number> {
    if (!markers.length) return 0;
    const project = await this.project();
    const seq = (await project.getSequences()).find((s) => s.guid.toString() === sequenceId);
    if (!seq) throw new PluginError('host_error', 'the new sequence was not found');
    const list = await this.ppro.Markers.getMarkers(seq);
    const { TickTime } = this.ppro;
    const fps = plan.sequence.fps;
    const type = this.ppro.Constants.MarkerType?.COMMENT ?? 'Comment';
    project.lockedAccess(() => {
      project.executeTransaction((compound) => {
        for (const m of markers) {
          compound.addAction(
            list.createAddMarkerAction(
              m.note.slice(0, 60) || 'Check this cut',
              type,
              TickTime.createWithTicks(frameToTicks(m.frame, fps)),
              TickTime.createWithTicks(frameToTicks(m.duration ?? 1, fps)),
              m.note,
            ),
          );
        }
      }, 'Multicam Studio: markers');
    });
    return markers.length;
  }
}

/**
 * Whether the clips' positions already line them up. Clips merely dropped at the
 * start of a sequence (every clip at frame 0, no trim) are treated as NOT synced,
 * so the engine runs its audio sync; any offset means the editor synced them.
 */
export function looksSynced(clips: SessionClipIn[]): boolean {
  if (clips.length < 2) return true;
  const offsets = new Set(clips.map((c) => (c.record_start_frame ?? 0) - (c.in_frame ?? 0)));
  return !(offsets.size === 1 && offsets.has(0));
}
