/**
 * Electron main process: starts the engine, serves the UI, owns the window.
 */
import { randomBytes } from 'node:crypto';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

import {
  BrowserWindow,
  Menu,
  app,
  clipboard,
  dialog,
  ipcMain,
  nativeTheme,
  protocol,
  shell,
  type IpcMainEvent,
  type IpcMainInvokeEvent,
  type MenuItemConstructorOptions,
} from 'electron';

import { CHANNELS, VIDEO_EXTENSIONS, type BridgeConfig } from './channels';
import { buildDiagnosticReport } from './diagnostics';
import { resolveLayout, type Layout } from './layout';
import { LogFile, tailFile } from './logs';
import { Sidecar, SidecarError } from './sidecar';
import { splashUrl } from './splash';
import {
  APP_HOST,
  APP_ORIGIN,
  APP_SCHEME,
  contentSecurityPolicy,
  mimeType,
  resolveStaticPath,
} from './static-files';

protocol.registerSchemesAsPrivileged([
  {
    scheme: APP_SCHEME,
    privileges: { standard: true, secure: true, supportFetchAPI: true, codeCache: true },
  },
]);

const isFile = (p: string) => {
  try {
    return fs.statSync(p).isFile();
  } catch {
    return false;
  }
};

const layout: Layout = resolveLayout({
  packaged: app.isPackaged,
  resourcesPath: process.resourcesPath,
  appPath: app.getAppPath(),
  platform: process.platform,
  env: process.env,
  isFile,
});

app.setAppLogsPath(); // ~/Library/Logs/Multicam Studio, %APPDATA%\Multicam Studio\logs
const logsDir = app.getPath('logs');
const mainLog = new LogFile(path.join(logsDir, 'main.log'));
const apiLog = new LogFile(path.join(logsDir, 'engine.log'));
const token = randomBytes(24).toString('base64url');
const uiOrigin = layout.webUrl ? new URL(layout.webUrl).origin : APP_ORIGIN;

const sidecar = new Sidecar({
  backend: layout.backend,
  token,
  uiOrigin,
  log: (source, line) =>
    source === 'sidecar' ? mainLog.write('engine', line) : apiLog.write(source, line),
});

let mainWindow: BrowserWindow | null = null;
let quitting = false;

function log(line: string): void {
  mainLog.write('main', line);
  if (!app.isPackaged) console.log(`[main] ${line}`);
}

function uiUrl(): string {
  return layout.webUrl ?? `${APP_ORIGIN}/`;
}

// ------------------------------------------------------------------ static UI
function serveStaticUi(): void {
  const csp = contentSecurityPolicy();
  protocol.handle(APP_SCHEME, async (request) => {
    const url = new URL(request.url);
    if (url.host !== APP_HOST) return new Response('Not found', { status: 404 });
    const file = resolveStaticPath(layout.webRoot, url.pathname, isFile);
    const headers = { 'Content-Security-Policy': csp, 'X-Content-Type-Options': 'nosniff' };
    if (!file) {
      const notFound = path.join(layout.webRoot, '404.html');
      const body = isFile(notFound) ? await fs.promises.readFile(notFound) : 'Not found';
      return new Response(body, {
        status: 404,
        headers: { ...headers, 'Content-Type': 'text/html; charset=utf-8' },
      });
    }
    const body = await fs.promises.readFile(file);
    return new Response(body, { headers: { ...headers, 'Content-Type': mimeType(file) } });
  });
}

// ------------------------------------------------------------------ IPC
function fromOurUi(event: IpcMainEvent | IpcMainInvokeEvent): boolean {
  const url = event.senderFrame?.url ?? '';
  return url.startsWith(`${APP_ORIGIN}/`) || (!!layout.webUrl && url.startsWith(uiOrigin));
}

function bridgeConfig(): BridgeConfig {
  return {
    apiBase: sidecar.info?.baseUrl ?? null,
    apiToken: token,
    appVersion: app.getVersion(),
    platform: process.platform,
  };
}

