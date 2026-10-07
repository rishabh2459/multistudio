/**
 * Panel entry (bundled to dist/index.js by scripts/build.mjs). Wires the real UXP
 * modules into the adapter and renders the shared plugin-core panel.
 */
import { AutoEditController } from '@multicam/plugin-core';
import { AutoEditPanel } from '@multicam/plugin-core/ui';
import { createRoot } from 'react-dom/client';

import { PremiereAdapter } from './adapter';
import { PremiereEngineHost, fileUrl } from './engine-host';
import type { PremierePro, UxpHost } from './ppro';
import { spectrumPrimitives } from './spectrum';

// UXP's require returns untyped host modules.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
declare const require: (name: string) => any;

function uxpHost(): UxpHost {
  const uxp = require('uxp');
  const os = require('os');
  return {
    appVersion: String(uxp.host?.version ?? ''),
    platform: () => (os.platform() === 'win32' ? 'windows' : 'mac'),
    homedir: () => os.homedir(),
    readFile: async (path) => {
      try {
        const entry = await uxp.storage.localFileSystem.getEntryWithUrl(fileUrl(path));
        return String(await entry.read({ format: uxp.storage.formats.utf8 }));
      } catch {
        return null;
      }
    },
    openExternal: async (url) => {
      await uxp.shell.openExternal(url, 'Multicam Studio will start its processing engine.');
    },
    pickFile: async (extensions) => {
      try {
        const file = await uxp.storage.localFileSystem.getFileForOpening({ types: extensions });
        return file ? String(file.nativePath) : null;
      } catch {
        return null;
      }
    },
  };
}

function mount(root: HTMLElement): void {
  const host = uxpHost();
  const ppro = require('premierepro') as PremierePro;
  const nativeApply = (() => {
    try {
      return localStorage.getItem('multicam.nativeApply') === '1';
    } catch {
      return false;
    }
  })();
  const controller = new AutoEditController(
    new PremiereAdapter(ppro, host, { nativeApply }),
    new PremiereEngineHost(host),
  );
  createRoot(root).render(
    <AutoEditPanel controller={controller} ui={spectrumPrimitives} hostLabel="Premiere Pro" />,
  );
}

const { entrypoints } = require('uxp');
let mounted = false;
entrypoints.setup({
  panels: {
    multicamPanel: {
      show() {
        if (mounted) return;
        mounted = true;
        mount(document.getElementById('root')!);
      },
    },
  },
});
