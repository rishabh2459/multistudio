/**
 * IPC bridge: the Resolve object only exists in the plugin's main process, the
 * panel (plugin-core React UI) runs in the renderer. Errors cross as
 * {code, message, hint} and become PluginErrors again.
 */
import {
  PluginError,
  type ApplyOptions,
  type ApplyResult,
  type EditPlan,
  type EngineHost,
  type ErrorCode,
  type HostAdapter,
  type HostCaps,
  type PlanMarker,
  type SessionCreate,
} from '@multicam/plugin-core';

export type Envelope<T = unknown> =
  | { ok: true; value: T }
  | { ok: false; error: { code: string; message: string; hint: string } };
export type Invoke = (
  target: 'host' | 'engine',
  method: string,
  args: unknown[],
) => Promise<Envelope>;

const HOST_METHODS = [
  'capabilities',
  'readSelection',
  'applyPlan',
  'importXml',
  'addMarkers',
] as const;
const ENGINE_METHODS = ['readEngineFile', 'openUrl'] as const;

/** Main process side: run a whitelisted method and wrap the outcome. */
export function makeHandler(adapter: HostAdapter, engine: EngineHost) {
  return async (target: unknown, method: unknown, args: unknown): Promise<Envelope> => {
    try {
      const list: readonly string[] =
        target === 'host' ? HOST_METHODS : target === 'engine' ? ENGINE_METHODS : [];
      if (typeof method !== 'string' || !list.includes(method) || !Array.isArray(args)) {
        throw new PluginError(
          'invalid_request',
          `unknown bridge call ${String(target)}.${String(method)}`,
        );
      }
      const obj = (target === 'host' ? adapter : engine) as unknown as Record<
        string,
        (...a: unknown[]) => Promise<unknown>
      >;
      // onProgress callbacks cannot cross IPC: drop functions from options.
      const clean = args.map((a) =>
        a && typeof a === 'object' && !Array.isArray(a)
          ? Object.fromEntries(Object.entries(a).filter(([, v]) => typeof v !== 'function'))
          : a,
      );
      return { ok: true, value: await obj[method]!.apply(obj, clean) };
    } catch (err) {
      const e = PluginError.from(err);
      return { ok: false, error: { code: e.code, message: e.message, hint: e.hint } };
    }
  };
}

async function call<T>(
  invoke: Invoke,
  target: 'host' | 'engine',
  method: string,
  args: unknown[],
): Promise<T> {
  const env = await invoke(target, method, args);
  if (env.ok) return env.value as T;
  throw new PluginError(env.error.code as ErrorCode, env.error.message, env.error.hint);
}

/** Renderer side: a HostAdapter that forwards to the main process. */
export class BridgeAdapter implements HostAdapter {
  readonly host = 'resolve' as const;
  constructor(private readonly invoke: Invoke) {}
  capabilities(): Promise<HostCaps> {
    return call(this.invoke, 'host', 'capabilities', []);
  }
  readSelection(): Promise<SessionCreate> {
    return call(this.invoke, 'host', 'readSelection', []);
  }
  applyPlan(plan: EditPlan, opts: ApplyOptions): Promise<ApplyResult> {
    // Functions cannot cross IPC (structured clone): send the plain options only.
    const { onProgress: _progress, ...plain } = opts;
    return call(this.invoke, 'host', 'applyPlan', [plan, plain]);
  }
  importXml(path: string, plan: EditPlan): Promise<ApplyResult> {
    return call(this.invoke, 'host', 'importXml', [path, plan]);
  }
  addMarkers(sequenceId: string, markers: PlanMarker[], plan: EditPlan): Promise<number> {
    return call(this.invoke, 'host', 'addMarkers', [sequenceId, markers, plan]);
  }
}

export class BridgeEngineHost implements EngineHost {
  constructor(private readonly invoke: Invoke) {}
  readEngineFile(): Promise<string | null> {
    return call(this.invoke, 'engine', 'readEngineFile', []);
  }
  openUrl(url: string): Promise<void> {
    return call(this.invoke, 'engine', 'openUrl', [url]);
  }
}
