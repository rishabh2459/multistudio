import path from 'node:path';

export const DESKTOP_DIR = path.resolve(__dirname, '..');
export const REPO_ROOT = path.resolve(DESKTOP_DIR, '../..');
export const E2E_DIR = path.join(DESKTOP_DIR, '.e2e');
export const MEDIA_DIR = process.env.E2E_MEDIA_DIR ?? path.join(E2E_DIR, 'media');

// The bridge the preload script exposes (full contract: apps/web/lib/desktop.ts).
declare global {
  interface Window {
    multicam?: { apiBase?: string; apiToken?: string; pickFiles?: unknown };
  }
}
