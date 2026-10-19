# Photo Migration Checker

A free, open-source, local, read-only Google Takeout to Immich verification tool. Compare an extracted export against the assets and albums your Immich API key can read. Inspect the evidence and export an offline HTML or JSON report.

**Release candidate, version 0.1.5rc1.** The app keeps uncertainty visible, including the one edited-photo date that cannot be established reliably from the tested export. See [release notes and installation details](docs/RELEASE.md), [changes](CHANGELOG.md), and [test evidence](docs/TESTING.md).

The 0.1.4 verification baseline used real disposable Immich 3.3.3, controlled migration problems, and the Google Photos portion of Magnet's published 2020 forensic-training Takeout, independently migrated with immich-go 0.32.0. Both modes verified 62 content matches, 62 media-type agreements, eight motion-photo relationships, seven matching albums, 53 Takeout capture instants and eight separately labeled nominal container dates. One empty auxiliary JSON remains inventoried. The 195-row report retains one attention finding for the edited photo's source date. These results validate the tested sample and workflow; other export variants remain unvalidated. The release's final validation is recorded separately in the test evidence.

This checks the supplied export. It cannot prove Google exported everything. **Keep your originals.**

## Quick start

Requires Python 3.11 or newer. See the [platform-validation table](docs/TESTING.md#platform-validation) for the exact operating systems, interpreter versions and checks exercised for this candidate. The source release and wheel include the built interface and local Inter fonts, so running either does not require Node. The bundled code's [third-party notices](pmc/web/THIRD-PARTY-NOTICES.txt) and [Inter font license](pmc/web/INTER-LICENSE.txt) are included. Installing dependencies may require internet access. Runtime requires no paid API or cloud account. There is no telemetry or background startup service.

Windows PowerShell, from the extracted project folder:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install .
.\.venv\Scripts\python.exe -m pmc --data-dir .\private-checkpoints
```

Equivalent macOS / Linux commands are below. Consult the platform-validation table for Linux results; macOS remains unvalidated.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/python -m pmc --data-dir ./private-checkpoints
```

Open **http://127.0.0.1:8765**. Leave the terminal open; Ctrl+C stops the app. It binds only to loopback. The explicit data directory above keeps scan history and checkpoints together. Keep it outside the selected Takeout folder. Without `--data-dir` or `PMC_DATA_DIR`, the default is `.pmc` relative to the directory where the app starts. To select another port:

```sh
python -m pmc --port 8766 --data-dir ./private-checkpoints
```

Use the virtual environment's Python for that command; activating the environment makes `python` available. On Windows you can also run `scripts/run-local.ps1 -Python python` with a working Python command or `-Python C:\path\to\python.exe`. That helper starts from the project directory and uses its default `.pmc` data directory. The Microsoft Store placeholder is not a Python installation. Wheel installation, upgrades, backups and uninstall steps are in the [release guide](docs/RELEASE.md).

## First sample scan

1. At **Source**, select **Try the sample**. Choose the sample with seeded problems or the clean sample. The app explicitly creates small synthetic media in its local data directory; no personal files are used.
2. The sample preselects its local destination and opens **Scan**. It is clearly labeled and does not contact an Immich server. Actual libraries go through the **Destination** connection screen.
3. At **Scan**, choose **Original bytes** and accept the displayed transfer scope. The fixture adapter reads real local original bytes with the same streaming hashing interface.
4. Inspect **Results**, filter findings, select a row to view the hashes, paths and explanation, then export HTML and JSON.

The clean sample has eight source occurrences and seven distinct originals. One duplicate appears in two albums. It should report eight content matches and zero attention findings. The problem sample includes omitted originals and an edit, changed bytes, a date difference, missing album membership, duplicate album names, malformed / ambiguous sidecars, timezone uncertainty, video, paired components, and unsupported files. Exact expectations are in `tests/fixtures/expected.json`.

## Scan an actual library

1. Extract Takeout yourself and select the folder using the native picker or its path. ZIP extraction is outside this release. Nothing in the selected source tree is written.
2. In Immich, create a dedicated API key with **asset.read** and **album.read**. Add **asset.download** only for original-byte verification. Enter it in the local password field. Never paste a key into an issue or chat. Keys stay only in the app process and disappear when it stops. Reconnect after restarting.
3. Enter the server's base HTTP(S) URL. Credentials, queries and fragments in URLs are rejected; redirects are not followed. HTTPS is recommended when traffic leaves the same computer. The adapter targets the source-reviewed 3.3.3 contract; other major versions are refused, and checksum proof is disabled outside exactly 3.3.3.
4. Review the source and accessible destination scope. **Checksum mode** reads stored server evidence and does not download originals. **Original mode** streams **every accessible active destination original**, including unrelated items, to find matches independently of server checksum provenance. It can transfer the entire accessible collection. The preview shows known total sizes and counts unknown sizes; there is no transfer quota. Choose this mode explicitly before it starts.
5. Keep both collections stable while scanning. Cancel is cooperative between chunks / requests. An in-flight request can take up to its timeout before cancellation is observed. Reconnect to the same server to resume a cancelled or interrupted scan. The scan ID and durable checkpoints remain; source and destination are re-enumerated. **Originals are downloaded again on resume** because unchanged database metadata cannot prove unchanged disk bytes. This favors evidence quality over transfer savings.
6. Review coverage and unresolved cases before interpreting matches. Exporting creates a local download. Reports contain relative filenames, album names, dates, hashes and destination asset IDs; they may be sensitive. They omit API keys, server URLs, absolute source roots and GPS fields. SQLite checkpoints retain a source root for resume; protect the data directory.

## Evidence levels

| Finding | Meaning |
| --- | --- |
| Verified original bytes | Downloaded `original?edited=false`, SHA-256 matches source. Download buffers are discarded. |
| Server-reported checksum match | Source SHA-1 matches a documented stored upload checksum; does not attest current bytes. Disabled for external-library / unknown provenance. |
| Possible match | Filename suggests a relationship, without compatible content proof. |
| Missing / mismatched | No content match in the completed accessible evidence scope, or same name with independently different bytes. Read the scan's mode and coverage. |
| Inaccessible / unsupported / unresolved | The available evidence cannot settle the case; coverage stays visibly incomplete. |
| Verified paired original bytes | Validated source Motion Photo XMP bounds and embedded video structure, whole-image SHA-256, and the actual linked video's current SHA-256 and size all agree. |
| Stored paired-media relationship | Compatible stored image/video SHA-1, reported component size and actual link agree with the validated source pair; current destination bytes were not downloaded. |
| Capture date agrees | A content-matched original's `fileCreatedAt` agrees with its asserted Takeout `photoTakenTime` instant within one second. |
| Container creation timestamp agrees | A sidecar-free video's validated movie/track/media creation fields agree internally and with `fileCreatedAt` as nominal UTC. This is container metadata, not proof of shutter time or original camera timezone. |
| Empty auxiliary metadata | The recognized `shared_album_comments.json` contains an empty JSON object. Its bytes and hashes remain inventoried with a neutral status; no destination media asset or comment payload is expected. |
| Media type agrees / difference | Source container structure establishes IMAGE or VIDEO and is compared with Immich's API type. Original mode also inspects the downloaded container. Filename extensions are only hints. |

Source occurrences are kept individually. Identical content can legitimately map to one Immich original; edited bytes remain separate. Filename, size, date and collection counts never prove equality. Albums are compared through matched membership, including duplicate names. Ordinary source directory names are hints; only recognizable album metadata asserts album membership. English `metadata.json` and French `métadonnées.json` are supported; empty or conflicting titles stay unresolved. Capture epochs, unknown original camera timezones and filesystem dates remain separate.

Pairing checks support Google JPEG Motion Photos with modern `Container:Directory` metadata or separately identified legacy MicroVideo offsets and an appended MP4/MOV video track. The embedded video is hashed from its validated exact byte range; a standalone exported component can corroborate it but is not required. Missing, wrong, reversed and cyclic destination relationships are reported separately from media classification. Unknown source pairing formats and inaccessible or ambiguous targets remain unresolved. Reports use schema version 3; existing saved version 1 and 2 reports remain readable.

## Build and test from a checkout

Requires Node 22+ and pnpm (tested with 11.25.0) in addition to Python. A plain Git checkout needs the frontend build before packaging:

```sh
pnpm --dir frontend install --frozen-lockfile
pnpm --dir frontend build
python -m pip install -e ".[test]"
python -m pytest -q
python -m pmc
```

The frontend build runs TypeScript and Vite, then copies the result into `pmc/web`, including bundled dependency notices. For the pinned validation dependency set, install `requirements.txt` first; `requirements.lock` remains a compatible entry point to those same pins. The standard manifest lets dependency monitoring inspect the exact transitive versions. The platform-validation table identifies the Python versions actually exercised. CI is configured to build the UI and wheel and run deterministic tests on Windows and Linux. Real-server testing uses `scripts/immich_integration.py --run` and requires a working Docker Linux engine; its explicit setup writes are restricted to a fresh disposable stack. The application never imports that harness. The test-only observer, failure checks and storage audit are described in [the live test notes](docs/TESTING.md).

## Scope and limitations

- Extracted folders, one local scan worker, sequential streamed hashing / downloads. Metadata inventories are held in memory and stored in SQLite. No whole media file is loaded into memory.
- Readable active, non-locked assets, including readable shared-album assets; API visibility and permissions limit scope. This cannot claim server-wide or Google-account completeness.
- No upload, repair, deletion, automatic fix, remote thumbnail fetch, or telemetry in the application. The only permitted POST to Immich is read-only metadata search. See [API evidence](docs/immich-contract.md).
- Container structure inspection supports JPEG, PNG, MP4/MOV with video tracks, and AVI. Recognized extensions also permit content hashing for other formats, but their media type remains unresolved. No codec, decoded-pixel, playback or perceptual-equivalence claim is made. Embedded EXIF extraction is not implemented: capture comparison currently uses Takeout JSON `photoTakenTime` versus Immich `fileCreatedAt`. Sidecar-free MP4/MOV videos may separately compare nonzero, complete and mutually agreeing ISO BMFF creation fields as nominal container dates. Malformed, conflicting or ambiguous sidecars never fall back to these fields. Other missing trustworthy dates remain unresolved.
- No ZIPs, other photo services, automatic pairing reconstruction, or automatic correction. Pair verification reads existing evidence and links without changing them. HEIC / RAW bytes can be hashed without decoding, but their real server behavior is unvalidated here. Other pairing formats and containers remain unvalidated.
- Rehashing and re-enumeration detect observable source and database changes. Immich provides no atomic snapshot, and disk changes after a download may escape observation. Work against stable collections.
- Symlinks, junctions and non-regular files are surfaced and skipped. The scanner checks for replacement while reading; a hostile local process racing filesystem operations is outside the protection claim.
- HTML and JSON exports are supported. CSV is intentionally absent. No spreadsheet formula interpretation is introduced.

See the [release guide](docs/RELEASE.md), [changelog](CHANGELOG.md), [architecture](docs/ARCHITECTURE.md), [test evidence](docs/TESTING.md), and [MIT license](LICENSE).
