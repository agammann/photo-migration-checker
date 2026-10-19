import { useDeferredValue, useMemo, useState } from 'react';
import type { DateProvenance, Finding, Job, MediaProof, Report } from './types';
import { Banner, bytes, humanize, Icon, PageHeading } from './ui';

const verified = new Set(['original', 'checksum']);
const attentionFree = new Set(['original', 'checksum', 'not_applicable']);
const unresolved = new Set(['unresolved', 'inaccessible', 'ambiguous', 'unsupported', 'possible']);
const PAGE_SIZE = 8;

function needsAttention(finding: Finding) {
  return !attentionFree.has(finding.status);
}

function Evidence({ finding }: { finding: Finding }) {
  const neutral = finding.status === 'not_applicable';
  const good = verified.has(finding.status);
  const bad = ['missing', 'mismatched'].includes(finding.status);
  return <span className={`evidence ${neutral ? '' : good ? 'evidence-good' : bad ? 'evidence-bad' : 'evidence-warning'}`}>{neutral ? null : <Icon name={good ? 'check' : bad ? 'cross' : 'warning'} size={20} />}<span>{finding.evidence}</span></span>;
}

export function Results({ job, busy, onExport, onNew }: { job: Job & { report: Report }; busy: boolean; onExport: (format: 'html' | 'json') => void; onNew: () => void }) {
  const { report } = job;
  const { summary } = report;
  const [query, setQuery] = useState('');
  const deferredQuery = useDeferredValue(query);
  const [filter, setFilter] = useState('all');
  const [selectedIndex, setSelectedIndex] = useState(() => Math.max(0, report.findings.findIndex((finding) => finding.kind === 'content' && !verified.has(finding.status))));
  const [page, setPage] = useState(Math.floor(selectedIndex / PAGE_SIZE));
  const findings = useMemo(() => {
    const needle = deferredQuery.trim().toLocaleLowerCase();
    return report.findings.map((finding, index) => ({ finding, index })).filter(({ finding }) => {
      const category = filter === 'all' || (filter === 'attention' && needsAttention(finding)) ||
        (filter === 'matched' && finding.kind === 'content' && verified.has(finding.status)) || (filter === 'unresolved' && unresolved.has(finding.status)) ||
        (filter === 'metadata' && ['metadata', 'source_metadata'].includes(finding.kind)) ||
        (filter === 'album' && finding.kind === 'album') || (filter === 'paired_media' && finding.kind === 'paired_media') ||
        (filter === 'media_type' && finding.kind === 'media_type') || (filter === 'auxiliary' && finding.kind === 'auxiliary') ||
        (filter === 'missing' && ['missing', 'mismatched'].includes(finding.status));
      return category && (!needle || `${finding.path} ${finding.asset_ids.join(' ')} ${finding.message} ${finding.evidence}`.toLocaleLowerCase().includes(needle));
    });
  }, [report, deferredQuery, filter]);
  const pageCount = Math.max(1, Math.ceil(findings.length / PAGE_SIZE));
  const currentPage = Math.min(page, pageCount - 1);
  const pageFindings = findings.slice(currentPage * PAGE_SIZE, (currentPage + 1) * PAGE_SIZE);
  const selected = pageFindings.find(({ index }) => index === selectedIndex) ?? pageFindings[0];
  return <>
    <PageHeading title="Your migration, checked." subtitle="Review the evidence before making decisions about your originals."><button className="button secondary" disabled={busy} onClick={() => onExport('json')}>Export JSON</button><button className="button primary" disabled={busy} onClick={() => onExport('html')}>Export HTML</button></PageHeading>
    <Banner title={!summary.coverage_complete ? 'Incomplete coverage' : summary.attention ? 'Review required' : 'Scope checked — review the evidence'}>{!summary.coverage_complete ? 'Some source or destination evidence could not be checked. Unresolved items and coverage gaps are listed below.' : summary.attention ? 'Some items need attention. This report covers only the supplied export.' : 'No differences were found within this scan’s scope. This does not prove Google exported everything.'}{job.demo ? <span className="sample-disclosure"> Sample fixture results · simulated destination · not a real migration validation.</span> : null}</Banner>
    <div className="summary-strip"><div><span>{summary.media_files !== undefined ? 'Media files' : 'Source files'}</span><strong>{(summary.media_files ?? summary.source_files).toLocaleString()}</strong></div><div><span>Content matched</span><strong>{summary.matched.toLocaleString()}</strong></div><div><span>Needs attention</span><strong>{summary.attention.toLocaleString()}<small> {summary.attention === 1 ? 'finding' : 'findings'}</small></strong></div><div><span>Verification</span><strong className="verification-value">{report.mode === 'original' ? 'Original bytes' : 'Server checksum'}</strong></div></div>
    {summary.inventory_files !== undefined ? <div className="coverage-line" aria-label="Source inventory"><span>Total inventory: <strong>{summary.inventory_files.toLocaleString()} files</strong></span>{summary.media_files !== undefined ? <span>Media: <strong>{summary.media_files.toLocaleString()}</strong></span> : null}{summary.sidecar_files !== undefined ? <span>Sidecars: <strong>{summary.sidecar_files.toLocaleString()}</strong></span> : null}{summary.album_metadata_files !== undefined ? <span>Album metadata: <strong>{summary.album_metadata_files.toLocaleString()}</strong></span> : null}{summary.auxiliary_files !== undefined ? <span>Auxiliary files: <strong>{summary.auxiliary_files.toLocaleString()}</strong></span> : null}</div> : null}
    {report.coverage ? <div className="coverage-line"><span>Capture dates comparable: <strong>{report.coverage.capture_dates.comparable} / {report.coverage.capture_dates.total}</strong></span>{report.coverage.container_dates?.total ? <span>Nominal container dates comparable: <strong>{report.coverage.container_dates.comparable} / {report.coverage.container_dates.total}</strong></span> : null}<span>Source album membership asserted: <strong>{report.coverage.album_membership.asserted_occurrences} / {report.coverage.album_membership.total}</strong></span>{report.coverage.media_types ? <span>Media types checked: <strong>{report.coverage.media_types.checked} / {report.coverage.media_types.matched}</strong></span> : null}{report.coverage.paired_media?.total ? <span>{report.mode === 'original' ? 'Pair byte matches' : 'Stored pair relationships'}: <strong>{report.mode === 'original' ? report.coverage.paired_media.original_verified : report.coverage.paired_media.checksum_supported} / {report.coverage.paired_media.asserted}</strong></span> : null}</div> : null}
    <section aria-labelledby="findings-heading" className="findings-section">
      <div className="findings-toolbar"><h2 id="findings-heading">Findings</h2><div className="filters"><div className="search-field"><Icon name="search" /><input type="search" value={query} onChange={(event) => { setQuery(event.target.value); setPage(0); }} aria-label="Filter findings by path or asset ID" placeholder="Filter by path or asset ID" /></div><select aria-label="Finding category" value={filter} onChange={(event) => { setFilter(event.target.value); setPage(0); }}><option value="all">All findings</option><option value="attention">Needs attention</option><option value="matched">Content matched</option><option value="missing">Missing or mismatched</option><option value="metadata">Capture and container dates</option><option value="album">Album differences</option><option value="paired_media">Paired media</option><option value="media_type">Media types</option><option value="auxiliary">Auxiliary files</option><option value="unresolved">Unresolved</option></select></div></div>
      <div className="table-wrap" tabIndex={0} aria-label="Findings table; scroll horizontally on small screens"><table><thead><tr><th scope="col">Source file</th><th scope="col">Evidence</th><th scope="col">Destination</th><th scope="col">Details</th></tr></thead><tbody>{pageFindings.map(({ finding, index }) => <tr key={index} className={selected?.index === index ? 'selected' : ''} onClick={() => setSelectedIndex(index)}><td><button className="file-button" aria-pressed={selected?.index === index} onClick={() => setSelectedIndex(index)} title={finding.path}>{finding.path}</button></td><td><Evidence finding={finding} /></td><td className="destination-cell" title={finding.asset_ids.join(', ')}>{finding.asset_ids.length ? `${finding.asset_ids[0].slice(0, 13)}${finding.asset_ids[0].length > 13 ? '…' : ''}${finding.asset_ids.length > 1 ? ` +${finding.asset_ids.length - 1}` : ''}` : '—'}</td><td><span className="detail-preview" title={finding.message}>{finding.message}</span></td></tr>)}</tbody></table>{!findings.length ? <div className="empty-state">No findings match these filters. Try another path, asset ID or category.</div> : null}</div>
      <div className="table-caption"><span aria-live="polite">{findings.length.toLocaleString()} of {report.findings.length.toLocaleString()} findings{findings.length > PAGE_SIZE ? ` · Page ${currentPage + 1} of ${pageCount}` : ''}</span>{pageCount > 1 ? <div className="button-row"><button className="button quiet small" disabled={currentPage === 0} onClick={() => setPage(currentPage - 1)}>Previous</button><button className="button quiet small" disabled={currentPage === pageCount - 1} onClick={() => setPage(currentPage + 1)}>Next</button></div> : <span>Select a source file to inspect its evidence.</span>}</div>
    </section>
    {selected ? <EvidenceInspector key={`${job.id}-${selected.index}`} finding={selected.finding} /> : null}
    <details className="coverage-details"><summary>Scan scope, limitations and export contents</summary><div className="coverage-body"><p>{report.scope}</p>{report.coverage ? <p>{report.coverage.album_membership.policy}</p> : null}<dl className="coverage-grid"><div><dt>Immich version</dt><dd>{report.immich_version ?? 'Unknown'}</dd></div><div><dt>Source bytes</dt><dd>{bytes(summary.source_bytes)}</dd></div><div><dt>Unique source content</dt><dd>{summary.unique_source_content.toLocaleString()}</dd></div><div><dt>Accessible destination assets</dt><dd>{summary.destination_assets.toLocaleString()}</dd></div><div><dt>Source / destination albums</dt><dd>{summary.source_albums.toLocaleString()} / {summary.destination_albums.toLocaleString()}</dd></div><div><dt>Evidence level</dt><dd>{summary.verification}</dd></div></dl><AdditionalScope report={report} /><p>JSON and HTML exports include the full report: relative source paths, hashes, asset and album IDs, comparison dates, findings and limitations. They exclude your API key. Treat exported reports as sensitive.</p><ul>{report.limitations.map((text) => <li key={text}>{text}</li>)}</ul></div></details>
    <div className="results-actions"><button className="button quiet" onClick={onNew}>Start another check<Icon name="arrow" size={18} /></button><span>Scan {job.id.slice(0, 8)}</span></div>
  </>;
}

