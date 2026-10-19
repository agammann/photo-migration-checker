// Live Immich only. Required: PMC_REAL_STATE and PMC_REAL_PYTHON (or PMCPYTHON).
// PMC_REAL_SCENARIO=problems|correct; the problems library supports lifecycle checks.
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { createHash } from 'node:crypto';
import { createReadStream } from 'node:fs';
import { mkdir, readdir, readFile, stat, writeFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const project = fileURLToPath(new URL('../', import.meta.url));
const require = createRequire(new URL('../frontend/package.json', import.meta.url));
const { chromium } = require('playwright');
const scenario = process.env.PMC_REAL_SCENARIO ?? 'problems';
assert(['correct', 'problems'].includes(scenario), 'Choose correct or problems live scenario.');
assert(process.env.PMC_REAL_STATE, 'PMC_REAL_STATE must reference the private live test state.');
const privateState = JSON.parse(await readFile(process.env.PMC_REAL_STATE, 'utf8'));
const selected = privateState.scenarios?.[scenario];
assert(selected?.key && selected?.source && selected?.expected, 'Private scenario state is incomplete.');
const connectionUrl = process.env.PMC_REAL_URL ?? privateState.url;
const key = selected.key;
const source = path.resolve(selected.source);
const expected = JSON.parse(await readFile(selected.expected, 'utf8'));
const python = process.env.PMC_REAL_PYTHON ?? process.env.PMCPYTHON;
assert(python, 'Provide PMC_REAL_PYTHON so this runner owns its isolated preview lifecycle.');
const appCwd = process.env.PMC_REAL_APP_CWD ? path.resolve(process.env.PMC_REAL_APP_CWD) : project;
const preview = new URL(process.env.PMC_PREVIEW_URL ?? 'http://127.0.0.1:8767');
assert(preview.protocol === 'http:' && ['127.0.0.1', 'localhost'].includes(preview.hostname), 'Preview must be an isolated loopback HTTP app.');
assert(preview.port && !['8765', '8766'].includes(preview.port), 'Use a dedicated preview port, such as 8767.');
const output = path.resolve(process.env.PMC_REAL_BROWSER_OUTPUT ?? path.join(project, '../../work/real-immich-browser', scenario));
const screenshots = path.join(project, 'docs/screenshots/real-immich');
const dataDir = path.resolve(process.env.PMC_REAL_DATA_DIR ?? path.join(output, 'pmc-state'));
const lifecycleDelay = Number(process.env.PMC_REAL_LIFECYCLE_DELAY_MS ?? 2000);
assert(Number.isFinite(lifecycleDelay) && lifecycleDelay >= 0 && lifecycleDelay <= 30000, 'Lifecycle delay must be between 0 and 30000 milliseconds.');
const observerLedger = process.env.PMC_REAL_OBSERVER_LEDGER;
await Promise.all([mkdir(output, { recursive: true }), mkdir(screenshots, { recursive: true })]);

const checks = [], errors = [], expectedNetworkEvents = [], requestOrigins = new Set();
let credentialInRequestUrl = false;
let server, browser, page, restarting = false, originalTransferBytes = null;
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const redact = value => String(value).replaceAll(key, '[redacted]').replaceAll(source, '[source folder]').replaceAll(process.env.PMC_REAL_STATE, '[private state]');
const check = (name, detail = true) => checks.push({ name, passed: true, detail });

async function reachable() {
  try { return (await fetch(new URL('/api/bootstrap', preview), { signal: AbortSignal.timeout(500) })).ok; }
  catch { return false; }
}

async function startPreview() {
  assert.equal(await reachable(), false, 'Dedicated preview port is occupied; no existing process was stopped.');
  const childEnv = { ...process.env };
  for (const name of Object.keys(childEnv)) if (name.startsWith('PMC_REAL_') || name === 'PMCPYTHON') delete childEnv[name];
  if (process.env.PMC_REAL_APP_CWD) delete childEnv.PYTHONPATH;
  server = spawn(python, ['-m', 'pmc', '--port', preview.port, '--data-dir', dataDir], {
    cwd: appCwd, env: childEnv, stdio: 'ignore', windowsHide: true,
  });
  let spawnError;
  server.on('error', error => { spawnError = error; });
  const deadline = Date.now() + 30000;
  while (!await reachable()) {
    if (spawnError || server.exitCode !== null) throw new Error('Owned preview process could not start. Check the Python environment.');
    assert(Date.now() < deadline, 'Owned preview did not become ready within 30 seconds.');
    await sleep(150);
  }
}

async function stopPreview() {
  const owned = server;
  if (!owned || owned.exitCode !== null) return;
  await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('Owned preview process did not stop.')), 10000);
    owned.once('exit', () => { clearTimeout(timer); resolve(); });
    owned.kill();
  });
  server = undefined;
}

