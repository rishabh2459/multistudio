/**
 * HostAdapter: the only host-specific code (PLUGIN_PLAN 8.1). Everything else -
 * flow, UI, errors - lives in plugin-core and is tested without an NLE.
 */
import type { SocialClipOut } from './extras';
import type { EditPlan, HostApp, PlanMarker, PlanMethod, SessionCreate } from './types';

export interface HostCaps {
  /** Can build a native multicam clip and switch angles. */
  multicam: boolean;
  /** Can razor + enable/disable track items (stacked_enable natively). */
  enableDisable: boolean;
  /**
   * Can place AND disable a stacked edit natively in one undo step. `false` when the
   * host can only disable clips after they exist (a second transaction): stacked
   * edits then go through XML import, which carries the enabled flags (one step).
   */
  stackedOneUndo?: boolean;
  /** Can write position/scale keyframes (reframe). */
  keyframes: boolean;
  markers: boolean;
  captions: boolean;
  /** Can import an XML timeline (the Rule C fallback). */
  xmlImport: 'fcpxml' | 'xmeml' | null;
  /** Above this many video events, import XML instead of issuing API calls (7.2). */
  maxNativeEvents: number;
}

export interface ApplyOptions {
  method: PlanMethod;
  /** Force the XML import path. */
  viaXml?: boolean;
  /** Path of the exported XML when `viaXml` (the engine writes it). */
  xmlPath?: string;
  /** Called with 0..1 while applying. */
  onProgress?: (fraction: number, message: string) => void;
}

export interface ApplyResult {
  /** Host id of the new sequence / timeline. */
  sequenceId: string;
  sequenceName: string;
  via: 'native' | 'xml';
  markers: number;
  warnings: string[];
}

export interface HostAdapter {
  readonly host: HostApp;
  capabilities(): Promise<HostCaps>;
  /** What the user selected (a sequence or bin items), as a session request. */
  readSelection(): Promise<SessionCreate>;
  /** Build the edit in ONE undo step. */
  applyPlan(plan: EditPlan, opts: ApplyOptions): Promise<ApplyResult>;
  /**
   * Rule C fallback: import an XML file as a new sequence. `method` is what the
   * file was exported for (it can differ from `plan.method`, e.g. multicam).
   */
  importXml(path: string, plan: EditPlan, method?: PlanMethod): Promise<ApplyResult>;
  addMarkers(sequenceId: string, markers: PlanMarker[], plan: EditPlan): Promise<number>;
  /** The edit as it is now on the host timeline (feedback / re-apply). */
  readTimeline?(sequenceId: string, plan: EditPlan): Promise<EditPlan>;
  /**
   * In / out marks of the open sequence in its frames (null: none set). Social clips
   * use them as the range when the panel does not give one.
   */
  readInOut?(): Promise<{ inFrame: number; outFrame: number; sequenceName: string } | null>;
  /** Let the user pick a file (watermark / end page picture, export preset). */
  pickFile?(purpose: 'picture' | 'preset'): Promise<string | null>;
  /** Bring social clips in (one sequence each, in one bin) and optionally queue renders. */
  importSocial?(clips: SocialClipOut[], opts: SocialImportOptions): Promise<SocialImportResult>;
}

export interface SocialImportOptions {
  /** Queue every clip for rendering (Premiere: Adobe Media Encoder). */
  queueRenders?: boolean;
  /** Export preset file (.epr); empty = the host's default for the sequence. */
  presetPath?: string;
  /** Start the render queue right away (when the host can). */
  startQueue?: boolean;
}

export interface SocialImportResult {
  sequences: { name: string; aspect: string; sequenceId: string }[];
  bin: string;
  queued: number;
  warnings: string[];
}
