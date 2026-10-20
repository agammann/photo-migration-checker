# What was actually tested

Development evidence recorded on October 18, 2026 (America/Los_Angeles). Release candidate 0.1.5rc1 checks real disposable Immich 3.3.3, controlled migration problems, and a published Google Photos Takeout from Magnet's 2020 forensic-training scenario imported through independent immich-go 0.32.0. A personal collection and other export variants remain outside this evidence. Versioned receipts distinguish the latest pairing/type validation from historical runs below.

## Release candidate 0.1.5rc2

This candidate changes local API authorization and launch behavior. An unrelated loopback HTTP client previously obtained the process token from unauthenticated bootstrap and then read a synthetic saved report. The updated API requires the current launch capability for bootstrap, reads, exports and mutations. The launcher reserves the endpoint before printing its private fragment link; an occupied port emits no link and does not create the checkpoint directory.

The Windows Python 3.12 deterministic suite passes 251 tests and 28 subtests, with one symlink-capability skip and the existing Starlette TestClient warning. Focused actual loopback tests exercise the normal CLI, unauthorized bootstrap, authenticated sample access, occupied-port refusal and a new capability after process restart. The frozen frontend build passes.

Chrome 155.0.8059.85 checks at 1505 by 1045 and 390 by 844 cover private-fragment removal before API requests, sample scan and JSON export, tab reload, stale-capability rejection after restart, opening the new link in an existing tab, and blocked browser storage. An open tab can use an in-memory capability when storage is blocked; a reload then requires the private link again. The successful sample flow had no page or console errors or capability in request URLs. The Browser plugin was unavailable, so these checks used local Playwright with the installed Chrome executable and synthetic data.

The migration-evidence rules are unchanged. The historical real Immich and real Takeout results below were not rerun for this authorization change. They do not establish a fresh real-provider result for this candidate. Native macOS behavior and a compromised account, terminal, browser or process able to read the capability remain outside these checks.

## Release candidate 0.1.5rc1

The candidate keeps the unresolved edited-photo date flagged. It changes distribution metadata, bundled license notices, source-archive privacy exclusions, documentation and the singular finding label; the migration-evidence rules and schema 3 are unchanged. Python package metadata uses `0.1.5rc1`; the private frontend package uses the equivalent npm spelling `0.1.5-rc.1`.

The frontend rebuild passes from the frozen pnpm lock. The wheel includes the exact React, ReactDOM and scheduler MIT copyright/permission notice and Inter OFL. All application and bundled-web bytes are compared with the frozen source and fresh installed package. The packager regression exercises accidental private JSON, environment, credential, database, journal and dump files under otherwise eligible source directories.

### Platform validation

| Environment | Installed candidate validation | Observed result |
| --- | --- | --- |
| Windows, Python 3.12.14 | Complete deterministic suite outside checkout | 248 passed, 28 subtests passed; one symlink-privilege skip |
| Linux container, Python 3.11.17 | Exact wheel, tests/scripts copied to tmpfs, read-only source/artifact mounts | 248 passed, 28 subtests passed; Windows-only junction test skipped; symlink test ran |
| Linux container, Python 3.13.15 | Same isolated installed-wheel flow | 248 passed, 28 subtests passed; Windows-only junction test skipped; symlink test ran |
| Windows default `py -3`, Python 3.14.8 | Normal runtime dependency install, CLI and actual loopback HTTP smoke | Clean/problem samples in both modes, JSON/HTML exports, session guard, bundled notices and saved history passed |

The deterministic suite retains one existing Starlette TestClient deprecation warning about a future transport change. This warning is distinct from browser console health. Exact Linux image and candidate-wheel digests are recorded in the validation receipts; transient Linux containers expose no ports or Docker socket and are removed after the tests. These are local Linux-container results, not remote GitHub CI or native macOS validation. The configured CI matrix now targets Python 3.11 and 3.13 on Windows and Ubuntu and checks wheel installation outside the checkout. Remote execution remains unperformed.

Dependency advisory checks at candidate preparation time found no published advisories for 122 locked frontend packages, all 24 locked Python packages (PyPI and OSV checked separately), and the pinned setuptools 84.0.0 build backend. There were no skipped packages or unavailable advisory services. All 18 runtime packages selected by the default Python 3.14 install equal their audited lock versions. An advisory scan does not prove absence of vulnerabilities or malicious behavior, and other future dependency resolutions are outside that exact-version evidence.

The main installed preview was upgraded from 0.1.4 only after stopping it and backing up its entire data directory. SQLite integrity and every preexisting row remained identical, and both historical reports stayed available. Keys were reconnected in memory for a fresh scan rather than persisted.

The frozen installed candidate passed the complete real-server rerun in both modes: 62 content matches, 62 media-type agreements, eight verified motion pairs, seven matching albums, 53 trusted sidecar capture instants and eight separately reported nominal container times. Both reports contain 195 findings and exactly one unresolved edited-photo capture date; coverage remains explicitly incomplete. No timestamp was guessed or changed. An independent raw-HTTP/source oracle checked the report rows and unchanged source files.