async function api(route) {
  return page.evaluate(async route => {
    const { token } = await (await fetch('/api/bootstrap', { cache: 'no-store' })).json();
    const response = await fetch(`/api${route}`, { headers: { 'X-PMC-Token': token }, cache: 'no-store' });
    if (!response.ok) throw new Error(`Local status request failed (${response.status}).`);
    return response.json();
  }, route);
}

async function sourceSnapshot() {
  const files = [];
  async function visit(directory) {
    for (const entry of await readdir(directory, { withFileTypes: true })) {
      const filename = path.join(directory, entry.name);
      if (entry.isDirectory()) await visit(filename);
      else if (entry.isFile()) {
        const metadata = await stat(filename);
        const hash = createHash('sha256');
        for await (const chunk of createReadStream(filename)) hash.update(chunk);
        files.push({ path: path.relative(source, filename).split(path.sep).join('/'), size: metadata.size, mtime: metadata.mtimeMs, sha256: hash.digest('hex') });
      } else throw new Error('Controlled live browser source unexpectedly contains a non-regular entry.');
    }
  }
  await visit(source);
  files.sort((a, b) => a.path.localeCompare(b.path));
  return { count: files.length, digest: createHash('sha256').update(JSON.stringify(files)).digest('hex') };
}

async function capture(name, target = page) {
  await target.screenshot({ path: path.join(screenshots, `${scenario}-${name}.png`), fullPage: true });
}

async function connectSource() {
  const startAnother = page.getByRole('button', { name: 'Start another check', exact: true });
  if (await startAnother.count()) await startAnother.click();
  else await page.goto(preview.href);
  await page.getByRole('heading', { name: 'Start with your Takeout.', exact: true }).waitFor();
  await page.getByLabel('Extracted folder path').fill(source);
  await page.getByRole('button', { name: 'Preview source', exact: true }).click();
  await page.getByRole('heading', { name: 'Connect your destination.', exact: true }).waitFor();
  await connectDestination();
}

async function connectDestination() {
  await page.getByLabel('Immich server URL').fill(connectionUrl);
  await page.getByLabel('API key', { exact: true }).fill(key);
  await page.getByRole('button', { name: 'Connect to Immich', exact: true }).click();
  await page.getByRole('heading', { name: /Choose your evidence\.|Your scan is paused\./ }).waitFor({ timeout: 60000 });
  assert.equal(await page.locator('#api-key').count(), 0, 'Connection key field must be removed after connecting.');
  assert.deepEqual(await page.evaluate(() => [localStorage.length, sessionStorage.length]), [0, 0], 'Credentials or scan state were persisted in browser storage.');
}

async function startScan(mode) {
  await page.getByRole('radio', { name: mode === 'original' ? /Verify original bytes/ : /Server-reported checksum/ }).check();
  const button = page.getByRole('button', { name: 'Start read-only scan', exact: true });
  if (mode === 'original') {
    assert.equal(await button.isEnabled(), false, 'Original downloads must require explicit consent.');
    await page.getByText('Expected transfer:', { exact: false }).waitFor();
    await page.getByRole('checkbox').check();
  }
  const observerStartIndex = observerLedger ? JSON.parse(await readFile(observerLedger, 'utf8')).length : null;
  const pending = page.waitForResponse(response => new URL(response.url()).pathname === '/api/scans' && response.request().method() === 'POST');
  await button.click();
  const response = await pending;
  assert.equal(response.ok(), true, 'Live scan start failed.');
  const job = await response.json();
  assert.equal(job.demo, false, 'Live browser runner must never use the sample destination.');
  return { ...job, observerStartIndex };
}