function EvidenceInspector({ finding }: { finding: Finding }) {
  return <section className="evidence-inspector" aria-label="Selected finding evidence"><div className="inspector-heading"><h3>{finding.path.split('/').pop() || finding.path}</h3><span>{humanize(finding.kind)}</span></div><p className="inspector-path">{finding.path}</p>
    <dl className="evidence-fields">
      {finding.source_sha256 ? <div><dt>Source SHA-256</dt><dd className="hash">{finding.source_sha256}</dd></div> : null}
      {finding.source_sha1 ? <div><dt>{finding.kind === 'auxiliary' ? 'Source SHA-1 · inventory hash' : 'Source SHA-1 · stored checksum comparison'}</dt><dd className="hash">{finding.source_sha1}</dd></div> : null}
      {finding.classification ? <div><dt>Auxiliary classification</dt><dd>{finding.classification === 'empty_shared_album_comments' ? 'Empty shared-album comments' : humanize(finding.classification)}</dd></div> : null}
      {finding.content_state ? <div><dt>Auxiliary content state</dt><dd>{finding.content_state === 'empty_object' ? 'Empty JSON object' : humanize(finding.content_state)}</dd></div> : null}
      {finding.kind === 'auxiliary' ? <div><dt>Comparison scope</dt><dd>Source-only auxiliary data. No destination media asset is expected.</dd></div> : null}
      {finding.proof_level ? <div><dt>Comparison evidence</dt><dd>{finding.proof_level === 'current_original_container' ? 'Source and current original containers' : finding.proof_level === 'source_container_stored_association' ? 'Source container and stored checksum association' : humanize(finding.proof_level)}</dd></div> : null}
      {finding.source_media ? <div><dt>Source media from bytes</dt><dd><MediaDescription media={finding.source_media} /></dd></div> : null}
      {finding.source_filename_mime ? <div><dt>Filename MIME hint</dt><dd>{finding.source_filename_mime}</dd></div> : null}
      {finding.expected_type ? <div><dt>Expected Immich type from source bytes</dt><dd>{finding.expected_type}</dd></div> : null}
      {finding.destination_types ? <div><dt>Immich API media types</dt><dd>{Object.entries(finding.destination_types).map(([id, type]) => <div key={id}><small>{id}</small><code>{type ?? 'Unavailable'}</code></div>)}</dd></div> : null}
      {finding.destination_media && Object.keys(finding.destination_media).length ? <div><dt>Destination original media from bytes</dt><dd>{Object.entries(finding.destination_media).map(([id, media]) => <div key={id}><small>{id}</small><MediaDescription media={media} /></div>)}</dd></div> : null}
      {finding.mismatched_asset_ids?.length ? <div><dt>Assets with a media-type difference</dt><dd>{finding.mismatched_asset_ids.map((id) => <code key={id}>{id}</code>)}</dd></div> : null}
      {finding.unknown_asset_ids?.length ? <div><dt>Assets with unresolved media types</dt><dd>{finding.unknown_asset_ids.map((id) => <code key={id}>{id}</code>)}</dd></div> : null}
      {finding.relation ? <div><dt>Pair relationship result</dt><dd>{humanize(finding.relation)}</dd></div> : null}
      {finding.expected_video_sha256 ? <div><dt>Embedded source video SHA-256</dt><dd className="hash">{finding.expected_video_sha256}</dd></div> : null}
      {finding.expected_video_sha1 ? <div><dt>Embedded source video SHA-1 · stored checksum comparison</dt><dd className="hash">{finding.expected_video_sha1}</dd></div> : null}
      {finding.embedded_video_offset !== undefined ? <div><dt>Embedded video offset</dt><dd>{finding.embedded_video_offset.toLocaleString()} bytes from the start of the source image</dd></div> : null}
      {finding.expected_video_size !== undefined ? <div><dt>Embedded source video size</dt><dd>{finding.expected_video_size.toLocaleString()} bytes ({bytes(finding.expected_video_size)})</dd></div> : null}
      {finding.source_video_paths?.length ? <div><dt>Standalone source videos with matching bytes</dt><dd>{finding.source_video_paths.map((path) => <code key={path}>{path}</code>)}</dd></div> : null}
      {finding.destination_links ? <div><dt>Actual image-to-video links</dt><dd>{Object.entries(finding.destination_links).map(([image, video]) => <div key={image}><small>Image asset {image}</small><code>{video ? `Video target ${video}` : 'No livePhotoVideoId target'}</code></div>)}</dd></div> : null}
      {finding.reverse_links ? <div><dt>Reversed links</dt><dd>{Object.entries(finding.reverse_links).map(([video, image]) => <div key={video}><small>Video asset {video}</small><code>Image target {image}</code></div>)}</dd></div> : null}
      {finding.destination_video_sha256 ? <div><dt>Linked destination original video SHA-256</dt><dd className="hash">{finding.destination_video_sha256}</dd></div> : null}
      {finding.size !== undefined ? <div className="compact-field"><dt>Source size</dt><dd>{bytes(finding.size)}</dd></div> : null}
      {finding.source_occurrences && finding.source_occurrences > 1 ? <div><dt>Duplicate source occurrences</dt><dd>{finding.source_occurrences} occurrences share these source bytes. One verified destination asset can satisfy multiple identical source occurrences.</dd></div> : null}
      {finding.asset_ids.length ? <div><dt>Destination asset IDs</dt><dd>{finding.asset_ids.map((id) => <code key={id}>{id}</code>)}</dd></div> : null}
      {finding.destination_sha256 && Object.keys(finding.destination_sha256).length ? <div><dt>Destination original SHA-256</dt><dd>{Object.entries(finding.destination_sha256).map(([id, hash]) => <div key={id}><small>{id}</small><code className="hash">{hash}</code></div>)}</dd></div> : null}
      {finding.sidecars?.length ? <div><dt>Associated sidecars</dt><dd>{finding.sidecars.map((path) => <code key={path}>{path}</code>)}</dd></div> : null}
      {finding.date_kind ? <div><dt>Date comparison</dt><dd>{finding.date_kind === 'container_creation' ? 'Container creation time' : finding.date_kind === 'capture' ? 'Capture instant' : humanize(finding.date_kind)}</dd></div> : null}
      {finding.source_date_provenance ? <DateEvidence provenance={finding.source_date_provenance} /> : null}
      {finding.source_date ? <div><dt>{finding.date_kind === 'container_creation' ? 'Source container creation time (nominal UTC)' : 'Source capture instant'}</dt><dd>{finding.source_date}</dd></div> : null}
      {finding.destination_dates ? <div><dt>{finding.date_kind === 'container_creation' ? 'Destination fileCreatedAt values' : 'Destination capture dates'}</dt><dd>{Object.entries(finding.destination_dates).map(([id, date]) => <div key={id}><code>{id}</code><span>{date ?? 'Unavailable'}</span></div>)}</dd></div> : null}
      {finding.album_ids?.length ? <div><dt>Destination album IDs</dt><dd>{finding.album_ids.map((id) => <code key={id}>{id}</code>)}</dd></div> : null}
    </dl><p className="evidence-explanation">{finding.message}</p>
  </section>;
}

