import type { ErrorCode } from './types';

/** Every failure the panel shows: a stable code, a message and what to do. */
export class PluginError extends Error {
  constructor(
    readonly code: ErrorCode,
    message: string,
    readonly hint = '',
    readonly status = 0,
  ) {
    super(message);
    this.name = 'PluginError';
  }

  static from(err: unknown, fallback: ErrorCode = 'host_error'): PluginError {
    if (err instanceof PluginError) return err;
    const message = err instanceof Error ? err.message : String(err);
    return new PluginError(fallback, message);
  }
}

/** Human text for a code when the engine sent no hint. */
export const DEFAULT_HINTS: Partial<Record<ErrorCode, string>> = {
  engine_unreachable: 'Start Multicam Studio (or press Start engine) and try again.',
  engine_incompatible: 'Update Multicam Studio and this plugin to matching versions.',
  unauthorized: 'Reconnect: the engine was restarted.',
  media_offline: 'Relink the media in your project, then start again.',
  setup_required: 'Check who is in each camera and which mic belongs to whom.',
  no_plan: 'Run Auto Edit first.',
};
