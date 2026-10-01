/**
 * The auto-edit flow every host panel runs (PLUGIN_PLAN 3.3):
 *
 *   idle -> connecting -> setup -> running -> review -> applying -> applied
 *                 \___________\__________\_________\__________-> error
 *
 * One controller per panel. The UI subscribes to state changes; the host adapter
 * is the only host-specific part.
 */
import type { ApplyResult, HostAdapter, HostCaps } from './adapter';
import type { ClientOptions, PluginClient } from './client';
import { connectEngine, startEngine, type EngineHost } from './engine';
import { DEFAULT_HINTS, PluginError } from './errors';
import { followRun, type ProgressEvent } from './events';
import { decideApply, type ApplyDecision } from './plan';
import { defaultRoles } from './setup';
import type {
  EditPlan,
  ErrorCode,
  Handshake,
  PlanMethod,
  Preset,
  SessionOut,
  SessionSetup,
} from './types';

export type Phase =
  | 'idle'
  | 'connecting'
  | 'setup'
  | 'running'
  | 'review'
  | 'applying'
  | 'applied'
  | 'error';

export interface FlowError {
  code: ErrorCode;
  message: string;
  hint: string;
}

export interface Progress {
  fraction: number;
  stage: string;
  message: string;
}

export interface FlowState {
  phase: Phase;
  /** Phase to return to after an error is dismissed. */
  resume: Phase;
  handshake: Handshake | null;
  session: SessionOut | null;
  plan: EditPlan | null;
  progress: Progress | null;
  decision: ApplyDecision | null;
  applied: ApplyResult | null;
  error: FlowError | null;
  /** Applied versions in this panel (re-apply keeps v7, v8 ...). */
  history: ApplyResult[];
}

const ALLOWED: Record<Phase, Phase[]> = {
  idle: ['connecting'],
  connecting: ['setup', 'review', 'error', 'idle'],
  setup: ['setup', 'running', 'connecting', 'review', 'idle'],
  running: ['review', 'setup', 'error'],
  review: ['review', 'running', 'applying', 'setup', 'connecting', 'idle'],
  applying: ['applied', 'error'],
  applied: ['review', 'running', 'setup', 'applying', 'connecting', 'idle'],
  error: ['idle', 'connecting', 'setup', 'running', 'review', 'applying', 'applied'],
};

export interface ControllerOptions {
  client?: ClientOptions;
  /** Force polling instead of SSE (hosts without streaming fetch). */
  poll?: boolean;
  pollMs?: number;
  /** Guess roles/names on a new session (default true). */
  autoSetup?: boolean;
}

type Listener = (state: FlowState) => void;

export class AutoEditController {
  private state: FlowState = {
    phase: 'idle',
    resume: 'idle',
    handshake: null,
    session: null,
    plan: null,
    progress: null,
    decision: null,
    applied: null,
    error: null,
    history: [],
  };
  private readonly listeners = new Set<Listener>();
  private client: PluginClient | null = null;
  private caps: HostCaps | null = null;
  private lastAction: (() => Promise<void>) | null = null;

  constructor(
    readonly adapter: HostAdapter,
    readonly engineHost: EngineHost,
    private readonly opts: ControllerOptions = {},
  ) {}

  // ---------------------------------------------------------------- state
  getState(): FlowState {
    return this.state;
  }

