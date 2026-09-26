/**
 * End-to-end test of the desktop app: real Electron window, real engine.
 *
 *   pnpm --filter @multicam/web build      # the UI the app loads
 *   pnpm --filter @multicam/desktop e2e
 *
 * Development layout (engine via `uv run multicam-api`, UI from apps/web/out).
 * Native file dialogs are replaced inside the test.
 */
import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  timeout: 300_000,
  expect: { timeout: 20_000 },
  workers: 1,
  reporter: process.env.CI ? [['github'], ['list']] : 'list',
  globalSetup: './e2e/global-setup.ts',
  use: { trace: 'retain-on-failure' },
});