async function waitForOriginalStream(job) {
  if (!observerLedger) {
    await sleep(lifecycleDelay);
    return { observed: false, policy: 'Timed delay only; original stream activity was not independently observed.' };
  }
  const deadline = Date.now() + 45000;
  while (Date.now() < deadline) {
    const ledger = JSON.parse(await readFile(observerLedger, 'utf8'));
    const offset = ledger.slice(job.observerStartIndex).findIndex(record => record.path?.endsWith('/original') && !record.complete && record.bytes >= 1024 * 1024);
    if (offset >= 0) {
      const index = job.observerStartIndex + offset;
      const observed = ledger[index];
      assert.equal(observed.allowed_read, true);
      assert.equal(observed.method, 'GET');
      assert.equal(observed.status, 200);
      return { observed: true, ledger_index: index, method: observed.method, path: observed.path, bytes: observed.bytes, status: observed.status };
    }
    assert.equal((await api(`/scans/${job.id}`)).status, 'running', 'Live job finished before an active original stream could be observed.');
    await sleep(100);
  }
  throw new Error('No active destination original stream observed within 45 seconds.');
}

function verifyReport(report, mode) {
  assert.equal(report.demo, false);
  assert.equal(report.mode, mode);
  assert.equal(report.immich_version, expected.immich_version);
  const oracle = expected[mode];
  assert(oracle?.summary && Array.isArray(oracle.findings), 'Live expected manifest must include summary and findings for both modes.');
  for (const [name, value] of Object.entries(oracle.summary)) assert.deepEqual(report.summary[name], value, `Unexpected live ${mode} summary field: ${name}`);
  assert.equal(report.findings.length, oracle.findings.length, `Unexpected live ${mode} finding count.`);
  const remaining = [...report.findings];
  for (const pattern of oracle.findings) {
    const index = remaining.findIndex(finding => Object.entries(pattern).every(([name, value]) => JSON.stringify(finding[name]) === JSON.stringify(value)));
    assert(index >= 0, `Expected live ${mode} finding absent: ${pattern.kind ?? ''} ${pattern.status ?? ''} ${pattern.path ?? ''}`);
    remaining.splice(index, 1);
  }
  const serialized = JSON.stringify(report);
  assert.equal(serialized.includes(key), false, 'Report contains a credential.');
  assert.equal(serialized.includes(source), false, 'Report contains the absolute source root.');
}

async function finished(job, mode) {
  await page.getByRole('heading', { name: 'Your migration, checked.', exact: true }).waitFor({ timeout: 180000 });
  const saved = await api(`/scans/${encodeURIComponent(job.id)}`);
  assert.equal(saved.status, 'completed');
  verifyReport(saved.report, mode);
  return saved;
}

