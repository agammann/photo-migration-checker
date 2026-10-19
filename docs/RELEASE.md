# Release guide

Version **0.1.5rc1** is a release candidate for Photo Migration Checker. The MIT-licensed application verifies an extracted Google Photos Takeout against the Immich assets and albums visible to a supplied read key. It does not migrate, repair or delete a library. Keep the original export and independent backups.

The runtime packages contain the built interface, [MIT notices for bundled React, React DOM and scheduler](../pmc/web/THIRD-PARTY-NOTICES.txt), and locally bundled Inter fonts with their [SIL Open Font License](../pmc/web/INTER-LICENSE.txt). Node and Docker are unnecessary for normal use. Docker is used only by the separate real-server test harness. Python 3.11 or newer is required. The [platform-validation table](TESTING.md#platform-validation) records the exact operating systems, interpreter versions and checks exercised for the final candidate; macOS remains unvalidated.

This candidate aligns Python's `0.1.5rc1` version with the frontend's `0.1.5-rc.1` metadata, corrects the singular attention label, and excludes private state, SQLite databases and sidecars, database dumps, keys and logs from source archives. A regression check covers private files accidentally placed within otherwise allowed source directories. These exclusions supplement the final package-content and credential audit.

## What this candidate covers

Original mode downloads every accessible active destination original, including unrelated assets. It hashes the current response bytes and discards the buffers. Checksum mode avoids those downloads and uses only compatible stored evidence under the source-reviewed Immich 3.3.3 contract. Checksum proof is disabled outside exactly 3.3.3; other major versions are refused. Review the transfer scope before starting original mode.

The established real-export baseline uses the Google Photos portion of Magnet's published 2020 forensic-training Takeout, imported with immich-go 0.32.0 into a disposable Immich 3.3.3 instance. Both modes produce 195 findings, including 62 content matches, 62 media-type agreements, eight motion-photo relationships, 53 capture-date agreements, eight nominal container-date agreements and one neutral auxiliary record. All seven source albums match. One edited-photo date remains an attention finding because the export supplies no reliable capture instant. A matching container timestamp never establishes shutter time or original camera timezone.

That unresolved finding is expected. It does not indicate missing or changed photo bytes. No capture date is substituted from a filename, filesystem timestamp, uncertain embedded timezone or unproved parent relationship. Final candidate test results and their limits belong in [TESTING.md](TESTING.md); historical results are not a substitute for testing the packaged candidate.

Recent supplemental-metadata variants, other languages, personal libraries, other Immich versions, very large libraries, HEIC / RAW decoding and other live-photo formats remain unvalidated. Native folder-picker interaction and assistive technologies are not covered by the automated browser checks. The app performs structural container checks, not general codec or perceptual-equivalence verification. An inventory recheck cannot create an atomic server snapshot.

## Verify the download

Use the SHA-256 value delivered with the specific release artifact. Check the wheel and source bundle separately. A matching hash detects a difference from that published artifact; an unsigned checksum alone does not establish publisher identity.

Windows PowerShell, replacing the filename with the artifact being checked:

```powershell
Get-FileHash -LiteralPath .\photo_migration_checker-0.1.5rc1-py3-none-any.whl -Algorithm SHA256
```

On macOS use `shasum -a 256 <artifact>`; on Linux use `sha256sum <artifact>`. Compare the complete digest before installation. Do not install from the private test workspace or copy its credentials, media or checkpoint directories into a release.

## Install the wheel

Create a dedicated application directory outside the Takeout source tree. Place the wheel there and run these PowerShell commands from that directory:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install .\photo_migration_checker-0.1.5rc1-py3-none-any.whl
.\.venv\Scripts\python.exe -m pmc --data-dir .\private-checkpoints
```

Dependency installation may need internet access. No paid API or cloud account is required. If `py` cannot find a working Python installation, install Python 3.11 or newer first; the Microsoft Store placeholder alone cannot create the environment.

The equivalent macOS / Linux commands are below. Consult the platform-validation table for Linux coverage; macOS remains unvalidated.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install ./photo_migration_checker-0.1.5rc1-py3-none-any.whl
.venv/bin/python -m pmc --data-dir ./private-checkpoints
```

Open **http://127.0.0.1:8765/**. Leave the terminal open while using the app. Ctrl+C stops it; no startup service or scheduled task is installed. To use another port, add `--port 8766` to the launch command. Refresh the browser after restarting because each process has a new local session token.

For the source release, extract the bundle, open a terminal in its `photo-migration-checker` directory, and replace the wheel-install command with the following:

```powershell
.\.venv\Scripts\python.exe -m pip install .
```

The source release includes `pmc/web`; a plain Git checkout needs a frontend build first. See the [checkout instructions](../README.md#build-and-test-from-a-checkout). `requirements.lock` records the Python environment used for validation; it includes test dependencies as well as runtime dependencies. Installing the wheel normally resolves its declared runtime dependencies.

## Data and credentials

`--data-dir` selects the checkpoint directory. With no argument, `PMC_DATA_DIR` is used when set; otherwise the default is `.pmc` beneath the directory from which the app starts. Always use the same explicit path to reopen the same history, and keep that path outside the selected source tree.

The directory contains `scans.sqlite3`, scan reports, source manifests and original-hash checkpoints. Resume data includes the absolute source root and normalized destination URL. Samples requested through the interface create synthetic files beneath its `samples` directory. Treat the entire data directory as private. Exported HTML and JSON omit API keys, server URLs, absolute source roots and GPS fields, but still contain potentially sensitive filenames, album names, dates, hashes and asset IDs.

API keys live only in the application process. Reconnect after stopping or restarting it. Use a dedicated key with `asset.read` and `album.read`; add `asset.download` for original-byte verification. Revoke that key in Immich when it is no longer needed. The app does not write a credential file or browser credential store.

Downloads made through the report-export buttons are separate files at the browser's chosen download location. The app does not delete them when stopped or uninstalled. Original-download byte buffers are discarded; the checker does not keep a second media library.

## Upgrade and rollback

1. Export any reports you want to keep separately. Stop the existing app with Ctrl+C and wait for its process to exit. Do not copy a running SQLite database.
2. Copy the **entire** private checkpoint directory to a new backup location. Keep the old wheel or source bundle and its virtual environment if you need a rollback.
3. Install the new wheel into the dedicated environment. Start it with the exact same `--data-dir` path, then reconnect to the same Immich server. Saved reports retain the evidence and schema of the version that created them; run a new scan for fresh verification.

For an existing installation using the example directory names:

```powershell
Copy-Item -LiteralPath .\private-checkpoints -Destination .\private-checkpoints-backup-before-0.1.5rc1 -Recurse
.\.venv\Scripts\python.exe -m pip install --upgrade .\photo_migration_checker-0.1.5rc1-py3-none-any.whl
.\.venv\Scripts\python.exe -m pmc --data-dir .\private-checkpoints
```

Choose a backup destination that does not already exist. If the previous installation used the default `.pmc`, substitute that directory in both the backup and launch commands. A cancelled, failed or interrupted scan may resume after reconnection, but source and destination inventories are rechecked and **all accessible originals are downloaded again** in original mode. No stopped scan becomes a completed proof merely by reopening the app.

For rollback, stop the new app, preserve its directory separately, reinstall the saved previous artifact in its own environment and point it at a separate copy of the pre-upgrade backup. Do not merge SQLite files or assume an older version can open data written by a newer version.

## Uninstall and retain or erase data

Stop the app first, then uninstall the package from its dedicated environment:

```powershell
.\.venv\Scripts\python.exe -m pip uninstall photo-migration-checker
```

This removes the installed package and command. It retains dependencies, the virtual environment, checkpoint data, source bundles and separately exported reports. You may remove the dedicated virtual environment once you no longer need it.

To erase retained app data, delete only the specific checkpoint directory selected by `--data-dir`, `PMC_DATA_DIR` or the default launch-directory `.pmc`, together with any backups and exported reports you intend to erase. Check the resolved path before deleting it. Uninstalling or deleting checkpoint data does not revoke the Immich key; revoke it in Immich separately. The Takeout source and destination library are not part of uninstall cleanup.

## Release checklist

The release owner records evidence for each gate before publishing:

- Align the Python package, CLI/API version, frontend package metadata and release filenames; include this guide, README, changelog, project MIT license, bundled dependency MIT notices and Inter license.
- Build the frontend from the frozen lockfile. Run deterministic tests and the owned real-server suite against the final source, preserving the expected unresolved date.
- Build a clean wheel and source archive. Install the wheel in a fresh environment outside the checkout, check its version and exercise the complete browser flow in both modes, including exports, mobile layout, cancellation, process interruption and fresh-download resume.
- Compare the final reports with independent source and raw Immich evidence. Verify source preservation, server original hashes and the scoped media/album table audit. Record checker read requests separately from any explicit disposable-fixture setup writes.
- Check every packaged application and web payload byte against the final source. Check archive integrity, license inclusion, documented commands, private-file exclusions and credentials before producing SHA-256 digests.
- Record final counts, exact tested versions, skipped checks and remaining unvalidated scope in [TESTING.md](TESTING.md) and the accompanying receipt. Remote CI success and publication require their own observed evidence.

Release preparation creates local reviewable artifacts. It does not itself publish a repository, package or release. The read-only application never performs the disposable test harness's imports, fixture mutations or maintenance actions.