The same run passed the clean/problem libraries, 260-original pagination, minimum permissions, three deliberate failure cases and ten isolated pairing-fault scans. Controlled source-copy, temporary-album and pair-link changes were restored. Those setup actions change normal update/audit metadata; the later read-only preservation window starts after restoration, rather than claiming those tables never changed during fault injection.

Eleven installed-wheel browser checks passed at 1505×1045 and 390×844, including both real-export modes, evidence filters, provenance, JSON and rendered offline HTML exports, reload, cancellation, reconnection and recovery after forced process termination. Both resumed scans freshly downloaded all 327,044,331 original bytes. The browser recorded zero unexpected errors and zero warnings, with one expected connection-refused event during the deliberate process kill. Six existing native MP4 playback responses also passed complete FFmpeg decode without errors.

Independent preservation checks confirmed all 123 source files unchanged by SHA-256, SHA-1, size and modification time. All 356 disposable stored originals, totaling 401,456,805 bytes, remained unchanged even across the fault exercises. All 13 audited media/album table fingerprints exactly matched the post-restoration baseline across the final browser and main-preview scans. The observer recorded 1,291 successful requests, zero writes, 332 completed original responses and two deliberately interrupted streams, with no pending records or ledger failures. Its process and the three owned test services were stopped; their data volumes were retained. The installed candidate remains available on the main loopback preview with a fresh completed original-mode report and its one explicit date flag.

The final source archive is built after this documentation is saved. Its exact archive digest, a fresh installation and loopback HTTP smoke on the Windows default Python, package-byte comparisons, private-data exclusions and deliverable checks are recorded in the external release-candidate verification receipt. This file intentionally does not claim a future remote CI run or a publication.

## Automated checks

Latest installed Windows automated run: **248 passed, 1 skipped, 28 subtests passed** on Windows, Python 3.12.14. This includes the backend and test-harness regressions. The skip is symbolic-link creation, unavailable without the required Windows privilege; Windows junction no-follow behavior passed. A Starlette TestClient deprecation warning notes a future transport change; there were no test failures.

The automated suite covers:

- Clean fixtures in both modes with eight matched source occurrences, seven distinct destination originals, three albums, and zero attention findings.
- Omitted original and edited versions, identical filenames with different content, legitimate deduplication across albums, changed capture instants, unknown timezones and missing date evidence.
- Missing memberships, duplicate album names, unknown album identity, conflicting album metadata, malformed and ambiguous sidecars, filename/title contradictions.
- Video original bytes, byte-derived container families, validated modern and legacy Google Motion Photo bounds, embedded-video hashes, actual destination links, wrong/missing/reversed/cyclic pairs, stored-checksum provenance, unrecognized formats and unsupported JSON.
- Cursor pagination, repeated / missing cursors, permission failures, timeouts, external-library checksum provenance, offline assets, trashed assets, shared-album visibility and write-request rejection.
- Cancellation / resume, process interruption, durable SQLite checkpoints, source mutation during hashing / between observations, destination metadata mutation, and unchanged source hashes / modification timestamps.
- Loopback Host / Origin / Fetch Metadata guards, session token requirement, explicit download consent, sanitized validation errors, escaped HTML, private report fields, and refusal to put checkpoint writes inside a selected source.

`tests/test_engine.py` includes an actual loopback HTTP protocol fixture with paginated JSON and streamed original responses. It proves transport behavior and the checker request allowlist against that fixture. It is **not an Immich server** and cannot establish real Immich compatibility. MockTransport tests separately test protocol errors and malformed responses.

The problem fixture reports 17 source entries, 12 content matches, two missing originals, one byte mismatch and two unsupported files. Metadata / album / sidecar / filename-pair uncertainty findings make 27 attention findings. Version 0.1.3 adds separate media-type evidence rows. Coverage is incomplete. The clean fixture has eight matches and no attention findings. Static hashes and seeded expectations are in `tests/fixtures/expected.json`.

## Browser checks

The full local browser flow has been exercised using Playwright Chromium 156.0.8078.4 at 1505×1045 and 390×844. The Browser plugin skill was unavailable, so local Playwright was used. Eleven checks passed:

1. App identity and meaningful source screen.
2. Source folder preview and connection through a real HTTP protocol fixture.
3. Cancellation reaches a stopped, resumable state.
4. Resume completes original-byte comparison through HTTP transport.
5. Original downloads require explicit consent; seeded unresolved cases show incomplete coverage.
6. Path search and evidence inspector display source hashes and destination IDs.
7. Empty search state and metadata category filters work.
8. Downloaded JSON and HTML contain expected findings and no API key.
9. Mobile layout has no page-wide horizontal overflow; the table scrolls in its own region.
10. Saved reports remain available after a browser reload.
11. No browser console / page errors, framework overlays, or external browser requests.

