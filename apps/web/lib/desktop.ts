/**
 * Bridge exposed by the desktop app's preload script (Phase 6). In a plain
 * browser (development) it is absent and the UI falls back to typed paths.
 */
export interface DesktopBridge {
  /** Base URL of the local API (the sidecar picks a free port). */
  apiBase?: string;
  /** Per-launch API token. */
  apiToken?: string;
  /** Native file picker; returns absolute paths. */
  pickFiles?: (options: { title?: string; multiple?: boolean }) => Promise<string[]>;
  /** Native folder picker; returns an absolute path or null. */
  pickFolder?: (options: { title?: string }) => Promise<string | null>;
  /** Reveal a file in Finder / Explorer. */
  showInFolder?: (path: string) => Promise<void>;
}

declare global {
  interface Window {
    multicam?: DesktopBridge;
  }
}

export function desktop(): DesktopBridge | undefined {
  return typeof window === 'undefined' ? undefined : window.multicam;
}