async function diagnosticReport(): Promise<string> {
  let systemInfo: unknown = 'engine not running';
  const info = sidecar.info;
  if (info) {
    try {
      const res = await fetch(`${info.baseUrl}/api/system/info`, {
        headers: { 'X-Multicam-Token': token },
      });
      systemInfo = await res.json();
    } catch (err) {
      systemInfo = `could not ask the engine: ${(err as Error).message}`;
    }
  }
  return buildDiagnosticReport({
    appVersion: app.getVersion(),
    versions: {
      electron: process.versions.electron,
      chrome: process.versions.chrome,
      node: process.versions.node,
    },
    os: {
      platform: process.platform,
      release: os.release(),
      arch: process.arch,
      cpus: `${os.cpus().length}× ${os.cpus()[0]?.model ?? 'CPU'}`,
      memoryGb: os.totalmem() / 1024 ** 3,
    },
    packaged: app.isPackaged,
    paths: {
      logs: logsDir,
      userData: app.getPath('userData'),
      web: layout.webRoot,
      engine: layout.backend.command,
    },
    engine: {
      status: sidecar.status,
      url: info?.baseUrl ?? null,
      pid: info?.pid ?? null,
      restarts: sidecar.restarts,
      lastExit: sidecar.lastExit,
    },
    systemInfo,
    logs: {
      'engine.log': tailFile(apiLog.file, 150),
      'main.log': tailFile(mainLog.file, 80),
    },
    token,
    now: new Date(),
  });
}

function registerIpc(): void {
  ipcMain.on(CHANNELS.config, (event) => {
    event.returnValue = fromOurUi(event) ? bridgeConfig() : null;
  });

  const handle = <A extends unknown[], R>(
    channel: string,
    fn: (event: IpcMainInvokeEvent, ...args: A) => Promise<R> | R,
  ) =>
    ipcMain.handle(channel, (event, ...args: unknown[]) => {
      if (!fromOurUi(event)) throw new Error('not allowed');
      return fn(event, ...(args as A));
    });

  handle(CHANNELS.pickFiles, async (event, options: { title?: string; multiple?: boolean }) => {
    const win = BrowserWindow.fromWebContents(event.sender);
    const opts: Electron.OpenDialogOptions = {
      title: typeof options?.title === 'string' ? options.title : 'Choose files',
      properties: options?.multiple ? ['openFile', 'multiSelections'] : ['openFile'],
      filters: [
        { name: 'Video and audio', extensions: VIDEO_EXTENSIONS },
        { name: 'All files', extensions: ['*'] },
      ],
    };
    const result = win ? await dialog.showOpenDialog(win, opts) : await dialog.showOpenDialog(opts);
    return result.canceled ? [] : result.filePaths;
  });

  handle(CHANNELS.pickFolder, async (event, options: { title?: string }) => {
    const win = BrowserWindow.fromWebContents(event.sender);
    const opts: Electron.OpenDialogOptions = {
      title: typeof options?.title === 'string' ? options.title : 'Choose a folder',
      properties: ['openDirectory', 'createDirectory'],
    };
    const result = win ? await dialog.showOpenDialog(win, opts) : await dialog.showOpenDialog(opts);
    return result.canceled ? null : (result.filePaths[0] ?? null);
  });

  handle(CHANNELS.showInFolder, (_event, target: unknown) => {
    if (typeof target === 'string' && path.isAbsolute(target)) shell.showItemInFolder(target);
  });

  handle(CHANNELS.copyDiagnostics, async () => {
    const report = await diagnosticReport();
    clipboard.writeText(report);
    return report;
  });

  handle(CHANNELS.openLogs, async () => {
    await shell.openPath(logsDir);
  });
}

