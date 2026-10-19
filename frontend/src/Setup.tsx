import { useState } from 'react';
import type { FormEvent } from 'react';
import type { Destination, Job, Mode, Source } from './types';
import { Banner, bytes, humanize, Icon, PageHeading } from './ui';
import { request } from './api';

type Run = (work: () => Promise<void>) => Promise<void>;

export function SourceStep({ busy, run, onSource, onDemo }: {
  busy: boolean; run: Run; onSource: (source: Source) => void; onDemo: (scenario: 'problems' | 'correct') => void;
}) {
  const [path, setPath] = useState('');
  function submit(event: FormEvent) {
    event.preventDefault();
    void run(async () => onSource(await request<Source>('/source', { path })));
  }
  return <div className="source-screen">
    <PageHeading title="Start with your Takeout." subtitle="Choose the extracted export you want to compare with Immich." />
      <form onSubmit={submit} className="setup-form source-form">
        <h2>Your source folder</h2>
        <p>Select a locally extracted Google Takeout folder. The checker reads files in place.</p>
        <label htmlFor="source-path">Extracted folder path</label>
        <div className="source-path"><Icon name="folder" size={25} /><input id="source-path" value={path} onChange={(event) => setPath(event.target.value)} autoComplete="off" required placeholder="C:\Photos\Takeout" aria-describedby="path-hint" /></div><div className="source-buttons"><button className="button secondary" type="button" disabled={busy} onClick={() => void run(async () => {
          const result = await request<{ path: string | null }>('/folder', {});
          if (result.path) setPath(result.path);
        })}><Icon name="folder" />Choose folder</button><button className="button primary" type="submit" disabled={busy || !path.trim()}>{busy ? 'Reading folder…' : 'Preview source'}<Icon name="arrow" /></button></div>
        <p id="path-hint" className="hint">Use a folder on the computer running this app. Extract ZIP files before continuing.</p>
      </form>
      <aside className="side-note"><h3>A check you can inspect</h3><p>Compare content, capture dates and album membership. Every finding includes the evidence behind it.</p><p>Your source and Immich library are read only. Nothing is uploaded, repaired or deleted.</p></aside>
    <section className="sample-section"><div><h2>Try the sample first</h2><p>A small, deterministic fixture lets you explore the full workflow without a server or credentials.</p></div><div className="button-row"><button className="button secondary" disabled={busy} onClick={() => onDemo('problems')}>Sample with problems</button><button className="button quiet" disabled={busy} onClick={() => onDemo('correct')}>Correct sample<Icon name="arrow" size={18} /></button></div></section>
  </div>;
}

export function DestinationStep({ source, busy, run, onConnect }: { source: Source | null; busy: boolean; run: Run; onConnect: (destination: Destination) => void }) {
  const [url, setUrl] = useState('');
  const [key, setKey] = useState('');
  function submit(event: FormEvent) {
    event.preventDefault();
    void run(async () => {
      const destination = await request<Destination>('/connect', { url, api_key: key });
      setKey('');
      onConnect(destination);
    });
  }
  return <>
    <PageHeading title="Connect your destination." subtitle="Give this local session read access to your Immich library." />
    {source ? <div className="scope-line"><Icon name="folder" /><strong>{source.root_name}</strong><span>{source.files.toLocaleString()} non-JSON candidates</span><span>{bytes(source.total_bytes)}</span></div> : null}
    <div className="setup-layout">
      <form onSubmit={submit} className="setup-form">
        <h2>Immich connection</h2><p>Use a dedicated API key with the read permissions in the setup guide.</p>
        <label htmlFor="server-url">Immich server URL</label><input id="server-url" type="url" value={url} onChange={(event) => setUrl(event.target.value)} required placeholder="https://photos.example.com" autoComplete="off" spellCheck={false} />
        <label htmlFor="api-key">API key</label><input id="api-key" type="password" value={key} onChange={(event) => setKey(event.target.value)} required autoComplete="off" aria-describedby="key-hint" />
        <p className="hint" id="key-hint">Held in memory for this server session. The key is excluded from saved scans and reports. Reconnect after restarting the app.</p>
        <button className="button primary" type="submit" disabled={busy || !url.trim() || !key.trim()}>{busy ? 'Checking connection…' : 'Connect to Immich'}<Icon name="arrow" /></button>
      </form>
      <aside className="side-note"><h3>Only what your key can see</h3><p>The report covers accessible assets and albums. Locked media, unavailable pages and permission failures can limit coverage.</p><p>A working connection does not prove your whole library is visible.</p></aside>
    </div>
  </>;
}