The fixture server observed only GET requests and read-only `POST /api/search/metadata` from the checker. It received no upload / mutation request. Credentials used for that fixture were synthetic test data; no personal credentials were used.

The eleven-check sample browser run was repeated against the **historical 0.1.0 wheel installed in a separate virtual environment**, served on loopback port 8766 from outside the source tree. All eleven checks passed with the violet / lime Inter interface. That wheel contains eleven web files, including seven WOFF2 font subsets and the Inter OFL license. The documented sample workflow and downloaded reports therefore ran against an installed package, not a source-tree import. The normal user preview now serves the installed 0.1.5rc1 candidate on port 8765; its current checks are recorded in the release-candidate section above.

The exported HTML was also opened as an offline local file and visually inspected at desktop size. Its 39 findings rendered with coverage and sample limitations visible; `docs/screenshots/report-preview.png` records that inspection.

`scripts/browser-smoke.mjs` reproduces the sample checks against a running app. Optional `PMC_FIXTURE_SOURCE`, `PMC_FIXTURE_URL`, and `PMC_FIXTURE_KEY` enable the controlled HTTP connection / cancel / resume branch. The fixture must deliberately keep the first download slow enough to cancel; the test does not target a personal library. Screenshots and a machine-readable browser receipt are in `docs/screenshots/` and `docs/test-evidence/`.

## Real Immich integration — passed

**Actual Immich version tested: v3.3.3.** Official API / server source reference: commit `d2dac658fe1c67e8bbd08aa18200a32e5d45b9e4`. Runtime: Docker Desktop 4.94.0, Linux Engine 29.8.2. The server, database and Redis use a unique disposable Compose project and named volumes. Only the loopback Immich port is published.

The earlier Docker startup blocker was rechecked and the Linux engine was already responding. No factory reset, socket deletion, or secret-store alteration was needed. The first Immich start exposed a database-readiness race in the test Compose setup; health-based dependency conditions fix that race without adding restart-at-boot behavior. Fresh generated Compose configuration validation passes.

The final complete `--run` reproduction started from an empty disposable project and **passed in 126.07 seconds**, without manual container restarts. It repeated both modes, controlled videos, seeded findings, minimum-permission failures and 260-asset pagination. Before each preservation snapshot, the setup administrator waits for idle media queues and five stable inventories, bounded by 180 seconds. This final run exercised actual pending background work: the clean library required 15 polls (10 busy), the problem library seven polls (two busy), and pagination five polls. This prevents post-upload timestamp changes from invalidating a test's starting conditions. A regression test confirms unchanged EXIF alone cannot bypass that wait.

Afterward, the three final test services were stopped and their volumes preserved. Earlier owned test stacks are also stopped. The Docker engine remains running, and unrelated Docker projects were not modified. The sanitized `fresh-stack-summary.json`, `fresh-stack-backend-evidence.json`, `fresh-stack-quiescence.json` and `runtime-image.json` record the reproduction, queue observations and immutable image identity.

The extended live harness uses separate disposable users for clean, seeded-problem and pagination scenarios. Its setup client creates test media and albums; scoped checker keys have no write permissions. It runs the actual Manager lifecycle and streams originals from the real server, independently checking source hashes / modification times and destination inventories / original hashes before and after.

| Real-server check | Observed result |
| --- | --- |
| Clean library, both modes | 10 source occurrences, 7 originals, 6 albums; zero attention findings |
| Seeded library, original mode | 21 source items; 16 matched, 2 missing, 1 mismatched, 2 unsupported; 30 attention findings, explicitly incomplete |
| Seeded library, checksum mode | Historical checksum matches remain separate from original-byte proof; changed-byte filename stays only a possible match |
| Album identity and empty albums | Distinct names resolve identical membership; one destination album cannot silently satisfy two source identities; missing empty album is reported |
| Actual cursor pagination | 260 real originals cross the 250-result page boundary and finish without false alarms |
| Minimum permissions | Read / album / download scoped key succeeds; missing download permission returns real HTTP 403; denied album access remains incomplete |
| Media | Real PNG images, indexed AVI videos, genuine H.264 MP4 and a large valid PNG used for streamed transfers |
| Source change during scan | A modified source copy is flagged with incomplete coverage; original fixture stays unchanged |
| Destination change during scan | Setup-created empty album is detected; that exact temporary album is removed afterward and baseline is verified restored |
| Timeout | A test observer delays real upstream original headers by 1 second; a 0.4-second client timeout produces inaccessible findings, no false missing claims |

The source and destination mutation tests use scheduling barriers after actual inventory requests; responses and media are not mocked. Timeout tests use explicit transport fault injection against the real upstream server. A separate raw HTTP oracle hashes originals without importing the checker adapter. Test receipts and real reports are retained under `docs/test-evidence/real-immich/`.

### Real-server browser and installed-package checks