async function inspectAndExport(job, mode) {
  const report = job.report;
  const finding = report.findings.find(item => item.kind === 'content' && ['missing', 'mismatched'].includes(item.status)) ?? report.findings.find(item => item.kind === 'content');
  assert(finding?.source_sha256, 'Controlled live fixture should provide inspectable source byte evidence.');
  const search = page.getByRole('searchbox');
  await search.fill(finding.path);
  await page.getByRole('button', { name: finding.path, exact: true }).first().click();
  await page.getByRole('heading', { name: finding.path.split('/').pop(), exact: true }).waitFor();
  await page.getByText(finding.source_sha256, { exact: true }).first().waitFor();
  await capture(`${mode}-evidence-desktop`);
  await search.fill('no-controlled-file-has-this-name');
  await page.getByText('No findings match these filters.', { exact: false }).waitFor();
  await search.fill('');
  await page.getByLabel('Finding category').selectOption('metadata');
  const metadataCount = report.findings.filter(item => ['metadata', 'source_metadata'].includes(item.kind)).length;
  if (metadataCount) await page.locator('tbody tr').first().waitFor();
  else await page.getByText('No findings match these filters.', { exact: false }).waitFor();
  await page.getByLabel('Finding category').selectOption('all');
  await capture(`${mode}-results-desktop`);
  for (const format of ['json', 'html']) {
    const pending = page.waitForEvent('download');
    await page.getByRole('button', { name: `Export ${format.toUpperCase()}`, exact: true }).click();
    const download = await pending;
    const filename = path.join(output, `${scenario}-${mode}-report.${format}`);
    await download.saveAs(filename);
    const text = await readFile(filename, 'utf8');
    assert.equal(text.includes(key), false, 'Export contains a credential.');
    assert.equal(text.includes(source), false, 'Export contains the absolute source root.');
    if (format === 'json') assert.deepEqual(JSON.parse(text), report);
    else {
      assert.equal(/<script[\s>]/i.test(text), false);
      assert.equal(text.includes('This is not a real Immich validation.'), false);
      const offline = await browser.newPage({ viewport: { width: 1505, height: 1045 } });
      const remote = [];
      offline.on('request', request => { if (['http:', 'https:'].includes(new URL(request.url()).protocol)) remote.push(request.url()); });
      await offline.goto(pathToFileURL(filename).href);
      await offline.getByRole('heading', { name: 'Photo Migration Checker', exact: true }).waitFor();
      assert.equal(await offline.locator('tbody tr').count(), report.findings.length);
      const firstEvidence = offline.locator('tbody details').first();
      await firstEvidence.locator('summary').click();
      assert.equal(typeof JSON.parse(await firstEvidence.locator('pre').textContent()).source_sha256, 'string', 'Offline evidence disclosure should retain the source hash.');
      assert.equal(remote.length, 0, 'Offline HTML requested a remote resource.');
      await capture(`${mode}-html-export`, offline);
      await offline.close();
    }
  }
  await page.setViewportSize({ width: 390, height: 844 });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth), 390, 'Live results page overflows mobile viewport.');
  await capture(`${mode}-results-mobile`);
  await page.setViewportSize({ width: 1505, height: 1045 });
  check(`${mode}: actual findings search, category filter, source hash inspector, parsed JSON, offline HTML and mobile rendering`, { source_files: report.summary.source_files, matched: report.summary.matched, attention: report.summary.attention, coverage_complete: report.summary.coverage_complete, findings: report.findings.length });
}

async function reopen(job) {
  await page.reload();
  await page.locator('.history-item').filter({ hasText: job.id.slice(0, 8) }).click();
  await page.getByRole('heading', { name: 'Your migration, checked.', exact: true }).waitFor();
  assert.deepEqual((await api(`/scans/${job.id}`)).report, job.report);
}