function AdditionalScope({ report }: { report: Report }) {
  const { summary, coverage } = report;
  const capture = coverage?.capture_dates;
  const container = coverage?.container_dates;
  const captureCounts = [
    capture?.asserted === undefined ? null : `${capture.asserted} asserted`,
    capture?.agreements === undefined ? null : `${capture.agreements} agree`,
    capture?.differences === undefined ? null : `${capture.differences} differences`,
    capture?.unresolved === undefined ? null : `${capture.unresolved} unresolved`,
    capture?.container_only === undefined ? null : `${capture.container_only} container-only`,
  ].filter(Boolean).join(' · ');
  if (summary.inventory_bytes === undefined && summary.auxiliary_bytes === undefined && !captureCounts && !container) return null;
  return <><dl className="coverage-grid">{summary.inventory_bytes !== undefined ? <div><dt>Total inventoried source bytes</dt><dd>{summary.inventory_bytes.toLocaleString()} bytes ({bytes(summary.inventory_bytes)})</dd></div> : null}{summary.auxiliary_bytes !== undefined ? <div><dt>Auxiliary source bytes</dt><dd>{summary.auxiliary_bytes.toLocaleString()} bytes ({bytes(summary.auxiliary_bytes)})</dd></div> : null}{captureCounts ? <div><dt>Capture-instant evidence</dt><dd>{captureCounts}</dd></div> : null}{container ? <div><dt>Nominal container date evidence</dt><dd>{container.comparable} / {container.total} comparable · {container.agreements} agree · {container.differences} differences · {container.unresolved} unresolved</dd></div> : null}</dl>{container?.policy ? <p>{container.policy}</p> : null}</>;
}