The real Source → Destination → Scan → Results workflow passed **18 checks** across the clean and seeded libraries at 1505×1045 and 390×844. Both verification modes, live evidence inspection, filters, full JSON exports, rendered offline HTML reports, browser reload and source-preservation checks passed. No unexpected console / page errors or external browser requests occurred. The expected connection interruption during an intentional process shutdown is recorded separately.

Cancellation and forced Python-process termination each occurred during an independently observed real original download after at least 1 MiB had been forwarded. Stopped scans had no finished report. Resume required reconnection after process restart, freshly transferred all **53,171,916 bytes** of the problem library, and matched the expected findings. Source contents, sizes and modification times stayed unchanged.

The problem workflow's **10 checks were repeated against the installed 0.1.1 wheel**, running outside the repository with `PYTHONPATH` cleared. They passed, including cancellation, process interruption, reconnection and full re-download. The installed package imports from `site-packages`, not the checkout. Its eleven web files exactly match the current build and include seven Inter font subsets plus the OFL license.

The transparent loopback observer forwarded unchanged responses from the real Immich server, limiting transfer speed only to make lifecycle transitions observable. Across the source and installed-package browser runs it recorded **593 requests, zero write attempts, 107 completed original responses and four deliberately interrupted original streams**. A separate Docker-side audit found **all 281 stored originals, totaling 53,191,644 bytes, and all 13 audited media/album table fingerprints unchanged** before and after both browser runs. Authentication-usage and job-queue bookkeeping are outside those table fingerprints.

### Reproducing the live checks

Use a fresh working folder and a working Docker Linux engine:

```sh
python scripts/immich_integration.py --run --keep --work-dir ./work/live-qa
```

This creates separate disposable users, valid PNG / AVI media, a large transfer fixture, album cases and the 260-original pagination library. `--extra-video /path/to/controlled.mp4` adds an existing controlled MP4. The harness validates the actual container's project label, image and loopback binding before setup writes. Test credentials are stored only in the private working folder for the test runners; never copy that folder into a report or commit.

`scripts/observe_immich.py` supplies read-only forwarding and optional delayed headers for fault injection. `scripts/browser-real-immich.mjs` reads the private state at runtime and owns a separate local app process; its optional `PMC_REAL_APP_CWD` selects an installed package. `scripts/live_failure_checks.py` performs the source-copy mutation, temporary album mutation / restoration, and timeout checks. `scripts/audit_disposable.py` independently reads container originals and database table fingerprints. These are test tools, not application code, and are never imported by the checker.

## Published real Takeout migration