export function ScanStep({ source, destination, busy, job, mode, consent, onMode, onConsent, onStart, onCancel, onResume, onReconnect, connectionReady, demo }: {
  source: Source | null; destination: Destination | null; busy: boolean; job: Job | null; mode: Mode; consent: boolean;
  onMode: (mode: Mode) => void; onConsent: (value: boolean) => void; onStart: () => void; onCancel: () => void;
  onResume: () => void; onReconnect: () => void; connectionReady: boolean; demo: boolean;
}) {
  const running = job?.status === 'running';
  return <>
    <PageHeading title={job ? (running ? 'Checking your migration.' : 'Your scan is paused.') : 'Choose your evidence.'} subtitle={job ? 'Scan checkpoints stay on this computer so you can return to this work.' : 'Preview the scope, then choose how to compare your files.'} />
    {demo ? <Banner title="Sample workflow" tone="info">This scan uses deterministic fixture media and a local simulated destination. It does not validate a real Immich migration.</Banner> : null}
    {job ? <ScanProgress job={job} busy={busy} onCancel={onCancel} onResume={onResume} onReconnect={onReconnect} connectionReady={connectionReady} /> : <>
      <div className="preview-strip"><div><span>Source</span><strong>{source?.root_name ?? 'Selected folder'}</strong><small>{source?.files.toLocaleString() ?? '—'} non-JSON candidates · {bytes(source?.total_bytes)}</small></div><Icon name="arrow" /><div><span>Destination</span><strong>Immich {destination?.version ?? ''}</strong><small>{destination?.asset_count.toLocaleString() ?? '—'} accessible assets</small></div></div>
      {destination?.issues.length ? <Banner title="Connection coverage needs review">The destination reported {destination.issues.length} issue{destination.issues.length === 1 ? '' : 's'}. The scan will preserve these gaps in its report.</Banner> : null}
      <fieldset className="mode-options"><legend>Verification level</legend>
        <label className={`mode-option ${mode === 'checksum' ? 'chosen' : ''}`}><input type="radio" name="mode" value="checksum" checked={mode === 'checksum'} onChange={() => onMode('checksum')} /><div><strong>Server-reported checksum</strong><p>Compare compatible source hashes with Immich’s stored upload checksums. This checks historical checksum evidence; it does not download and verify the current original bytes.</p><span className="hint">Low transfer volume · version and asset provenance limitations apply</span></div></label>
        <label className={`mode-option ${mode === 'original' ? 'chosen' : ''}`}><input type="radio" name="mode" value="original" checked={mode === 'original'} onChange={() => onMode('original')} /><div><strong>Verify original bytes</strong><p>Stream destination originals and compare SHA-256 hashes. This can download the entire accessible destination collection; extra original copies are not retained.</p><span className="hint">Expected transfer: {bytes(destination?.known_bytes)} known{destination?.unknown_sizes ? ` + ${destination.unknown_sizes.toLocaleString()} assets with unknown sizes` : ''}</span></div></label>
      </fieldset>
      {mode === 'original' ? <label className="consent"><input type="checkbox" checked={consent} onChange={(event) => onConsent(event.target.checked)} /><span>I choose to download destination originals for this scan and understand the transfer volume may be larger than the known estimate.</span></label> : null}
      <div className="scan-actions"><button className="button primary" disabled={busy || (mode === 'original' && !consent)} onClick={onStart}>{busy ? 'Starting…' : 'Start read-only scan'}<Icon name="arrow" /></button><span>The source folder and destination library remain unchanged.</span></div>
    </>}
  </>;
}

function ScanProgress({ job, busy, onCancel, onResume, onReconnect, connectionReady }: { job: Job; busy: boolean; onCancel: () => void; onResume: () => void; onReconnect: () => void; connectionReady: boolean }) {
  const running = job.status === 'running';
  const entries = Object.entries(job.progress ?? {});
  return <section className="progress-section" aria-live="polite">
    <div className="progress-heading"><h2>{humanize(job.phase || job.status)}</h2><span className={running ? 'running-state' : ''}>{humanize(job.status)}</span></div>
    {running ? <div className="activity-track" role="progressbar" aria-label="Scan is running"><span /></div> : null}
    {entries.length ? <dl className="progress-details">{entries.map(([key, value]) => <div key={key}><dt>{humanize(key)}</dt><dd>{typeof value === 'number' ? value.toLocaleString() : value}</dd></div>)}</dl> : <p>Preparing the source manifest and destination inventory…</p>}
    {job.error ? <Banner title="Scan could not complete" tone="error">{job.error}</Banner> : null}
    {!running ? <p>The saved checkpoint remains available. Resume checks the source and destination again before producing a report.</p> : null}
    <div className="button-row">{running ? <button className="button secondary" disabled={busy} onClick={onCancel}>Cancel scan</button> : connectionReady || job.demo ? <button className="button primary" disabled={busy} onClick={onResume}>Resume scan<Icon name="arrow" /></button> : <button className="button primary" disabled={busy} onClick={onReconnect}>Reconnect to resume<Icon name="arrow" /></button>}</div>
  </section>;
}

export function ScanHistory({ jobs, onOpen, busy }: { jobs: Job[]; onOpen: (job: Job) => void; busy: boolean }) {
  if (!jobs.length) return null;
  return <section className="scan-history"><h2>Previous scans</h2><p>Manifests and reports stay on this computer. Reports can contain sensitive paths and asset identifiers.</p><div className="history-list">{jobs.map((job) => <button key={job.id} className="history-item" disabled={busy} onClick={() => onOpen(job)}><span><strong>{job.demo ? 'Sample scan' : 'Library scan'}</strong><small>{job.id.slice(0, 8)} · {job.mode === 'original' ? 'Original bytes' : 'Server checksum'}{job.created_at ? ` · ${new Date(job.created_at).toLocaleString()}` : ''}</small></span><span className="history-status">{humanize(job.status)}<Icon name="arrow" size={18} /></span></button>)}</div></section>;
}