// ------------------------------------------------------------------ menu
function buildMenu(): void {
  const isMac = process.platform === 'darwin';
  const help: MenuItemConstructorOptions = {
    role: 'help',
    submenu: [
      { label: 'Open Logs Folder', click: () => void shell.openPath(logsDir) },
      {
        label: 'Copy Diagnostic Report',
        click: async () => {
          clipboard.writeText(await diagnosticReport());
          void dialog.showMessageBox({
            message: 'Diagnostic report copied',
            detail: 'Paste it into your message to support. It contains no API token.',
          });
        },
      },
      {
        label: 'Show Data Folder',
        click: () => void shell.openPath(app.getPath('userData')),
      },
    ],
  };
  const template: MenuItemConstructorOptions[] = [
    ...(isMac ? [{ role: 'appMenu' as const }] : []),
    { role: 'fileMenu' },
    { role: 'editMenu' },
    {
      label: 'View',
      submenu: [
        { role: 'reload' },
        ...(app.isPackaged ? [] : [{ role: 'toggleDevTools' as const }]),
        { type: 'separator' },
        { role: 'resetZoom' },
        { role: 'zoomIn' },
        { role: 'zoomOut' },
        { type: 'separator' },
        { role: 'togglefullscreen' },
      ],
    },
    { role: 'windowMenu' },
    help,
  ];
  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

// ------------------------------------------------------------------ window
function createWindow(): BrowserWindow {
  const win = new BrowserWindow({
    width: 1280,
    height: 860,
    minWidth: 900,
    minHeight: 600,
    title: 'Multicam Studio',
    backgroundColor: nativeTheme.shouldUseDarkColors ? '#111318' : '#f7f7f8',
    show: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      sandbox: true,
      nodeIntegration: false,
      webSecurity: true,
      spellcheck: false,
    },
  });
  win.once('ready-to-show', () => win.show());
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:\/\//.test(url) && !url.startsWith('http://127.0.0.1')) {
      void shell.openExternal(url);
    }
    return { action: 'deny' };
  });
  win.webContents.on('will-navigate', (event, url) => {
    const allowed = url.startsWith(`${APP_ORIGIN}/`) || url.startsWith(uiOrigin);
    if (!allowed) {
      event.preventDefault();
      log(`blocked navigation to ${url}`);
    }
  });
  win.on('closed', () => {
    if (mainWindow === win) mainWindow = null;
  });
  void win.loadURL(splashUrl(nativeTheme.shouldUseDarkColors));
  return win;
}

async function startEngine(): Promise<void> {
  try {
    const info = await sidecar.start();
    log(`engine ready at ${info.baseUrl}`);
    await mainWindow?.loadURL(uiUrl());
  } catch (err) {
    await engineFailed(err as Error);
  }
}

async function engineFailed(err: Error): Promise<void> {
  if (quitting) return;
  log(`engine failed: ${err.message}`);
  const output = err instanceof SidecarError ? err.output.slice(-8).join('\n') : '';
  const options: Electron.MessageBoxOptions = {
    type: 'error',
    message: 'The processing engine could not start',
    detail: `${err.message}\n\n${output}\n\nLogs: ${logsDir}`.trim(),
    buttons: ['Try Again', 'Open Logs Folder', 'Quit'],
    defaultId: 0,
    cancelId: 2,
  };
  const { response } = mainWindow
    ? await dialog.showMessageBox(mainWindow, options)
    : await dialog.showMessageBox(options);
  if (response === 0) {
    await mainWindow?.loadURL(splashUrl(nativeTheme.shouldUseDarkColors));
    await startEngine();
  } else if (response === 1) {
    await shell.openPath(logsDir);
    await engineFailed(err);
  } else {
    app.quit();
  }
}

sidecar.on('restarted', ({ info, portChanged }) => {
  log(`engine restarted at ${info.baseUrl}`);
  if (portChanged) mainWindow?.reload(); // preload picks up the new address
});
sidecar.on('failed', (err) => void engineFailed(err));

// ------------------------------------------------------------------ lifecycle
if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });

  app.whenReady().then(async () => {
    log(`Multicam Studio ${app.getVersion()} starting (packaged: ${app.isPackaged})`);
    log(`ui: ${layout.webUrl ?? layout.webRoot}; engine: ${layout.backend.command}`);
    serveStaticUi();
    registerIpc();
    buildMenu();
    mainWindow = createWindow();
    await startEngine();
  });

  app.on('window-all-closed', () => app.quit());

  app.on('before-quit', (event) => {
    if (quitting) return;
    quitting = true;
    event.preventDefault();
    log('quitting: stopping the engine');
    void sidecar.stop().finally(() => {
      mainLog.close();
      apiLog.close();
      app.exit(0);
    });
  });
}
