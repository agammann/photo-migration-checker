# Architecture

The app serves compiled React / TypeScript assets and a small FastAPI API on `127.0.0.1`. The browser talks only to that local API. Python performs source reading, streamed hashing, Immich access, evidence comparison and report rendering. No backend service is required beyond the user's existing Immich server.

## Data flow

`Extracted folder → source manifest → evidence comparison ← Immich inventory / streamed originals`

`SQLite checkpoints → resumable scan job → React results → offline HTML / JSON`

- `pmc/source.py`: deterministic path manifest, SHA-256 and SHA-1, bounded sidecar parsing, conservative associations and album metadata, source change checks. Container inspection shares the hashing stream.
- `pmc/media.py`: bounded JPEG/PNG/MP4/MOV/AVI structure inspection, exact modern/legacy Google Motion Photo bounds and embedded-video hashes; no media payload decoding or raw XMP persistence.
- `pmc/container_dates.py`: bounded streamed movie/track/media creation fields, separate from source capture instants; invalid, zero or conflicting fields never establish a date.
- `pmc/dates_compare.py`: direct Takeout capture comparisons and separately labeled nominal container-date comparisons, provenance, positive evidence and coverage denominators.
- `pmc/pairing.py`: pure comparison of validated source pair assertions with actual destination links, current component hashes or compatible stored evidence. Media-type labels and filenames never establish a pair.
- `pmc/media_compare.py`: pure byte-derived family versus API classification comparison, with separate source/current/stored evidence levels and coverage counts.
- `pmc/immich.py`: allowlisted read operations, opaque cursor pagination, active / non-locked accessible scope, album memberships, original download with explicit `edited=false`, sanitized errors.
- `pmc/compare.py`: pure comparison rules; content proof, metadata and membership findings remain distinct. Duplicate source occurrences retain their paths while sharing content evidence.
- `pmc/engine.py`: one background worker; SQLite job, manifest and original-hash records; cancellation event; restart detection; source rehash and destination re-enumeration before a finished report.
- `pmc/api.py`: loopback / Host / Origin / Fetch Metadata guards, per-process random session token on local API requests, in-memory destination credentials, source selection and explicit mode consent.
- `pmc/reports.py`: escaped offline HTML without scripts or remote resources; structured JSON. No CSV export.
- `pmc/sample.py`: explicitly requested creation of synthetic source / destination fixture files. It is separate from the read-only source scanner and production Immich adapter.

## Evidence policy

Original mode downloads every accessible active destination original, incrementally hashes it using SHA-256, and discards byte buffers. It matches these hashes to source hashes. A missing match is conclusive only within the successfully enumerated and downloaded scope. Failed pages or original requests yield unresolved / inaccessible cases, never a clean missing assertion based on incomplete evidence.

Checksum mode compares compatible source SHA-1 to Immich's base64 SHA-1 upload checksum only for the exact source-reviewed version and explicit upload provenance. External-library records may use a path checksum; unknown provenance remains unresolved. A checksum match never becomes original-byte proof.

Capture date comparisons require a trustworthy source epoch and timezone-aware destination instant. Original camera timezone is not inferred. Album comparisons require source album metadata and matched asset memberships. Same-name destination albums remain separate identities.

Sidecar-free MP4/MOV videos may compare complete, nonzero and mutually agreeing container creation fields with `fileCreatedAt` as nominal UTC. This never establishes shutter time or original camera timezone, and never overrides malformed, ambiguous or conflicting sidecar evidence. Eligible unmatched originals remain in the date denominator. The exact recognized empty shared-album comments JSON remains hashed and inventoried as neutral auxiliary evidence, outside media matches and attention; association candidates, nonempty and unknown JSON keep their normal conservative handling.

## Persistence and lifecycle

SQLite stores job state, source manifests, minimized destination metadata and original hash checkpoints. Keys are never stored. The checkpoint database may contain sensitive relative paths and an absolute source root required for resume. The user chooses the data directory; default is `.pmc` under the launch directory. Stop the app before removing a data directory. There is no boot service, scheduled task or telemetry.

On startup, jobs left `running` become `interrupted`. Resume requires a fresh in-memory connection to the same normalized server URL. It rechecks the source and destination. Original downloads are repeated rather than promoting stale cached hashes to current proof. A finished report does not represent an atomic source or destination snapshot.

## Browser boundary

Loopback binding, a loopback Host allowlist, same-origin checks and rejection of cross-site Fetch Metadata guard the local server. The UI bootstraps a random token; every further local API endpoint requires it in a custom header. No permissive CORS is installed. The app uses a restrictive content security policy, no external fonts / images / scripts, escaped React text, and credential-free error messages. Requests to Immich never follow redirects. This boundary does not protect against an already compromised operating-system account or a malicious local process that can read the application memory.

## Resource bounds

One scan runs at a time. Source files are read in 1 MiB chunks; original downloads are hashed in incremental transport chunks. JSON sidecars are limited to 2 MiB; destination JSON pages are capped at 64 MiB. Enumeration uses bounded pages, while complete metadata inventories reside in memory. Cancellation is checked while hashing, during response streaming, between pages and between originals. Network reads have a 30-second inactivity timeout. Large collections trade transfer time for independent proof; the preview is an estimate, not a hard traffic cap.
