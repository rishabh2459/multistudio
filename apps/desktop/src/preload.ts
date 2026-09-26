/**
 * Preload script: the only bridge between the web UI and the OS.
 * Runs sandboxed, so it may import nothing but 'electron' (channel names are
 * repeated here on purpose; see channels.ts).
 * Exposes window.multicam (contract: apps/web/lib/desktop.ts).
 */
import { contextBridge, ipcRenderer } from 'electron';

const config = ipcRenderer.sendSync('multicam:config') as {
  apiBase: string | null;
  apiToken: string;
  appVersion: string;
  platform: string;
};

contextBridge.exposeInMainWorld('multicam', {
  apiBase: config.apiBase ?? undefined,
  apiToken: config.apiToken,
  appVersion: config.appVersion,
  platform: config.platform,
  pickFiles: (options: { title?: string; multiple?: boolean } = {}): Promise<string[]> =>
    ipcRenderer.invoke('multicam:pick-files', options),
  pickFolder: (options: { title?: string } = {}): Promise<string | null> =>
    ipcRenderer.invoke('multicam:pick-folder', options),
  showInFolder: (path: string): Promise<void> =>
    ipcRenderer.invoke('multicam:show-in-folder', path),
  copyDiagnostics: (): Promise<string> => ipcRenderer.invoke('multicam:copy-diagnostics'),
  openLogs: (): Promise<void> => ipcRenderer.invoke('multicam:open-logs'),
});
