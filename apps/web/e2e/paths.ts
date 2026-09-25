import path from 'node:path';
import { fileURLToPath } from 'node:url';

export const WEB_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
export const REPO_ROOT = path.resolve(WEB_DIR, '../..');
export const E2E_DIR = path.join(WEB_DIR, '.e2e');
export const E2E_MEDIA_DIR = path.join(E2E_DIR, 'media');
export const API_PORT = 8799;
export const WEB_PORT = 3100;
