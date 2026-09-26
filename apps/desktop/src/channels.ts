/** IPC channel names shared by main and preload (preload repeats them: a
 *  sandboxed preload script cannot import local files; a test keeps them equal). */
export const CHANNELS = {
  config: 'multicam:config',
  pickFiles: 'multicam:pick-files',
  pickFolder: 'multicam:pick-folder',
  showInFolder: 'multicam:show-in-folder',
  copyDiagnostics: 'multicam:copy-diagnostics',
  openLogs: 'multicam:open-logs',
} as const;

/** What the preload script gets synchronously before the page loads. */
export interface BridgeConfig {
  apiBase: string | null;
  apiToken: string;
  appVersion: string;
  platform: string;
}

export const VIDEO_EXTENSIONS = [
  'mp4',
  'mov',
  'm4v',
  'mkv',
  'avi',
  'mts',
  'm2ts',
  'mxf',
  'webm',
  'wav',
  'mp3',
  'm4a',
];
