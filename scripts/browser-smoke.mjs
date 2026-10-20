// Run with the app already listening; URL is its current private launch link.
// node scripts/browser-smoke.mjs URL ARTIFACT_DIR
// Optional PMC_FIXTURE_SOURCE/URL/KEY exercise a local protocol fixture, not real Immich.
import assert from 'node:assert/strict';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { createRequire } from 'node:module';
const require = createRequire(new URL('../frontend/package.json', import.meta.url));
const { chromium } = require('playwright');
const url = process.argv[2] ?? 'http://127.0.0.1:8765';
const publicUrl = new URL(url);
assert.match(publicUrl.hash, /^#session=[A-Za-z0-9_-]{43}$/, 'Pass the current private link printed by the app terminal.');
publicUrl.hash = '';
const output = path.resolve(process.argv[3] ?? 'browser-evidence');
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1505, height: 1045 }, acceptDownloads: true });
const errors = [], requests = [], checks = [];
page.on('pageerror', e => errors.push(e.message));
page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
page.on('request', r => requests.push({ method: r.method(), url: r.url() }));
const check = (name, detail = true) => checks.push({ name, passed: true, detail });

try {
  await page.goto(url);
  await page.waitForFunction(() => location.hash === '');
  assert.equal(await page.title(), 'Photo Migration Checker');
  await page.getByRole('heading', { name: 'Start with your Takeout.' }).waitFor();
  assert.equal((await page.request.get(new URL('/api/bootstrap', publicUrl).href)).status(), 403);
  check('private launch fragment removed; unrelated bootstrap cannot obtain a token');
  check('page identity and meaningful source screen');
  await page.screenshot({ path: path.join(output, 'source-desktop.png'), fullPage: true });

  if (process.env.PMC_FIXTURE_SOURCE) {
    await page.getByLabel('Extracted folder path').fill(process.env.PMC_FIXTURE_SOURCE);
    await page.getByRole('button', { name: 'Preview source', exact: true }).click();
    await page.getByRole('heading', { name: 'Connect your destination.' }).waitFor();
    await page.getByLabel('Immich server URL').fill(process.env.PMC_FIXTURE_URL);
    await page.getByLabel('API key', { exact: true }).fill(process.env.PMC_FIXTURE_KEY);
    await page.getByRole('button', { name: 'Connect to Immich', exact: true }).click();
    await page.getByRole('heading', { name: 'Choose your evidence.' }).waitFor();
    assert.equal(await page.locator('#api-key').count(), 0);
    check('source preview and real HTTP protocol-fixture connection');
    await page.getByRole('radio', { name: /Verify original bytes/ }).check();
    await page.getByRole('checkbox').check();
    await page.getByRole('button', { name: 'Start read-only scan', exact: true }).click();
    await page.getByRole('button', { name: 'Cancel scan', exact: true }).click();
    await page.getByRole('button', { name: 'Resume scan', exact: true }).waitFor({ timeout: 30000 });
    await page.screenshot({ path: path.join(output, 'cancelled.png'), fullPage: true });
    check('cooperative cancellation reaches a resumable stopped state');
    await page.getByRole('button', { name: 'Resume scan', exact: true }).click();
    await page.getByRole('heading', { name: 'Your migration, checked.' }).waitFor({ timeout: 30000 });
    await page.getByText('Scope checked — review the evidence', { exact: true }).waitFor();
    check('resume finishes original-byte verification through HTTP transport');
    await page.getByRole('button', { name: 'Start another check', exact: true }).click();
  }

  await page.getByRole('button', { name: 'Sample with problems', exact: true }).click();
  await page.getByRole('radio', { name: /Verify original bytes/ }).check();
  const start = page.getByRole('button', { name: 'Start read-only scan', exact: true });
  assert.equal(await start.isEnabled(), false);
  await page.getByRole('checkbox').check();
  await start.click();
  await page.getByRole('heading', { name: 'Your migration, checked.' }).waitFor({ timeout: 30000 });
  await page.getByText('Incomplete coverage', { exact: true }).waitFor();
  check('explicit download consent and honest incomplete sample results');

  const search = page.getByRole('searchbox');
  await search.fill('portrait-edited');
  await page.getByRole('button', { name: 'Family/portrait-edited.png', exact: true }).waitFor();
  assert.equal(await page.locator('tbody tr').count(), 1);
  await page.getByRole('button', { name: 'Family/portrait-edited.png', exact: true }).click();
  await page.getByRole('heading', { name: 'portrait-edited.png', exact: true }).waitFor();
  await page.getByText('Source SHA-256', { exact: true }).waitFor();
  await page.screenshot({ path: path.join(output, 'evidence-desktop.png'), fullPage: true });
  check('path search and selected evidence inspector');
  await search.fill('no-such-file');
  await page.getByText('No findings match these filters.', { exact: false }).waitFor();
  await search.fill('');
  await page.getByLabel('Finding category').selectOption('metadata');
  await page.waitForFunction(() => document.querySelectorAll('tbody tr').length > 0);
  check('empty search state and metadata category filter');
  await page.getByLabel('Finding category').selectOption('all');
  await page.screenshot({ path: path.join(output, 'results-desktop.png'), fullPage: true });
  for (const format of ['JSON', 'HTML']) {
    const pending = page.waitForEvent('download');
    await page.getByRole('button', { name: `Export ${format}`, exact: true }).click();
    const download = await pending;
    const dest = path.join(output, `sample-report.${format.toLowerCase()}`);
    await download.saveAs(dest);
    const contents = await readFile(dest, 'utf8');
    assert.equal(contents.includes(process.env.PMC_FIXTURE_KEY ?? 'UNUSED_PRIVATE_TEST_SENTINEL'), false);
    if (format === 'JSON') {
      const report = JSON.parse(contents);
      assert.equal(report.demo, true);
      assert.equal(report.summary.coverage_complete, false);
      assert.equal(report.findings.some(f => f.path === 'Family/portrait-edited.png' && f.status === 'missing'), true);
    } else {
      assert.equal(contents.includes('not a real Immich validation'), true);
      assert.equal(contents.includes('<script'), false);
    }
  }
  check('downloaded JSON and offline HTML contain expected findings and no key');
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: path.join(output, 'results-mobile.png'), fullPage: true });
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth);
  assert.equal(overflow, false, 'Page overflows mobile viewport');
  check('390px mobile viewport without page overflow');
  await page.setViewportSize({ width: 1505, height: 1045 });
  await page.reload();
  await page.getByRole('heading', { name: 'Previous scans', exact: true }).waitFor();
  await page.locator('.history-item').first().click();
  await page.getByRole('heading', { name: 'Your migration, checked.' }).waitFor();
  check('saved report remains available after browser reload');
  assert.equal(errors.length, 0, JSON.stringify(errors));
  assert.equal(requests.every(r => new URL(r.url).origin === new URL(url).origin), true, 'Unexpected external browser request');
  check('no console errors, runtime overlays or external browser requests');
  await writeFile(path.join(output, 'browser-evidence.json'), JSON.stringify({
    browser: await browser.version(), url: publicUrl.href, viewports: ['1505x1045', '390x844'],
    browser_plugin: 'Browser skill unavailable; local Playwright Chromium used',
    protocol_fixture: Boolean(process.env.PMC_FIXTURE_SOURCE), checks, errors,
  }, null, 2));
  console.log(`${checks.length} browser checks passed; evidence: ${output}`);
} finally {
  await browser.close();
}