The main real-export case is the **Google Photos portion of Magnet's 2020 CTF Takeout**, downloaded from [Digital Corpora](https://digitalcorpora.s3.amazonaws.com/corpora/scenarios/magnet/2020%20CTF%20-%20Takeout.zip). Magnet explicitly publishes its CTF images for learning, testing and tool validation ([publisher statement](https://www.magnetforensics.com/blog/magnet-weekly-ctf-2020-images-and-questions/)). Digital Corpora's [terms](https://digitalcorpora.org/about-digitalcorpora/terms-of-use/) make original scenario data available under CC0, with an exception for independently copyrighted embedded material. The test downloads are retained privately; no original media or raw account metadata is redistributed with this project.

The complete ZIP is 356,764,506 bytes, SHA-256 `0cff235410a2475d71aca69bde9c4f6e8835fe8aaca3f87b6a35dd6184b4b59d`. Only the exact `Takeout/Google Photos/` prefix was extracted. All selected entries passed ZIP CRC and size validation, with traversal, links and duplicate destinations rejected. The unchanged extracted source has 123 files: 62 media occurrences and 61 JSON files, including seven album metadata files. Media total 327,044,331 bytes. Although 61 media filenames end in `.jpg` and one in `.mp4`, independent header inspection finds 53 JPEG containers and nine MP4 containers: eight exported motion components use `.jpg` filenames. Extension labels are not codec validation.

Official **immich-go 0.32.0** imported the unchanged source into an isolated account on a fresh, owned Immich 3.3.3 Docker project, with no upload errors. Its Windows download was verified against published SHA-256 `37326f95d6654f7f67a5fde3263e96aa8f9cf288dcbb9a2164aafae0aaa144af`. Setup credentials stayed in a private test configuration, never command arguments. The importer's own processed/discarded counters were not treated as preservation proof.

An independent source oracle uses explicitly reviewed sidecar relationships, and a separate raw HTTP oracle imports no checker code. It streams each actual destination original with `edited=false`, hashes it and compares raw album memberships and capture epochs. Observations establish:

| Real-export evidence | Result |
| --- | --- |
| Original media | All 62 distinct source SHA-256 hashes and sizes match actual destination originals; zero missing or changed originals |
| Capture dates | All 53 reviewed sidecar epochs match destination capture instants; nine source occurrences have no trustworthy sidecar date |
| Albums | Seven source and destination albums; one motion-component membership missing from `2020-03-10`, one from `Instant Upload` |
| Pairing | Eight JPEGs contain structurally valid appended videos at exact legacy XMP bounds. Each embedded SHA-256 and size matches the actual `livePhotoVideoId` original; all eight pairs verified |
| Media classification | All 62 source containers are structurally identified: 53 JPEG and nine MP4. Six MP4 originals with `.jpg` names are labeled `IMAGE` by Immich; six explicit type differences, 56 agreements |
| Auxiliary JSON | The archive's unchanged three-byte `shared_album_comments.json` is surfaced as unsupported, not silently discarded |
| Checker, both modes | 62 matches, 20 attention findings across 146 rows, explicitly incomplete coverage; both album omissions, eight pairs and six type differences agree with the independent oracle |

The checker counts 63 source items because its report also includes the unsupported auxiliary JSON. The 20 attention findings comprise nine unavailable dates, six media-type differences, two album differences, one unsupported content row, one related source-metadata finding and one coverage row. None asserts a missing photograph. Pair verification is independent of API media type: a byte-correct video link can coexist with an incorrect `IMAGE` classification.

### Version 0.1.3 pairing and media-type validation

The independent oracle imports no checker code. It parses source JPEG APP1 XMP namespaces, verifies the actual JPEG end boundary and complete MP4 box layout with a video-track handler, hashes the exact appended range, then compares it with separately downloaded originals and actual destination links. All eight real source pairs use legacy MicroVideo offsets. Generated tests separately cover modern `Container:Directory`, explicit padding, malformed/truncated/contradictory XMP, unsupported layouts and byte-stream boundaries. The source preserves its original filenames and bytes throughout.

References are the [current Google Motion Photo specification](https://developer.android.com/media/platform/motion-photo-format), the [pinned AndroidX legacy XMP parser](https://github.com/androidx/media/blob/8c6678b657ede1e7883fc164ef73ed483c7796c3/libraries/extractor/src/main/java/androidx/media3/extractor/jpeg/XmpMotionPhotoDescriptionParser.java), and its [byte-layout implementation](https://github.com/androidx/media/blob/8c6678b657ede1e7883fc164ef73ed483c7796c3/libraries/extractor/src/main/java/androidx/media3/extractor/jpeg/MotionPhotoDescription.java). Legacy support is labeled separately; current Google metadata replaces those fields. No codec decoding or playback test is claimed.

An additional isolated user contains two byte-exact source Motion Photos and two component videos, uploaded before the stills so their links can be safely changed by the setup client. Ten actual Manager scans exercise five states in both modes: correct baseline, missing link, wrong video link, rejected reversed-link attempt, and restored baseline. Missing and wrong links produce the expected separate pair differences; checksum mode downloads no originals. Immich rejects video-to-image linking with HTTP 400 and leaves the inventory unchanged. Pure tests cover reversed and cyclic corrupt states that the server API refuses to create. Source hashes/mtimes and all four original hashes remain unchanged. Setup mutations are kept distinct from the checker, which issues zero writes.

The full controlled synthetic suite was rerun: clean libraries have zero attention findings, seeded differences remain visible, all 260 pagination originals verify, denied download permission yields actual HTTP 403, and missing album permission stays incomplete. Source-copy mutation, temporary destination album mutation/restoration, and delayed real-original timeout also pass. Latest sanitized evidence is under `docs/test-evidence/real-takeout/v0.1.3/`.

The final **installed 0.1.3 wheel passed 11/11 complete browser checks**, running outside the checkout with `PYTHONPATH` removed. Both modes exactly reproduce the independently audited 146-row reports, omitting only scan ID and creation time from equality checks. Pair and media-type filters, embedded offsets/hashes/actual links, current-container versus API classification, content-only matched counts, desktop/mobile layouts, JSON exports, offline HTML, history and reload all pass. No unexpected browser errors, warnings, external requests, credential URLs or browser-storage persistence occurred. Inter remains bundled locally with its license.

Cancellation and forced owned-process interruption each occurred in `Hashing destination originals`, after one of 62 originals and 4,375,823 bytes had completed, with a new response independently observed streaming at least 2 MiB. Stopped scans had no completed report. Reload/restart required reconnection, and each resume freshly downloaded all **327,044,331 bytes**, reproducing the entire expected report. One connection-refused browser event during the deliberate process kill is explicitly expected.

Final raw HTTP observations confirm all 62 CTF originals and seven album inventories unchanged, including all eight pair targets and six API type differences. All 123 source files retain identical paths, hashes, sizes and modification timestamps. Across the v0.1.3 backend, pair-fault and browser runs, the observer records **2,245 read requests, all HTTP 200, zero write attempts, 582 completed originals and four deliberate interrupted streams**. That combined ledger includes the preserved earlier browser attempt; the final browser receipt identifies the final run's own stream records. There are no pending records or recorder failures. After all explicit setup mutations were restored, the Docker audit finds **all 356 originals (401,456,805 bytes) and all 13 media/album table fingerprints unchanged**. That wider scope includes separate synthetic, pagination, pair-fault and upstream-derived accounts. Authentication and queue bookkeeping are outside the audited table set.

The normal preview serves the exact installed 0.1.3 package and its own completed original-mode report. After final audits, only this test project's three services and the owned observer were stopped; named volumes and saved evidence were preserved. Other Docker projects were not changed. The source and wheel packages are separately checked for CRC, current application/web bytes, versions, credentials, private runtime files and unwanted authorship labels.

The historical installed **0.1.2 wheel** passed **10 complete browser checks** using Chromium 156.0.8078.4 at 1505×1045 and 390×844. Its saved reports contain the earlier 22-attention result, before pairing/type checks. Both modes' full reports, parsed JSON exports, rendered offline HTML, filtering, pagination, hash evidence, saved history and reload agree with that version's independently checked backend reports; only the scan ID and creation timestamp differ. No browser errors, warnings, external requests, credential URLs or browser-storage persistence occurred.

Cancellation occurred while the actual scan was in `Hashing destination originals`, with one of 62 assets completed and 4,375,823 bytes transferred, while a new original response had streamed at least 1 MiB. The cancelled scan had no completed report. Reload required reconnection; resume freshly transferred all 327,044,331 destination bytes and reproduced the complete original-mode report. The normal preview also completed its own original-mode scan with the same full report.

The final clean browser observer recorded **487 read requests, all upstream HTTP 200, zero write attempts, 125 complete original responses and one deliberate interrupted original response**. Earlier instrumented attempts were kept separately: a Windows sharing conflict could prevent atomic ledger replacement while a reader held the file. The test-only recorder now retries those conflicts with a bounded limit and reports audit failures separately from transport interruptions; two regressions cover recovery and failure propagation. The complete browser flow was repeated after this fix, with no recorder errors or unfinished records except the intentional interruption.

An independent final raw-HTTP observation after the last browser run verified all 62 CTF originals and all seven album inventories unchanged. Source paths, hashes, sizes and modification timestamps stayed unchanged across all 123 files. The separate Docker-side audit also found **all 71 originals (329,163,482 bytes) and 13 media/album table fingerprints unchanged**; that wider server scope includes nine originals from the separate upstream-derived test account. No raw database/GPS fields are retained in that audit. Sanitized receipts are in `docs/test-evidence/real-takeout/`; the original media and raw account metadata remain outside the source bundle.

A second, smaller corpus from [immich-go's published regression data](https://github.com/simulot/immich-go/tree/6ee7ad550dfcdd89b3ee0a52bc3052c2d0aa3ffd/app/upload/TEST_DATA) is labeled **redacted Takeout-derived test data**, rather than an untouched export. It exposed unrecognized French album metadata. Version 0.1.2 adds conservative recognition of `mÃ©tadonnÃ©es.json`, preserving the asserted title and membership. Eleven generated-byte regression cases cover Unicode variants, photo-sidecar rejection, unknown JSON, conflicting names and empty titles. Numbered filename heuristics were not relaxed based on its zero-byte placeholders. The real-server recheck now asserts all eight members of the named French album, agrees with destination membership, preserves the unresolved blank title and reports the three unimportable empty-file placeholders as missing. All nine imported originals and both source and destination snapshots remained unchanged.

## Repaired real Takeout library — separate maintenance and full rerun

The six classification differences and two album omissions above were repaired in the same owned disposable Immich 3.3.3 library. The checker application remains version 0.1.3 and performs read-only verification. Its application and bundled interface bytes exactly match the previously installed wheel.

Before repair, independent direct HTTP and Docker-side observations confirmed all originals, links and memberships. A full custom-format database backup was saved privately. The source and original media volumes were preserved. Immich's [pinned public asset-update schema](https://github.com/immich-app/immich/blob/d2dac658fe1c67e8bbd08aa18200a32e5d45b9e4/server/src/dtos/asset.dto.ts) has no media-type field. A single guarded maintenance transaction therefore corrected exactly six proven MP4 records from `IMAGE` to `VIDEO`, checking owner, IDs, original paths and checksums. It asserted that the other 350 asset rows and every other target field were unchanged apart from normal update timestamps/IDs. Two standard album-membership API calls added the independently identified missing assets. The original 62 asset identities, filenames, paths, checksums, eight pair links and seven album identities were retained.

The six companions lacked native video metadata. Supported targeted metadata jobs populated it, and targeted native transcoding generated six playback derivatives. The server's complete configuration was saved privately; `ffmpeg.transcode` was temporarily set to `all` while only these six jobs ran, then the exact configuration was restored in `finally`. Storage-template migration was disabled throughout. Hidden companions remain hidden, so their native thumbnail jobs intentionally skip them and the parent photos retain their previews. Processing changed only the six targets' duration, rotation-correct dimensions, and normal update fields. Source-supported capture instants, links and repaired memberships remain exact.

All six real HTTP playback responses return `video/mp4`. Their exact downloaded bodies have valid video containers and decode completely with zero FFmpeg errors. An earlier verifier used the default null-output time base, which rounded variable-frame timestamps into duplicate output DTS. That instrumentation failure is retained separately; preserving the input time base verifies the same existing derivatives without rerunning jobs or changing media. Original `.jpg` names and paths are intentionally preserved, so original-download MIME hints remain extension-derived. Correct MP4 playback is supplied by the registered derivatives; later server transcoding policy can reevaluate those derivatives.

The independent repaired-library oracle establishes the following in both scan modes:

| Check | After repair |
| --- | --- |
| Original media content | 62/62 exact matches; zero missing or changed originals |
| Media classification | 62 agreements, zero differences; 53 images and nine videos |
| Paired relationships | Eight correct relationships at the selected original/checksum evidence level |
| Albums | Seven identities and full memberships match; zero album findings |
| Known capture epochs | All 53 source-supported instants match |
| Remaining attention | 12 rows: nine unavailable source dates and three rows for the unchanged auxiliary JSON |
| Report size | 144 findings; incomplete coverage remains explicit |

The unchanged checker passes 190 tests plus 24 subtests again, with the same single Windows symbolic-link privilege skip and TestClient deprecation warning. TypeScript/Vite rebuild successfully and reproduce the packaged interface bytes. The full live synthetic suite reuses all existing accounts and IDs with zero uploads or setup mutations: clean libraries have zero attention, seeded problems remain detected, all 260 pagination assets verify and permission failures remain incomplete. Source change, destination change/restoration and timeout tests pass again. Ten pairing fault-case scans reuse the existing isolated four-asset account, restore its baseline, and independently verify 40 content proofs, 40 media-type agreements and 20 pairing assertions.

The final installed-package browser rerun passes **11/11 checks** in Chromium at 1505×1045 and 390×844. Both full reports match the independently audited backend reports exactly apart from scan ID and creation time. The exact six previously incorrect asset IDs now show `VIDEO` agreements in the inspector; both album-category views have zero findings. Exports, offline HTML, pairing evidence, content-only match counts, mobile layout and reload pass. Cancellation and forced owned-process interruption each resume only after reconnection and freshly transfer all 327,044,331 bytes, reproducing the entire 144-row report. Source hashes, sizes and modification timestamps remain unchanged. There are no unexpected browser errors or warnings in the final run. A prior run's unattributed HTTP 403 remains preserved as a failed attempt; the stricter complete repeat records HTTP error origin/path/status/lifecycle and would accept a stale-session rejection only after checking its exact local response body during the deliberate restart. No HTTP 403 occurred in that final repeat, so the earlier event is not retroactively reclassified.

Final direct HTTP observations confirm the processed inventory, all 62 original hashes/sizes, eight pair targets, 62 correct media types, seven repaired memberships and all 53 known source capture instants unchanged after the browser and normal-preview scans. Across the repair and all checks, all 356 originals in the disposable server retain their IDs, SHA-256 and sizes (401,456,805 bytes). After explicit repair and processing, all 13 audited media/album table fingerprints remain unchanged during verification. The observer records 2,019 read requests, all upstream HTTP 200, zero write attempts, 520 completed original responses and four deliberate interrupted streams across both browser attempts and the other checks. There are no pending records or ledger-write failures. Explicit maintenance and processing requests are recorded separately from read-only checker traffic.

The complete browser rerun, independent source/raw-HTTP comparisons, scoped repair receipt and six playback decode proofs are recorded under `docs/test-evidence/real-takeout/remediation/`. Previous before-repair reports and failed instrumentation attempts remain preserved separately. After final observations only the owned observer and three test containers were stopped; named volumes and the private backup remain available. The normal installed-package preview stays open on its own completed repaired report.

## Version 0.1.4 date and auxiliary evidence

The remaining 12 post-repair attention rows were investigated against the unchanged source and raw destination evidence. Eight were video components without Takeout capture sidecars; three came from one empty auxiliary JSON; one was an edited JPEG with no reliable capture instant. This version resolves eleven rows without changing source or destination media or dates. The edited image remains explicitly unresolved.

The bounded streamed ISO BMFF inspector reads version 0/1 movie, track and media creation fields while the source is hashed. It requires a complete valid video container, nonzero representable dates, complete field pairs, and agreement across all inspected fields. All eight eligible real videos agree internally across 60 encoded fields and exactly match Immich `fileCreatedAt`. Their parent-photo capture epochs differ by one to three seconds, so no parent date is copied. These are nominal container creation timestamps, not shutter instants or camera-timezone proof. Apple's [movie creation field](https://developer.apple.com/documentation/quicktime-file-format/movie_header_atom/creation_time), [track creation field](https://developer.apple.com/documentation/quicktime-file-format/track_header_atom/creation_time), and [media creation field](https://developer.apple.com/documentation/quicktime-file-format/media_header_atom/creation_time) describe this metadata. Container fallback is blocked by associated, malformed, ambiguous or conflicting sidecars. Eligible unmatched videos remain in the container-date denominator with a separate unmatched count.

The exact known `shared_album_comments.json` parses as an empty object. Its three bytes, SHA-256 and SHA-1 stay in the inventory and a neutral auxiliary finding. It has no comments or media payload to migrate. Unknown empty JSON, nonempty comments metadata, parse failures and association candidates retain their previous unresolved/unsupported behavior. Auxiliary rows count neither as matched media nor as attention.

Independent examination of `2020-03-10/IMG_20200310_140416-EFFECTS-edited.jpg` found no Takeout sidecar, trustworthy EXIF offset or proved source lineage. Its XMP offset cannot be trusted: a control written with the same wall-clock pattern contradicts its own Takeout epoch by 3,599 seconds. The related original JPEG's GPS timestamp precedes its own explicit-offset capture instant by 15 seconds; the edited JPEG has no GPS timestamp. All 53 source JPEGs were checked for coding/entropy equivalence without finding a verified parent for the edit. No filename date, filesystem timestamp, borrowed timezone, stale GPS time or uncertain XMP instant is substituted. This investigation is recorded independently; the application's general policy remains conservative rather than hard-coding that filename.

| Final report evidence, both modes | Result |
| --- | --- |
| Inventoried source | 123 files / 327,085,591 bytes |
| Inventory roles | 62 media, 53 sidecars, seven album metadata files, one empty auxiliary file |
| Content | 62 matches / 327,044,331 media bytes |
| Media types, pairs and albums | 62 agreements, eight relationships, seven matching albums |
| Capture instants | 53 asserted, comparable and agreeing; eight container-only dates remain separate |
| Nominal container dates | Eight comparable and agreeing; zero differences or unmatched eligible sources |
| Remaining attention | One edited-photo date; coverage explicitly incomplete |
| Total findings | 195: 62 content + 62 types + eight pairs + 53 capture + eight container + one unresolved date + one neutral auxiliary |

The final production code passes 247 automated tests plus 28 subtests, with one Windows symbolic-link privilege skip and the existing TestClient deprecation warning. New cases cover bounded creation-field parsing, invalid/zero/conflicting dates, narrow auxiliary classification, sidecar precedence, positive date provenance and unmatched denominators. The final real backend reports pass independent assertions for every row, content/date/hash field and inventory count. The final controlled live suite again verifies both modes, clean/seeded fixtures, 260-original pagination and denied permissions with existing accounts and zero uploads or setup mutations. Three live failure scenarios and ten pair-fault scans passed and restored their baselines before the last denominator/finite-input review change; their original receipts remain intact and are not presented as installed-wheel executions.

The full installed-wheel browser run passes **11/11 checks** at 1505×1045 and 390×844, including both modes, exact full-report equality, date provenance and auxiliary filters, parsed JSON exports, offline HTML rendering and reload. Neutral auxiliary evidence is excluded from Content matched and Needs attention. Cancellation and forced owned-process interruption happen during independently observed active original responses after 3 MiB and 1 MiB respectively; both resumes reconnect and freshly transfer all 327,044,331 bytes. There are no unexpected browser errors, warnings or external requests. One expected connection-refused event comes from the deliberate process interruption; no HTTP 403 occurs. A first scratch-run selector ambiguity is preserved separately, and the full successful run uses fresh state.

Final raw HTTP observations preserve the complete CTF inventory, all 62 original hashes/sizes, all 53 capture instants, eight nominal container dates, eight links and seven matching albums. All 123 source hashes, sizes and mtimes are exact. The final container-side before/after audit confirms all 356 stored originals (401,456,805 bytes) and all 13 media/album table fingerprints unchanged during final verification. The transparent observer records 1,547 read requests, all HTTP 200, zero write attempts, and two deliberately interrupted original responses, with no pending records or ledger-write failures. Earlier pair-fault setup writes use a separate setup client and precede the final table baseline; they are not counted as checker requests.

Evidence is retained under `docs/test-evidence/real-takeout/date-coverage/`. The main preview runs the installed 0.1.4 wheel and shows its own completed 195-row original-byte report. After observations, only the owned observer and three test containers are stopped; their named volumes and the existing private backup are preserved.

## Remaining release gates

- Expand real-export coverage beyond this 2020 training Takeout: recent supplemental-metadata variants, other languages, personal libraries and other Immich versions remain unvalidated.
- CI is configured but has not run on a remote repository. Windows is locally tested; Linux is a CI target, not a locally verified platform.
- Native folder-picker interaction has not been automated. Path entry is browser-tested. Large-library throughput, HEIC / RAW decoding, other live-photo formats, codec playback and accessibility assistive technologies are unvalidated. The eight legacy Google Motion Photo relationships above are byte-verified; they do not establish support for every pairing format.

Original mode deliberately re-downloads originals when a stopped scan resumes. Checkpoint reuse is not promoted to current byte proof. Cancellation may wait for an in-flight network request to finish or time out. Inventory rechecks do not create an atomic snapshot or detect all disk changes after a hash observation.