  subscribe(listener: Listener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  get engine(): PluginClient | null {
    return this.client;
  }

  private set(patch: Partial<FlowState>): void {
    const next = patch.phase;
    if (
      next &&
      next !== 'error' &&
      next !== this.state.phase &&
      !ALLOWED[this.state.phase].includes(next)
    ) {
      throw new Error(`illegal transition ${this.state.phase} -> ${next}`);
    }
    this.state = { ...this.state, ...patch };
    for (const l of this.listeners) l(this.state);
  }

  private async guard(action: () => Promise<void>): Promise<void> {
    this.lastAction = action;
    const resume = this.state.phase === 'error' ? this.state.resume : this.state.phase;
    try {
      await action();
    } catch (err) {
      const e = PluginError.from(err);
      this.set({
        phase: 'error',
        resume: resume === 'connecting' || resume === 'idle' ? 'idle' : backTo(resume),
        error: { code: e.code, message: e.message, hint: e.hint || DEFAULT_HINTS[e.code] || '' },
      });
    }
  }

  private need(): PluginClient {
    if (!this.client) throw new PluginError('engine_unreachable', 'not connected to the engine');
    return this.client;
  }

  private needSession(): SessionOut {
    if (!this.state.session) throw new PluginError('setup_required', 'select clips first');
    return this.state.session;
  }

  // ---------------------------------------------------------------- actions
  /** Find the engine (start it when `start`), then read the host selection. */
  connect(start = false): Promise<void> {
    return this.guard(async () => {
      this.set({ phase: 'connecting', error: null, progress: null });
      const conn = start
        ? await startEngine(this.engineHost, this.opts.client)
        : await connectEngine(this.engineHost, this.opts.client);
      this.client = conn.client;
      this.caps = null;
      this.set({ handshake: conn.handshake });
      await this.loadSelectionInner();
    });
  }

  /** Re-read what is selected in the host (new clips -> new session). */
  loadSelection(): Promise<void> {
    return this.guard(async () => {
      this.set({ phase: 'connecting', error: null });
      await this.loadSelectionInner();
    });
  }

  private async loadSelectionInner(): Promise<void> {
    const client = this.need();
    const selection = await this.adapter.readSelection();
    let session = await client.createSession(selection);
    if (!session.reused && this.opts.autoSetup !== false) {
      session = await client.setup(session.id, { roles: defaultRoles(session) });
    }
    let plan: EditPlan | null = null;
    if (session.reused && session.plan) {
      plan = await client.editPlan(session.id, { host: this.adapter.host });
    }
    this.set({ phase: plan ? 'review' : 'setup', session, plan, applied: null, decision: null });
  }

  /** Save setup changes (roles, layout, preset, sliders, method). */
  updateSetup(body: SessionSetup): Promise<void> {
    return this.guard(async () => {
      const session = await this.need().setup(this.needSession().id, body);
      const phase = this.state.phase === 'error' ? this.state.resume : this.state.phase;
      this.set({ phase: phase === 'applied' ? 'review' : phase, session, error: null });
    });
  }

  /** Full auto edit (sync if needed, analyse, decide), then fetch the plan. */
  run(opts: { framing?: boolean; vad?: 'auto' | 'silero' | 'energy' } = {}): Promise<void> {
    return this.guard(() => this.runInner({ steps: 'auto', ...opts }));
  }

  /** New preset on the stored analysis: only "decide" runs (< 1 s). */
  recut(preset?: Preset): Promise<void> {
    return this.guard(async () => {
      const id = this.needSession().id;
      if (preset) {
        const session = await this.need().setup(id, { preset });
        this.set({ session });
      }
      await this.runInner({ steps: ['decide'] });
    });
  }

  private async runInner(body: {
    steps: 'auto' | ['decide'];
    framing?: boolean;
    vad?: 'auto' | 'silero' | 'energy';
  }): Promise<void> {
    const client = this.need();
    const id = this.needSession().id;
    this.set({
      phase: 'running',
      error: null,
      progress: { fraction: 0, stage: 'starting', message: '' },
    });
    const run = await client.run(id, body);
    await followRun(client, id, run.job_id, {
      ...(this.opts.poll !== undefined ? { poll: this.opts.poll } : {}),
      ...(this.opts.pollMs !== undefined ? { pollMs: this.opts.pollMs } : {}),
      onEvent: (ev) => {
        if (ev.type === 'progress') this.set({ progress: toProgress(ev.data) });
      },
    });
    const [session, plan] = await Promise.all([
      client.getSession(id),
      client.editPlan(id, { host: this.adapter.host }),
    ]);
    this.set({ phase: 'review', session, plan, progress: null, applied: null });
  }

  /** Show another method's plan (same cuts) before applying. */
  previewMethod(method: PlanMethod): Promise<void> {
    return this.guard(async () => {
      const id = this.needSession().id;
      const plan = await this.need().editPlan(id, { host: this.adapter.host, method });
      this.set({ plan });
    });
  }

  /** Build the edit in the host: natively, or by XML import when that is better. */
  apply(opts: { method?: PlanMethod; viaXml?: boolean } = {}): Promise<void> {
    return this.guard(async () => {
      const plan = this.state.plan;
      if (!plan) throw new PluginError('no_plan', 'no edit to apply yet');
      const client = this.need();
      this.caps ??= await this.adapter.capabilities();
      const decision = decideApply(plan, this.caps, opts);
      this.set({
        phase: 'applying',
        decision,
        error: null,
        progress: { fraction: 0, stage: 'applying', message: decision.reason },
      });
      const onProgress = (fraction: number, message: string) =>
        this.set({ progress: { fraction, stage: 'applying', message } });
      let result: ApplyResult;
      const viaXml = async (): Promise<ApplyResult> => {
        const fmt = this.caps!.xmlImport;
        if (!fmt) throw new PluginError('not_available', 'this host cannot import XML');
        const file = await client.exportFile(this.needSession().id, fmt, plan.cutlist_version);
        return this.adapter.importXml(file.path, plan);
      };
      if (decision.via === 'xml') {
        result = await viaXml();
      } else {
        try {
          result = await this.adapter.applyPlan(plan, { method: decision.method, onProgress });
        } catch (err) {
          if (!this.caps.xmlImport) throw err;
          // Rule C: a host API gap never blocks the user.
          result = await viaXml();
          result = {
            ...result,
            warnings: [
              ...result.warnings,
              `native apply failed (${PluginError.from(err).message}); imported XML instead`,
            ],
          };
        }
      }
      if (this.caps.markers && plan.markers.length && result.markers === 0) {
        result = {
          ...result,
          markers: await this.adapter.addMarkers(result.sequenceId, plan.markers, plan),
        };
      }
      this.set({
        phase: 'applied',
        applied: result,
        progress: null,
        history: [...this.state.history, result],
      });
    });
  }

  /** Send the editor's final timeline back ("learn my style", PL8). */
  sendFeedback(note?: string): Promise<void> {
    return this.guard(async () => {
      const { applied, plan } = this.state;
      if (!applied || !plan || !this.adapter.readTimeline) {
        throw new PluginError('not_available', 'nothing applied to read back');
      }
      const final = await this.adapter.readTimeline(applied.sequenceId, plan);
      await this.need().feedback(this.needSession().id, final, note);
    });
  }

  /** Retry whatever failed last. */
  retry(): Promise<void> {
    return this.lastAction ? this.guard(this.lastAction) : Promise.resolve();
  }

  dismissError(): void {
    if (this.state.phase === 'error') this.set({ phase: this.state.resume, error: null });
  }

  /** Back to setup (keep the session). */
  backToSetup(): void {
    if (this.state.session) this.set({ phase: 'setup', error: null });
  }
}

function toProgress(p: ProgressEvent): Progress {
  return { fraction: p.progress, stage: p.stage, message: p.message };
}

/** Where an action that failed leaves the user. */
function backTo(phase: Phase): Phase {
  if (phase === 'running') return 'setup';
  if (phase === 'applying') return 'review';
  return phase;
}