try {
  const before = await sourceSnapshot();
  await startPreview();
  browser = await chromium.launch({ headless: true });
  page = await browser.newPage({ viewport: { width: 1505, height: 1045 }, acceptDownloads: true });
  page.on('pageerror', error => errors.push(redact(error.message)));
  page.on('console', message => {
    if (message.type() !== 'error') return;
    if (restarting && /net::ERR_|Failed to fetch|NetworkError/.test(message.text())) expectedNetworkEvents.push(redact(message.text()));
    else errors.push(redact(message.text()));
  });
  page.on('request', request => {
    const address = new URL(request.url());
    requestOrigins.add(address.origin);
    if (request.url().includes(key)) credentialInRequestUrl = true;
  });
  await page.goto(preview.href);
  await page.getByRole('heading', { name: 'Start with your Takeout.', exact: true }).waitFor();
  await capture('source-desktop');
  for (const mode of ['checksum', 'original']) {
    await connectSource();
    await capture(`${mode}-scope-desktop`);
    const job = await finished(await startScan(mode), mode);
    if (mode === 'original') {
      originalTransferBytes = job.report.bytes_transferred;
      assert(Number.isFinite(originalTransferBytes) && originalTransferBytes > 0, 'Live original scan must record actual original bytes.');
    } else assert.equal(job.report.bytes_transferred, 0, 'Checksum mode should not transfer destination original bytes.');
    check(`${mode}: local folder → scoped real Immich connection → completed live report`, { immich_version: job.report.immich_version, destination_assets: job.report.summary.destination_assets, bytes_transferred: job.report.bytes_transferred });
    await inspectAndExport(job, mode);
    await reopen(job);
    check(`${mode}: saved live report survives browser reload`);
  }

  if (scenario === 'problems') {
    await connectSource();
    const cancelled = await startScan('original');
    const cancelStream = await waitForOriginalStream(cancelled);
    const beforeCancel = await api(`/scans/${cancelled.id}`);
    assert.equal(beforeCancel.status, 'running', 'Controlled live scan ended before cancellation; use a larger original or a transparent rate-limiting observer.');
    await page.getByRole('button', { name: 'Cancel scan', exact: true }).click();
    await page.getByRole('button', { name: 'Resume scan', exact: true }).waitFor({ timeout: 30000 });
    const stopped = await api(`/scans/${cancelled.id}`);
    assert.equal(stopped.status, 'cancelled');
    assert.equal(stopped.report, null);
    await capture('cancelled');
    await page.getByRole('button', { name: 'Resume scan', exact: true }).click();
    const resumed = await finished(cancelled, 'original');
    assert.equal(resumed.report.bytes_transferred, originalTransferBytes, 'Resume must freshly transfer the full original inventory.');
    check('actual UI cancellation produces no report; resume recomputes and completes against real Immich', { active_original_stream: cancelStream, before_cancel_phase: beforeCancel.phase, before_cancel_progress: beforeCancel.progress, stopped_phase: stopped.phase, stopped_progress: stopped.progress, resumed_bytes_transferred: resumed.report.bytes_transferred });

    await connectSource();
    const interrupted = await startScan('original');
    assert.equal(interrupted.status, 'running', 'The lifecycle test needs an active live scan.');
    const interruptedStream = await waitForOriginalStream(interrupted);
    const beforeInterruption = await api(`/scans/${interrupted.id}`);
    assert.equal(beforeInterruption.status, 'running', 'Controlled live scan ended before process interruption.');
    restarting = true;
    await stopPreview();
    await startPreview();
    await page.reload();
    restarting = false;
    const persisted = await api(`/scans/${interrupted.id}`);
    assert.equal(persisted.status, 'interrupted', 'Process interruption must remain explicit after restart.');
    assert.equal(persisted.report, null);
    await page.locator('.history-item').filter({ hasText: interrupted.id.slice(0, 8) }).click();
    await page.getByRole('button', { name: 'Reconnect to resume', exact: true }).waitFor();
    await capture('interrupted-after-restart');
    await page.getByRole('button', { name: 'Reconnect to resume', exact: true }).click();
    await connectDestination();
    await page.getByRole('button', { name: 'Resume scan', exact: true }).click();
    const recovered = await finished(interrupted, 'original');
    assert.equal(recovered.report.bytes_transferred, originalTransferBytes, 'Recovery must freshly transfer the full original inventory.');
    await capture('resumed-after-restart');
    check('owned preview process restart preserves interrupted checkpoint, requires key reconnection and resumes live original verification', { active_original_stream: interruptedStream, before_interruption_phase: beforeInterruption.phase, before_interruption_progress: beforeInterruption.progress, interrupted_progress: persisted.progress, recovered_bytes_transferred: recovered.report.bytes_transferred });
  }
  assert.deepEqual(await sourceSnapshot(), before, 'Controlled source files changed during the browser workflows.');
  check('all source bytes, sizes and modification times unchanged', { files: before.count, snapshot_sha256: before.digest });
  assert.deepEqual([...requestOrigins], [preview.origin], 'Unexpected external browser request.');
  assert.equal(credentialInRequestUrl, false, 'Credential appeared in a browser request URL.');
  assert.equal(errors.length, 0, `Browser errors: ${JSON.stringify(errors)}`);
  check('no browser-storage persistence, credential URLs, external browser requests or unexpected console/page errors');
  const evidence = { scenario, destination: 'Disposable Docker Immich', immich_version: expected.immich_version, browser: await browser.version(), viewports: ['1505x1045', '390x844'], checks, errors, expected_restart_network_events: expectedNetworkEvents, limitations: ['Controlled synthetic media and disposable users; no permissioned real Takeout sample was used.'] };
  await writeFile(path.join(output, 'browser-real-evidence.json'), JSON.stringify(evidence, null, 2));
  console.log(`Live ${scenario}: ${checks.length} browser checks passed. Immich ${expected.immich_version}.`);
} catch (error) {
  await writeFile(path.join(output, 'browser-real-failure.json'), JSON.stringify({ scenario, checks, error: redact(error instanceof Error ? error.message : error), errors }, null, 2));
  console.error(redact(error instanceof Error ? error.message : error));
  process.exitCode = 1;
} finally {
  if (browser) await browser.close();
  await stopPreview();
}