function DateEvidence({ provenance }: { provenance: DateProvenance }) {
  const container = provenance.semantics === 'container_creation' || provenance.method === 'iso_bmff.creation_time';
  const fields = Array.isArray(provenance.fields) ? provenance.fields.map((value, index) => [`Field ${index + 1}`, value] as const) : provenance.fields && typeof provenance.fields === 'object' ? Object.entries(provenance.fields) : [];
  return <><div><dt>Source date provenance</dt><dd>{provenance.method === 'takeout.photoTakenTime' ? 'Direct Takeout photoTakenTime timestamp' : provenance.method === 'iso_bmff.creation_time' ? 'Embedded ISO BMFF creation timestamp' : humanize(provenance.method.replaceAll('.', ' '))}</dd></div>{provenance.timezone ? <div><dt>Time interpretation</dt><dd>{provenance.timezone === 'nominal_utc' ? 'Nominal UTC container representation' : provenance.timezone === 'utc' ? 'UTC epoch instant' : humanize(provenance.timezone)}</dd></div> : null}{container || provenance.capture_instant_verified === false ? <div><dt>Capture-instant limitation</dt><dd>This container timestamp does not establish shutter time or the original camera timezone.</dd></div> : null}{provenance.source_paths?.length ? <div><dt>Date evidence source paths</dt><dd>{provenance.source_paths.map((path) => <code key={path}>{path}</code>)}</dd></div> : null}{fields.length ? <div><dt>Container timestamp fields</dt><dd>{fields.map(([name, value]) => <div key={name}><small>{humanize(name)}</small><code className="hash">{typeof value === 'string' || typeof value === 'number' ? String(value) : JSON.stringify(value)}</code></div>)}</dd></div> : null}</>;
}

function MediaDescription({ media }: { media: MediaProof }) {
  return <><div>{humanize(media.family)} · {media.container ?? 'Container unknown'}{media.mime ? ` · ${media.mime}` : ''}</div><div>Container structure: {media.complete ? media.valid ? 'validated' : 'not validated' : 'incomplete inspection'}</div>{media.embedded_video ? <div>Embedded video: {media.embedded_video.size.toLocaleString()} bytes at offset {media.embedded_video.offset.toLocaleString()}</div> : null}{media.motion_photo?.declared ? <div>Motion photo: {media.motion_photo.validated ? 'embedded video validated' : 'declared, unresolved'}{media.motion_photo.format ? ` · ${media.motion_photo.format}` : ''}</div> : null}{media.evidence?.map((text, index) => <div key={`evidence-${index}`}>{text}</div>)}{media.issues?.map((text, index) => <div key={`issue-${index}`}>{text}</div>)}</>;
}
