import { useCallback, useEffect, useState } from 'react';
import { exportReport, request } from './api';
import { Results } from './Results';
import { DestinationStep, ScanHistory, ScanStep, SourceStep } from './Setup';
import type { Destination, Job, Mode, Report, Source, Step } from './types';

const steps = ['Source', 'Destination', 'Scan', 'Results'];

export default function App() {
  const [step, setStep] = useState<Step>(0);
  const [source, setSource] = useState<Source | null>(null);
  const [destination, setDestination] = useState<Destination | null>(null);
  const [sourceId, setSourceId] = useState<string | null>(null);
  const [connectionId, setConnectionId] = useState<string | null>(null);
  const [mode, setMode] = useState<Mode>('checksum');
  const [consent, setConsent] = useState(false);
  const [job, setJob] = useState<Job | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [demo, setDemo] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [resuming, setResuming] = useState(false);

  const run = useCallback(async (work: () => Promise<void>) => {
    setBusy(true);
    setError('');
    try { await work(); } catch (caught) { setError(caught instanceof Error ? caught.message : 'The request could not complete. Try again.'); }
    finally { setBusy(false); }
  }, []);

  const acceptJob = useCallback((updated: Job) => {
    setJob(updated);
    setJobs((previous) => [updated, ...previous.filter((item) => item.id !== updated.id)]);
    setDemo(updated.demo);
    setMode(updated.mode);
    setStep(updated.report ? 3 : 2);
  }, []);

  useEffect(() => {
    document.querySelector<HTMLHeadingElement>('h1')?.focus({ preventScroll: true });
    window.scrollTo({ top: 0, behavior: 'instant' });
  }, [step]);

  useEffect(() => {
    let live = true;
    void request<Job[] | { scans: Job[] }>('/scans').then((data) => { if (live) setJobs(Array.isArray(data) ? data : data.scans); }).catch((caught: unknown) => {
      if (live) setError(caught instanceof Error ? caught.message : 'Could not read saved scans.');
    });
    return () => { live = false; };
  }, []);

  useEffect(() => {
    if (job?.status !== 'running') return;
    const id = job.id;
    let live = true;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const updated = await request<Job>(`/scans/${encodeURIComponent(id)}`);
        if (live) { acceptJob(updated); setError(''); }
        if (live && updated.status === 'running') timer = setTimeout(() => void poll(), 700);
      } catch (caught) {
        if (live) {
          setError(caught instanceof Error ? caught.message : 'Connection interrupted. Scan checkpoints are saved locally.');
          timer = setTimeout(() => void poll(), 2500);
        }
      }
    }
    timer = setTimeout(() => void poll(), 350);
    return () => { live = false; clearTimeout(timer); };
  }, [job?.id, job?.status, acceptJob]);

  function onSource(selected: Source) {
    setSource(selected); setSourceId(selected.source_id ?? null); setDemo(false); setJob(null); setResuming(false); setMode('checksum'); setConsent(false); setStep(1);
  }
  function onConnect(connected: Destination) {
    setDestination(connected); setConnectionId(connected.connection_id ?? null); setStep(2);
    if (!resuming) setJob(null);
    setResuming(false);
  }
  function onDemo(scenario: 'correct' | 'problems') {
    void run(async () => {
      const data = await request<{ source_id: string; connection_id: string; source: Source; destination: Destination }>('/demo', { scenario });
      setSource(data.source); setSourceId(data.source_id); setDestination(data.destination); setConnectionId(data.connection_id);
      setDemo(true); setJob(null); setResuming(false); setMode('checksum'); setConsent(false); setStep(2);
    });
  }
  function onStart() {
    void run(async () => acceptJob(await request<Job>('/scans', { source_id: sourceId, connection_id: connectionId, mode, download_consent: consent })));
  }
  function onNew() {
    setStep(0); setJob(null); setSource(null); setSourceId(null); setDemo(false); setMode('checksum'); setConsent(false); setResuming(false); setError('');
  }
  function onResume() {
    void run(async () => {
      if (!job) return;
      let activeConnectionId = connectionId;
      if (job.demo) {
        const sample = await request<{ connection_id: string; destination: Destination }>('/demo', { scenario: job.demo_scenario ?? 'problems' });
        activeConnectionId = sample.connection_id;
        setConnectionId(activeConnectionId);
        setDestination(sample.destination);
      }
      acceptJob(await request<Job>(`/scans/${encodeURIComponent(job.id)}/resume`, { connection_id: activeConnectionId }));
    });
  }
  const maxStep = job?.report ? 3 : source || job ? (destination || job ? 2 : 1) : 0;
  return <>
    <header className="app-header"><div className="header-inner"><a href="/" onClick={(event) => { if (job?.status === 'running') { event.preventDefault(); return; } event.preventDefault(); onNew(); }} className="wordmark">Photo Migration Checker</a><span>Local session</span></div></header>
    <main className="app-main">
      <nav className="step-rail" aria-label="Check progress">{steps.map((name, index) => <div className="step-item" key={name}><button className={`step-button ${index === step ? 'active' : ''}`} disabled={index > maxStep || busy || job?.status === 'running' || (index === 1 && !sourceId) || (index === 2 && Boolean(job?.report) && !sourceId)} aria-current={step === index ? 'step' : undefined} onClick={() => { setStep(index as Step); setError(''); }}><span className="step-number">{index + 1}</span><span>{name}</span></button>{index < 3 ? <span className="step-line" /> : null}</div>)}</nav>
      {error ? <div role="alert" className="error-message"><strong>Could not complete this step.</strong><span>{error}</span><button type="button" onClick={() => setError('')} aria-label="Dismiss error">Dismiss</button></div> : null}
      {step === 0 ? <SourceStep busy={busy} run={run} onSource={onSource} onDemo={onDemo} /> : null}
      {step === 1 ? <DestinationStep source={source} busy={busy} run={run} onConnect={onConnect} /> : null}
      {step === 2 ? <ScanStep source={source} destination={destination} busy={busy} job={job && !job.report ? job : null} mode={mode} consent={consent} onMode={(next) => { setMode(next); setConsent(false); }} onConsent={setConsent} onStart={onStart} onCancel={() => void run(async () => { if (job) acceptJob(await request<Job>(`/scans/${encodeURIComponent(job.id)}/cancel`, {})); })} onResume={onResume} onReconnect={() => { setResuming(true); setStep(1); }} connectionReady={Boolean(connectionId)} demo={demo} /> : null}
      {step === 3 && job?.report ? <Results job={job as Job & { report: Report }} busy={busy} onExport={(format) => void run(async () => exportReport(job.id, format))} onNew={onNew} /> : null}
      {step === 0 ? <ScanHistory jobs={jobs} busy={busy} onOpen={(selected) => void run(async () => { const saved = await request<Job>(`/scans/${encodeURIComponent(selected.id)}`); setSource(null); acceptJob(saved); })} /> : null}
      <footer className="app-footer">This check cannot prove Google exported everything. Keep your originals.</footer>
    </main>
  </>;
}
