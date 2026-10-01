/**
 * In-memory NLE for tests (and for trying the panel in a browser): a selection,
 * a list of sequences with tracks of clip items, undo history and markers.
 */
import type { ApplyOptions, ApplyResult, HostAdapter, HostCaps } from '../src/adapter';
import { PluginError } from '../src/errors';
import { placements, type PlaceOp } from '../src/plan';
import type { EditPlan, HostApp, PlanMarker, SessionCreate } from '../src/types';

export interface FakeSequence {
  id: string;
  name: string;
  items: PlaceOp[];
  markers: PlanMarker[];
  via: 'native' | 'xml';
  xmlPath?: string;
}

export class FakeHost implements HostAdapter {
  readonly host: HostApp;
  sequences: FakeSequence[] = [];
  /** Each apply is one undo step: undo() removes the last sequence entirely. */
  undoStack: string[] = [];
  calls: string[] = [];
  failNative: string | null = null;

  constructor(
    public selection: SessionCreate,
    public caps: Partial<HostCaps> = {},
    host: HostApp = 'premiere',
  ) {
    this.host = host;
  }

  async capabilities(): Promise<HostCaps> {
    return {
      multicam: false,
      enableDisable: true,
      keyframes: false,
      markers: true,
      captions: false,
      xmlImport: 'xmeml',
      maxNativeEvents: 1500,
      ...this.caps,
    };
  }

  async readSelection(): Promise<SessionCreate> {
    this.calls.push('readSelection');
    return structuredClone(this.selection);
  }

  async applyPlan(plan: EditPlan, opts: ApplyOptions): Promise<ApplyResult> {
    this.calls.push(`applyPlan:${opts.method}`);
    if (this.failNative) throw new PluginError('host_error', this.failNative);
    const items = placements(plan, opts.method);
    opts.onProgress?.(1, `${items.length} items`);
    return this.addSequence(plan, items, 'native');
  }

  async importXml(path: string, plan: EditPlan): Promise<ApplyResult> {
    this.calls.push(`importXml:${path}`);
    return this.addSequence(plan, placements(plan, plan.method), 'xml', path);
  }

  async addMarkers(sequenceId: string, markers: PlanMarker[]): Promise<number> {
    this.calls.push('addMarkers');
    const seq = this.sequences.find((s) => s.id === sequenceId);
    if (!seq) throw new PluginError('host_error', 'no such sequence');
    seq.markers.push(...markers);
    return markers.length;
  }

  async readTimeline(sequenceId: string, plan: EditPlan): Promise<EditPlan> {
    const seq = this.sequences.find((s) => s.id === sequenceId);
    if (!seq) throw new PluginError('host_error', 'no such sequence');
    return plan;
  }

  undo(): void {
    const id = this.undoStack.pop();
    this.sequences = this.sequences.filter((s) => s.id !== id);
  }

  private addSequence(
    plan: EditPlan,
    items: PlaceOp[],
    via: 'native' | 'xml',
    xmlPath?: string,
  ): ApplyResult {
    const id = `seq-${this.sequences.length + 1}`;
    this.sequences.push({
      id,
      name: plan.sequence.name,
      items,
      markers: [],
      via,
      ...(xmlPath ? { xmlPath } : {}),
    });
    this.undoStack.push(id);
    return { sequenceId: id, sequenceName: plan.sequence.name, via, markers: 0, warnings: [] };
  }
}

/** An EngineHost that serves a fixed engine.json and records opened URLs. */
export function fakeEngineHost(engineJson: () => string | null) {
  const opened: string[] = [];
  return {
    opened,
    readEngineFile: async () => engineJson(),
    openUrl: async (url: string) => {
      opened.push(url);
    },
  };
}
