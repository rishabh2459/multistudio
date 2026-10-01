/**
 * Workflow Integration plugin main process (Resolve Studio, Workspace → Workflow
 * Integrations → Multicam Studio). Resolve starts this with its own Electron.
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

import { engineFilePath } from '@multicam/plugin-core';
import { BrowserWindow, app, ipcMain, shell } from 'electron';

import { ResolveWiAdapter } from './adapter';
import { makeHandler } from './bridge';
import type { Resolve } from './resolve-api';

const PLUGIN_ID = 'com.multicamstudio.resolve';
const ROOT = path.join(__dirname, '..');

function platform(): 'mac' | 'windows' | 'linux' {
  return process.platform === 'darwin' ? 'mac' : process.platform === 'win32' ? 'windows' : 'linux';
}

async function getResolve(): Promise<Resolve> {
  // WorkflowIntegration.node ships with Resolve (Developer/Workflow Integrations); the
  // installer copies it next to this plugin.
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const wi = require(path.join(ROOT, 'WorkflowIntegration.node'));
  if (!(await wi.Initialize(PLUGIN_ID))) throw new Error('Resolve refused the plugin id');
  const resolve = await wi.GetResolve();
  if (!resolve) throw new Error('Resolve is not available (Studio only)');
  return resolve as Resolve;
}

async function start(): Promise<void> {
  const resolve = await getResolve();
  const adapter = new ResolveWiAdapter(resolve, platform());
  const engine = {
    readEngineFile: async () => {
      try {
        return fs.readFileSync(engineFilePath(platform(), os.homedir(), process.env), 'utf8');
      } catch {
        return null;
      }
    },
    openUrl: async (url: string) => {
      if (url.startsWith('multicam://')) await shell.openExternal(url);
    },
  };
  const handle = makeHandler(adapter, engine);
  ipcMain.handle('multicam', (_event, target, method, args) => handle(target, method, args));

  const win = new BrowserWindow({
    width: 380,
    height: 640,
    title: 'Multicam Studio',
    backgroundColor: '#1f1f23',
    webPreferences: {
      preload: path.join(ROOT, 'dist', 'preload.js'),
      contextIsolation: true,
      sandbox: true,
      nodeIntegration: false,
    },
  });
  await win.loadFile(path.join(ROOT, 'index.html'));
}

app.whenReady().then(start, (err) => console.error(err));
app.on('window-all-closed', () => app.quit());
