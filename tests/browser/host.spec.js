const { test, expect } = require('@playwright/test');
const fs = require('fs');
const path = require('path');
const env = Object.fromEntries(fs.readFileSync(path.resolve(__dirname,
  '../../deployment/independent/.state/lab.env'), 'utf8').trim().split('\n').map(line => {
  const split = line.indexOf('='); return [line.slice(0, split), line.slice(split + 1)];
}));
test.setTimeout(120000);

test.beforeEach(async ({ page }) => {
  await page.goto('/login/');
  await page.locator('#username').fill('lab-admin');
  await page.locator('#password').fill(env.LAB_ADMIN_PASSWORD);
  await page.locator('button[type=submit]').click();
  await page.waitForURL(url => !url.pathname.startsWith('/login'));
});

test('supported loader evaluates the artifact and exposes only the documented APIs', async ({ page }) => {
  const remote = page.waitForResponse(r => r.url().includes('/api/v1/extensions/jalali-lab/registry-probe/remoteEntry.')
    && r.status() === 200);
  await page.goto('/superset/welcome/');
  await remote;
  await page.waitForFunction(() => !!window.superset?.extensions);
  const api = await page.evaluate(() => Object.keys(window.superset.extensions).sort());
  expect(api).toEqual(['getAllExtensions', 'getExtension']);
});

test('native Dashboard consumer integration gate', async ({ page }) => {
  const response = page.waitForResponse(r => r.url().includes('/api/v1/chart/data') && r.request().method() === 'POST');
  await page.goto('/superset/dashboard/jalali-acceptance/');
  const data = await (await response).json();
  expect(data.result[0].data[0].total).toBe(111110);
  await expect(page.getByText('Calendar range', { exact: true })).toBeVisible();
  // Actual host consumer is required; a panel in SQL Lab cannot satisfy this.
  const replacement = page.locator('[data-test=jalali-probe-date-control]');
  if (process.env.REQUIRE_NATIVE_JALALI === '1') {
    await expect(replacement).toBeVisible({ timeout: 5000 });
  } else {
    await expect(replacement).toHaveCount(0);
    await expect(page.getByText('No filter', { exact: true }).first()).toBeVisible();
  }
});
