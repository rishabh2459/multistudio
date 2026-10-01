/**
 * HostAdapter: the only host-specific code (PLUGIN_PLAN 8.1). Everything else -
 * flow, UI, errors - lives in plugin-core and is tested without an NLE.
 */
import type { EditPlan, HostApp, PlanMarker, PlanMethod, SessionCreate } from './types';

export interface HostCaps {
  /** Can build a native multicam clip and switch angles. */
  multicam: boolean;
  /** Can razor + enable/disable track items (stacked_enable natively). */
  enableDisable: boolean;
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
  /** Rule C fallback: import an XML file as a new sequence. */
  importXml(path: string, plan: EditPlan): Promise<ApplyResult>;
  addMarkers(sequenceId: string, markers: PlanMarker[], plan: EditPlan): Promise<number>;
  /** The edit as it is now on the host timeline (feedback / re-apply). */
  readTimeline?(sequenceId: string, plan: EditPlan): Promise<EditPlan>;
}
