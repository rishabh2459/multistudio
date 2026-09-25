/**
 * End-to-end test of the UI against the real engine.
 *
 *   pnpm --filter @multicam/web e2e
 *
 * Starts the API on port 8799 (fresh data folder in .e2e/) and `next dev` on
 * port 3100, makes a synthetic 3-camera recording, then clicks through
 * create -> add clips -> auto edit -> export. Needs uv, ffmpeg and a Chromium
 * (`pnpm --filter @multicam/web exec playwright install chromium` once).
 */
import { defineConfig, devices } from '@playwright/test';
import path from 'node:path';

import { API_PORT, E2E_DIR, REPO_ROOT, WEB_PORT } from './e2e/paths';

export default defineConfig({
  testDir: './e2e',
  timeout: 240_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [['github'], ['html', { open: 'never' }]] : 'list',
  globalSetup: './e2e/global-setup.ts',
  use: {
    baseURL: `http://localhost:${WEB_PORT}`,
    trace: 'retain-on-failure',
    ...devices['Desktop Chrome'],
  },
  webServer: [
    {
      command: `uv run multicam-api --port ${API_PORT} --data-dir "${path.join(E2E_DIR, 'data')}"`,
      cwd: REPO_ROOT,
      url: `http://127.0.0.1:${API_PORT}/api/system/health`,
      env: { MULTICAM_CORS: `http://localhost:${WEB_PORT},http://127.0.0.1:${WEB_PORT}` },
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command: `pnpm exec next dev --port ${WEB_PORT}`,
      url: `http://localhost:${WEB_PORT}`,
      env: { NEXT_PUBLIC_API_URL: `http://127.0.0.1:${API_PORT}` },
      reuseExistingServer: !process.env.CI,
      timeout: 180_000,
    },
  ],
});
