import { expect, test } from '@playwright/test';
import path from 'node:path';

import { E2E_MEDIA_DIR } from './paths';

const media = (name: string) => path.join(E2E_MEDIA_DIR, name);

test('create a project, auto edit it and export a video', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByText('Engine ready')).toBeVisible();

  // 1. New project
  await page.getByRole('link', { name: 'New project' }).first().click();
  const name = `E2E ${Date.now()}`;
  await page.getByLabel('Name').fill(name);
  await page.getByRole('button', { name: 'Create project' }).click();
  await expect(page.getByRole('heading', { name })).toBeVisible();

  // 2. Cameras (no desktop app here, so paths are typed)
  await page
    .getByLabel('File paths (one per line)')
    .fill([media('cam1.mp4'), media('cam2.mp4'), media('wide.mp4')].join('\n'));
  await page.getByRole('button', { name: 'Add clips' }).click();
  const rows = page.getByTestId('clip-row');
  await expect(rows).toHaveCount(3);
  await expect(rows.first()).toContainText('Reference');

  const wideRow = rows.filter({ hasText: 'wide.mp4' });
  await wideRow.getByLabel('Camera shows').selectOption('wide');
  await expect(wideRow.getByLabel('Speaker name')).toHaveCount(0);
  const hostLabel = rows.filter({ hasText: 'cam1.mp4' }).getByLabel('Speaker name');
  await hostLabel.fill('Host');
  await hostLabel.press('Enter');
  await page.getByRole('button', { name: 'Continue', exact: true }).click();

  // 3. Auto edit (loudness detection: fast and needs no model file)
  await page.getByLabel('Speech detection').selectOption('energy');
  await page.getByRole('button', { name: 'Start auto edit' }).click();
  await expect(page.getByTestId('cutlist-summary')).toBeVisible({ timeout: 180_000 });
  const syncTable = page.getByRole('table', { name: 'Sync results' });
  await expect(syncTable).toContainText('reference');
  await expect(syncTable).toContainText('+1000'); // cam2 started 1 s early
  await expect(page.getByText('Speaking time')).toBeVisible();

  // Re-cut with another style: a new cutlist version, no re-analysis
  const recut = page.waitForResponse(
    (r) => r.request().method() === 'POST' && r.url().endsWith('/jobs') && r.status() === 202,
  );
  await page.getByRole('button', { name: 'Dynamic' }).click();
  await recut;
  await expect(page.getByTestId('job-progress')).toHaveCount(0, { timeout: 60_000 });

  // 4. Export a draft
  await page.getByRole('button', { name: 'Continue to export' }).click();
  await page.getByLabel('Quality').selectOption('draft');
  await page.getByRole('button', { name: 'Export video' }).click();
  const video = page.getByTestId('result-video');
  await expect(video).toBeVisible({ timeout: 180_000 });
  // Playwright's Chromium has no H.264 decoder (the desktop app's does), so check
  // that the player's source is a real MP4 instead of waiting for playback.
  const src = await video.getAttribute('src');
  const head = await page.request.get(src!, { headers: { Range: 'bytes=0-11' } });
  expect(head.status()).toBe(206);
  expect((await head.body()).subarray(4, 8).toString()).toBe('ftyp');
  await expect(page.getByRole('list', { name: 'Exports' }).getByRole('listitem')).toHaveCount(1);

  // Back on the dashboard the project shows as edited
  await page.getByRole('link', { name: 'All projects' }).click();
  const card = page.getByTestId('project-card').filter({ hasText: name });
  await expect(card).toContainText('3 cameras');
  await expect(card).toContainText('Edited');
});

test('shows a clear error for a file that does not exist', async ({ page }) => {
  await page.goto('/new/');
  await page.getByLabel('Name').fill('Missing file');
  await page.getByRole('button', { name: 'Create project' }).click();
  await page.getByLabel('File paths (one per line)').fill('/definitely/not/here.mp4');
  await page.getByRole('button', { name: 'Add clips' }).click();
  await expect(page.getByText('Could not add a file')).toBeVisible();
  await expect(page.getByText(/file not found/)).toBeVisible();
});
