# Changelog

## 0.1.5rc2 - Private launch sessions

- Require the current launch capability for every local API endpoint, including bootstrap, so an unrelated loopback client cannot obtain API access by requesting a token.
- Reserve the loopback endpoint before printing its private launch link. An occupied port exits without exposing a link.
- Remove the link's private fragment before API requests and keep the capability in tab session storage for reloads. Opening a new launch link also works in an existing tab. If storage is blocked, the current tab works in memory and a reload requires reopening the link.
- Rotate the capability on each launch while retaining saved reports and reconnecting to Immich as before. Protect terminal output, browser storage and checkpoint files with the account's existing access controls; this is capability access, not operating-system identity authentication.
- Keep the source and packaged interface aligned at Python `0.1.5rc2` / frontend `0.1.5-rc.2`. Existing release assets remain unchanged.

## 0.1.5rc1 - Release candidate

- Package the local app for release with installation, upgrade, backup, data-retention and uninstall instructions.
- Include the exact MIT notices for bundled React 19.3.1, React DOM 19.3.1 and scheduler 0.28.0 in [third-party notices](pmc/web/THIRD-PARTY-NOTICES.txt), alongside the existing [Inter SIL Open Font License](pmc/web/INTER-LICENSE.txt).
- Align Python release metadata (`0.1.5rc1`) with frontend prerelease metadata (`0.1.5-rc.1`).
- Exclude accidentally placed private state, SQLite databases and sidecars, database dumps, keys and logs from source archives, with a packaging regression check.
- Preserve the conservative date policy: an edited image without a reliable source capture instant remains flagged. No source or destination dates are changed.
- Use the singular label for one attention finding.
- Retain the schema 3 distinction between Takeout capture instants, nominal video-container dates and neutral auxiliary metadata. Saved schema 1 and 2 reports remain readable.
- Correct the README's encoding for the French album-metadata filename and clarify the tested platform and export scope.

Final validation for this candidate is documented in [test evidence](docs/TESTING.md), including the [platform-validation table](docs/TESTING.md#platform-validation). A release candidate does not establish support for untested Takeout variants or Immich versions. See the [release guide](docs/RELEASE.md) for the distribution checklist and remaining limitations.

## 0.1.4 - Date and auxiliary evidence

- Add bounded streamed ISO BMFF creation-field inspection for eligible sidecar-free videos. Complete, nonzero, mutually agreeing fields may establish a nominal container date, separately from capture time and original camera timezone.
- Report positive Takeout capture-date evidence and date provenance. Malformed, ambiguous or conflicting sidecars prevent container fallback.
- Keep the exact recognized empty `shared_album_comments.json` hashed and inventoried as neutral auxiliary evidence, outside media matches and attention counts. Unknown or nonempty JSON keeps its conservative handling.
- Add schema 3 date and inventory coverage, filters and evidence details while retaining older saved reports.

The real 2020 forensic-training Takeout baseline contains 62 media matches, 62 media-type agreements, eight verified motion-photo relationships, seven matching albums, 53 agreeing capture instants and eight agreeing nominal container timestamps. Its 195 findings include one unresolved edited-photo date and one neutral auxiliary record. The last date is not recoverable reliably from the available export evidence.

## 0.1.3 - Pairing and media types

- Validate supported Google JPEG Motion Photo metadata, exact embedded-video ranges and component hashes against actual destination relationships.
- Compare supported source container structures with Immich media classifications. Filename extensions alone do not establish media type.
- Keep pairing, media classification, content and album evidence separate in results and exports.

## 0.1.2 - Real-export compatibility

- Recognize conservative French album metadata alongside English album metadata.
- Retain unknown, conflicting and empty album titles as unresolved evidence.
- Expand real-server, installed-package and lifecycle validation.

## 0.1.0 and 0.1.1 - Initial local verification

- Provide read-only extracted-Takeout comparison against accessible Immich originals and albums.
- Support streamed original-byte verification, narrowly scoped stored-checksum evidence, durable scan history, cancellation and restart recovery.
- Include explicit local samples, a loopback browser interface, and offline HTML and JSON reports.
