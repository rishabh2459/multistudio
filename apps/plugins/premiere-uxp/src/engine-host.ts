import { engineFilePath, type EngineHost } from '@multicam/plugin-core';

import type { UxpHost } from './ppro';

/** engine.json from the app-data folder; multicam://start through the OS. */
export class PremiereEngineHost implements EngineHost {
  constructor(private readonly uxp: UxpHost) {}

  get path(): string {
    return engineFilePath(this.uxp.platform(), this.uxp.homedir());
  }

  readEngineFile(): Promise<string | null> {
    return this.uxp.readFile(this.path);
  }

  openUrl(url: string): Promise<void> {
    return this.uxp.openExternal(url);
  }
}

/** A local path as the file: URL UXP's getEntryWithUrl expects. */
export function fileUrl(path: string): string {
  const p = path.replace(/\\/g, '/');
  return /^[A-Za-z]:\//.test(p) ? `file:/${p}` : `file:${p}`;
}
