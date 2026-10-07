/**
 * PremiereAdapter: Premiere Pro (UXP) glue for plugin-core (PLUGIN_PLAN 8.2).
 *
 * - readSelection: clips of the active sequence (video tracks = cameras, audio-only
 *   media on audio tracks = separate mics), with their sequence positions so the
 *   engine can skip audio sync when the sequence is already synced.
 * - apply: XML import (xmeml) into a new sequence = one undo step (PL4 default).
 *   Stacked enable/disable always comes in by XML (clips arrive already disabled:
 *   one undo step); natively it would take two transactions. Native `cuts` through
 *   SequenceEditor is behind `nativeApply` (beta, PL5) until the PL4 spike passes.
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
  type PlanMethod,
  type SessionClipIn,
  type SessionCreate,
  type SocialClipOut,
  type SocialImportOptions,
  type SocialImportResult,
} from '@multicam/plugin-core';

import type {
  ClipProjectItem,
  FolderItem,
  PremierePro,
  Project,
  ProjectItem,
  Track,
  UxpHost,
} from './ppro';

export const TICKS_PER_SECOND = 254_016_000_000n;
/** Everything the panel imports lands in this bin. */
export const BIN_ROOT = 'Multicam Studio';
export const SOCIAL_BIN = 'Social';
/** Name suffix of the multicam source sequence the engine writes (xmeml_multicam.py). */
export const MULTICAM_SOURCE_SUFFIX = ' - Multicam Source';

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
      // Disabling needs the clips to exist first (2nd transaction): stacked = XML.
      stackedOneUndo: false,
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
    // Made now (its own undo step) so a later apply stays ONE undo step.
    await this.ensureBin(project, BIN_ROOT);
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
  async importXml(path: string, plan: EditPlan, method?: PlanMethod): Promise<ApplyResult> {
    const project = await this.project();
    const before = new Set((await project.getSequences()).map((s) => s.guid.toString()));
    const bin = await this.ensureBin(project, BIN_ROOT);
    const ok = await project.importFiles([path], true, bin, false);
    if (!ok) throw new PluginError('host_error', `Premiere could not import ${path}`);
    const created = (await project.getSequences()).filter((s) => !before.has(s.guid.toString()));
    const seq = created.find((s) => s.name === plan.sequence.name) ?? created.at(0);
    if (!seq) throw new PluginError('host_error', 'the imported XML created no sequence');
    await project.openSequence(seq);
    const warnings: string[] = [];
    if (method === 'multicam') {
      const source = created.find((s) => s.name.endsWith(MULTICAM_SOURCE_SUFFIX));
      warnings.push(
        'Premiere has no plugin API for multicam sequences (Adobe), so the edit is on ' +
          'stacked tracks (same cuts, enable/disable).',
        source
          ? `"${source.name}" holds every camera in sync: nest it and use Multi-Camera > ` +
              'Enable to switch angles by hand.'
          : 'The multicam source sequence was not found after import.',
      );
    }
    return {
      sequenceId: seq.guid.toString(),
      sequenceName: seq.name,
      via: 'xml',
      markers: plan.markers.length, // the XML carries them
      warnings,
    };
  }

  /** A bin under `parent` (default: the project root), created once, found by name after. */
  private async ensureBin(
    project: Project,
    name: string,
    parent?: FolderItem,
  ): Promise<ProjectItem> {
    const folder = parent ?? (await project.getRootItem());
    const find = async () =>
      ((await folder.getItems()) ?? []).find(
        (i) => i.name === name && typeof (i as FolderItem).getItems === 'function',
      );
    const existing = await find();
    if (existing) return existing;
    if (typeof folder.createBinAction !== 'function') return project.getInsertionBin();
    project.lockedAccess(() => {
      project.executeTransaction((compound) => {
        compound.addAction(folder.createBinAction!(name, false));
      }, `Multicam Studio: bin ${name}`);
    });
    return (await find()) ?? project.getInsertionBin();
  }

  private folder(item: ProjectItem): FolderItem {
    return (this.ppro.FolderItem?.cast(item) ?? item) as FolderItem;
  }

  // ---------------------------------------------------------------- social clips
  async readInOut(): Promise<{ inFrame: number; outFrame: number; sequenceName: string } | null> {
    const project = await this.project();
    const seq = await project.getActiveSequence();
    if (!seq?.getInPoint || !seq.getOutPoint) return null;
    const tpf = BigInt(await seq.getTimebase());
    const [inT, outT] = await Promise.all([seq.getInPoint(), seq.getOutPoint()]);
    const inFrame = ticksToFrames(inT.ticks, tpf);
    const outFrame = ticksToFrames(outT.ticks, tpf);
    // No marks: Premiere reports the whole sequence (in 0, out = end) or nothing.
    const end = ticksToFrames((await seq.getEndTime()).ticks, tpf);
    if (outFrame <= inFrame || (inFrame === 0 && (outFrame === 0 || outFrame >= end))) {
      return null;
    }
    return { inFrame, outFrame, sequenceName: seq.name };
  }

  async pickFile(purpose: 'picture' | 'preset'): Promise<string | null> {
    if (!this.uxp.pickFile) return null;
    return this.uxp.pickFile(
      purpose === 'preset' ? ['epr'] : ['png', 'jpg', 'jpeg', 'gif', 'webp', 'mov', 'mp4'],
    );
  }

  async importSocial(
    clips: SocialClipOut[],
    opts: SocialImportOptions = {},
  ): Promise<SocialImportResult> {
    const project = await this.project();
    const paths = clips.map((c) => c.xml_path).filter((p): p is string => !!p);
    if (paths.length !== clips.length) {
      throw new PluginError('host_error', 'the engine wrote no XML for some clips');
    }
    const root = this.folder(await this.ensureBin(project, BIN_ROOT));
    const bin = await this.ensureBin(project, SOCIAL_BIN, root);
    const before = new Set((await project.getSequences()).map((s) => s.guid.toString()));
    // One import call for every clip: one step in the undo history.
    if (!(await project.importFiles(paths, true, bin, false))) {
      throw new PluginError('host_error', 'Premiere could not import the social clips');
    }
    const created = (await project.getSequences()).filter((s) => !before.has(s.guid.toString()));
    const warnings: string[] = [];
    const sequences: SocialImportResult['sequences'] = [];
    for (const clip of clips) {
      const seq = created.find((s) => s.name === clip.name);
      if (!seq) {
        warnings.push(`"${clip.name}" did not appear after the import`);
        continue;
      }
      sequences.push({ name: seq.name, aspect: clip.aspect, sequenceId: seq.guid.toString() });
    }
    let queued = 0;
    if (opts.queueRenders && sequences.length) {
      const encoder = this.ppro.EncoderManager?.getManager();
      const type = this.ppro.Constants.ExportType?.QUEUE_TO_AME;
      if (!encoder || type === undefined) {
        warnings.push(
          'This Premiere cannot queue renders from a plugin: export the clips by hand.',
        );
      } else if (!encoder.isAMEInstalled) {
        warnings.push('Adobe Media Encoder is not installed: renders were not queued.');
      } else {
        for (const s of sequences) {
          const seq = created.find((c) => c.guid.toString() === s.sequenceId)!;
          const clip = clips.find((c) => c.name === s.name)!;
          const ok = await encoder.exportSequence(
            seq,
            type,
            clip.render_path,
            opts.presetPath ?? '',
            true,
          );
          if (ok) queued += 1;
          else warnings.push(`could not queue "${s.name}"`);
        }
        if (queued && opts.startQueue && encoder.startBatchEncode) await encoder.startBatchEncode();
      }
    }
    if (sequences[0]) {
      const first = created.find((c) => c.guid.toString() === sequences[0]!.sequenceId);
      if (first) await project.openSequence(first);
    }
    return { sequences, bin: `${BIN_ROOT}/${SOCIAL_BIN}`, queued, warnings };
  }

  async applyPlan(plan: EditPlan, opts: ApplyOptions): Promise<ApplyResult> {
    if (opts.method !== 'cuts') {
      // Premiere can only disable a clip after it exists, i.e. in a second
      // transaction = a second undo step. XML import brings the clips in already
      // enabled/disabled in ONE step, so stacked (and multicam) always go that way.
      throw new PluginError(
        'not_available',
        `native "${opts.method}" would need more than one undo step in Premiere`,
        'the panel imports the edit as XML instead (one undo step)',
      );
    }
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
