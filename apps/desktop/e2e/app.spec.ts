import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

import { _electron, expect, test, type ElectronApplication, type Page } from '@playwright/test';

import { DESKTOP_DIR, MEDIA_DIR } from './paths';

let app: ElectronApplication;
let page: Page;
let closed = false;
const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'multicam-e2e-'));

test.beforeAll(async () => {
  app = await _electron.launch({
    args: [
      DESKTOP_DIR,
      ...(process.env.CI && process.platform === 'linux' ? ['--no-sandbox'] : []),
    ],
    ...(process.env.ELECTRON_PATH ? { executablePath: process.env.ELECTRON_PATH } : {}),
    env: { ...process.env, MULTICAM_DATA_DIR: dataDir } as Record<string, string>,
  });
  page = await app.firstWindow();
});

test.afterAll(async () => {
  if (!closed) await app?.close();
});

async function fakeFileDialog(files: string[]) {
  await app.evaluate(({ dialog }, paths) => {
    dialog.showOpenDialog = (async () => ({ canceled: false, filePaths: paths })) as never;
  }, files);
}

test('the app starts the engine and runs the whole flow', async () => {
  await expect(page.getByText('Engine ready')).toBeVisible({ timeout: 120_000 });
  const bridge = await page.evaluate(() => ({
    apiBase: window.multicam?.apiBase,
    hasToken: !!window.multicam?.apiToken,
    pickFiles: typeof window.multicam?.pickFiles,
    node: typeof (window as unknown as { require?: unknown }).require,
  }));
  expect(bridge.apiBase).toMatch(/^http:\/\/127\.0\.0\.1:\d+$/);
  expect(bridge).toMatchObject({ hasToken: true, pickFiles: 'function', node: 'undefined' });

  // The engine refuses requests without the per-launch token.
  const denied = await page.evaluate(
    async (base) => (await fetch(`${base}/api/projects`)).status,
    bridge.apiBase!,
  );
  expect(denied).toBe(401);

  await page.getByRole('link', { name: 'New project' }).first().click();
  await page.getByLabel('Name').fill('Desktop E2E');
  await page.getByRole('button', { name: 'Create project' }).click();
  await expect(page.getByRole('heading', { name: 'Desktop E2E' })).toBeVisible();

  await fakeFileDialog(['cam1.mp4', 'cam2.mp4', 'wide.mp4'].map((f) => path.join(MEDIA_DIR, f)));
  await page.getByRole('button', { name: 'Add camera files' }).click();
  const rows = page.getByTestId('clip-row');
  await expect(rows).toHaveCount(3);
  await rows.filter({ hasText: 'wide.mp4' }).getByLabel('Camera shows').selectOption('wide');
  await page.getByRole('button', { name: 'Continue', exact: true }).click();

  await page.getByLabel('Speech detection').selectOption('energy');
  await page.getByRole('button', { name: 'Start auto edit' }).click();
  await expect(page.getByTestId('cutlist-summary')).toBeVisible({ timeout: 180_000 });
  // Timeline editor: previews play (Electron decodes H.264), a camera switch is saved.
  await page.getByRole('button', { name: 'Continue to editing' }).click();
  await expect(page.getByTestId('timeline')).toBeVisible();
  await expect(page.getByTestId('job-progress')).toHaveCount(0, { timeout: 120_000 });
  const liveVideo = page.locator('[data-testid=program-monitor] button[aria-current=true] video');
  await expect
    .poll(() => liveVideo.evaluate((v: HTMLVideoElement) => v.readyState), { timeout: 30_000 })
    .toBeGreaterThan(0);
  await page.keyboard.press('2');
  await expect(page.getByTestId('save-status')).toContainText(/Saved \(version [2-9]/, {
    timeout: 10_000,
  });
  await page.getByRole('button', { name: 'Continue to export' }).click();

  await page.getByLabel('Quality').selectOption('draft');
  await page.getByRole('button', { name: 'Export video' }).click();
  const video = page.getByTestId('result-video');
  await expect(video).toBeVisible({ timeout: 180_000 });
  // Electron can decode H.264 (unlike Playwright's Chromium): the video really plays.
  await expect
    .poll(() => video.evaluate((v: HTMLVideoElement) => v.readyState), { timeout: 30_000 })
    .toBeGreaterThan(0);
});

test('diagnostic report and logs', async () => {
  await page.getByRole('link', { name: 'Settings' }).click();
  await page.getByRole('button', { name: /Copy diagnostic report/ }).click();
  await expect(page.getByText('Copied to the clipboard.')).toBeVisible();
  const report = await app.evaluate(({ clipboard }) => clipboard.readText());
  expect(report).toContain('# Multicam Studio diagnostic report');
  expect(report).toContain('Status: ready');
  expect(report).toContain('"vad_model_available"');
  const token = await page.evaluate(() => window.multicam?.apiToken ?? '');
  expect(token.length).toBeGreaterThan(10);
  expect(report).not.toContain(token);
  // No settings for the engine address in the desktop app.
  await expect(page.getByText('Engine connection')).toHaveCount(0);
});

test('quitting the app stops the engine', async () => {
  const base = await page.evaluate(() => window.multicam?.apiBase ?? '');
  await app.close();
  closed = true;
  await expect
    .poll(
      async () => {
        try {
          await fetch(`${base}/api/system/health`);
          return 'running';
        } catch {
          return 'stopped';
        }
      },
      { timeout: 20_000 },
    )
    .toBe('stopped');
});
