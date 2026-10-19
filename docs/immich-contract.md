# Immich contract

Contract researched against official **v3.3.3**, commit `d2dac658fe1c67e8bbd08aa18200a32e5d45b9e4`, on October 18, 2026. This records source/document review; it is separate from live integration results.

The official API home is [api.immich.app](https://api.immich.app/). The immutable [release OpenAPI specification](https://github.com/immich-app/immich/blob/d2dac658fe1c67e8bbd08aa18200a32e5d45b9e4/open-api/immich-openapi-specs.json) is the endpoint/permission reference used here.

| Request, relative to `/api` | Minimum key permission | Purpose |
| --- | --- | --- |
| `GET /server/version` | None | Record version |
| `POST /search/metadata` | `asset.read` | Read assets and album memberships |
| `GET /assets/{id}` | `asset.read` | Recheck an asset |
| `GET /albums`, `GET /albums/{id}` | `album.read` | Read album metadata |
| `GET /assets/{id}/original?edited=false` | `asset.download` | Stream original bytes |

The checker needs `asset.read` and `album.read`, plus `asset.download` when original-byte verification is chosen. It uses `x-api-key` headers. It does not need an all-permissions key. Search is a read operation despite its POST method; every other POST, PUT, PATCH, and DELETE is prohibited in the checker adapter.

## Enumeration and coverage

For v3.2 and later, enumerate using `{"size":250,"withExif":true,"withStacked":true,"filter":{"trashedAt":{"eq":null}}}`, following `assets.nextCursor` in the next request's `cursor` until null. For each album add `albumIds:{"any":["album-id"]}` to the same filter and follow the same cursor. Maximum page size is 1000. In v3.3.3, album detail responses have no `assets` collection. `assets.total` is deprecated and is only the page count in the server implementation; it cannot establish collection coverage.

Older supported adapters can use the deprecated flat shape `{"page":1,"size":250,"withExif":true,"withStacked":true}`, following `assets.nextPage`, and use top-level `albumIds:["album-id"]`. Do not mix new filter/cursor fields with the legacy page shape. Pagination failures must remain visible and prevent a complete-coverage result.

Search scope is active assets belonging to the key owner or eligible timeline-enabled partners, plus active assets enumerated from readable albums. Locked media requires elevated access and is excluded from ordinary key scans. Readable albums can include shared albums. IDs identify albums; duplicate names are valid. Compare matched member IDs instead of names or counts alone. The active-only filter is required explicitly: the new v3 search does not default-exclude trashed assets. Unexpected trashed results are excluded and flagged as incomplete coverage.

`withStacked:true` preserves all stacked asset rows. The [query builder](https://github.com/immich-app/immich/blob/d2dac658fe1c67e8bbd08aa18200a32e5d45b9e4/server/src/utils/database.ts) applies a stack filter only when the option is false. The response's `stack` field contains relationship metadata; it is not a nested substitute for those asset rows.

The v3 cursor encodes an offset; it is not a snapshot. Re-enumeration can detect observable changes during the scan, but cannot make the remote server transactionally consistent. The checker retains only IDs, filenames, content checksum/provenance hints, capture/local/update dates, pairing/edit/stack/status fields, and EXIF byte size. It discards server paths, GPS, and account details before persistence. Change detection compares that evidence subset and album membership. It cannot detect an unreported disk edit after original bytes were downloaded, or a change that is reverted before the next observation. Evidence: [search service](https://github.com/immich-app/immich/blob/d2dac658fe1c67e8bbd08aa18200a32e5d45b9e4/server/src/services/search.service.ts).

## Checksums and original bytes

The [asset response schema](https://github.com/immich-app/immich/blob/d2dac658fe1c67e8bbd08aa18200a32e5d45b9e4/server/src/dtos/asset-response.dto.ts) describes `checksum` as base64 SHA-1. Uploaded assets are created with `sha1` file-content provenance. However, the same release creates external-library assets with SHA-1 of `path:` followed by the server file path. The algorithm field exists internally but is not included in asset responses. See the [algorithm enum](https://github.com/immich-app/immich/blob/d2dac658fe1c67e8bbd08aa18200a32e5d45b9e4/server/src/enum.ts) and [external-library construction](https://github.com/immich-app/immich/blob/d2dac658fe1c67e8bbd08aa18200a32e5d45b9e4/server/src/services/library.service.ts).

Consequently, a source SHA-1 match to a valid 20-byte decoded checksum is only **server-reported checksum evidence**. It does not verify that current stored bytes are readable or unchanged. External assets with non-null `libraryId` need original downloads; nonmatching path checksums cannot prove missing content. Unknown provenance, stale database values, and SHA-1 collision limits must remain explicit.

Independent original verification streams `GET /assets/{id}/original?edited=false` and computes SHA-256. The [original-download service](https://github.com/immich-app/immich/blob/d2dac658fe1c67e8bbd08aa18200a32e5d45b9e4/server/src/services/asset-media.service.ts) serves `originalPath` with `edited=false`; playback may serve transcoded video and is unsuitable. Shared links force edited content and therefore are not supported credentials. `isEdited` and `livePhotoVideoId` identify relationships requiring care; an edit recipe does not prove preservation of a separately exported edited file.

## Disposable integration harness

`python scripts/immich_integration.py --prepare-only` prepares isolated fixtures and a pinned Docker Compose stack. `python scripts/immich_integration.py --run` starts that disposable stack, uses setup-only writes to seed separate clean, problem, and pagination accounts, then invokes the real Manager and records redacted evidence. Use `--keep` only when keeping this disposable stack for browser testing; by default the harness tears down its own project and volumes. Generated Compose dependencies wait for database and Redis health, avoiding first-boot connection races. Containers have no restart policy and nothing starts at boot.

For a stack already started from a harness-owned folder, `--suite-existing-work <prepared-folder> --work-dir <fresh-evidence-folder>` runs the extended suite without starting or stopping containers. This mode checks the ownership marker and fixed loopback endpoint. `--extra-video <controlled-file.mp4>` adds a supplied H.264 MP4 to the problem fixture. The setup harness is deliberately separate from the app and must not be pointed at a personal server.

The live suite verifies images and AVI videos, omitted original/edit, changed bytes with a matching filename, duplicate occurrences, album membership and identity, empty albums, capture dates, malformed/ambiguous sidecars, uncertain timezone and unresolved filename-only paired-media hints. Version 0.1.3 additionally verifies eight genuine Google Motion Photo relationships using exact embedded-video hashes and actual `livePhotoVideoId` originals, and separately reports six byte-derived video versus API `IMAGE` classification differences. Isolated setup link mutations prove missing/wrong pair detection; the server rejects a reversed video-to-image link with HTTP 400. The suite uploads 260 unique originals to cross the 250-result pagination boundary, checks original download denial with a key lacking `asset.download`, and checks incomplete coverage with a key lacking `album.read`. Before taking preservation snapshots, the separate setup administrator observes `GET /queues` until media queues have no pending work and five consecutive inventories are stable, bounded by 180 seconds. EXIF size alone is insufficient: asynchronous thumbnail/video work can update asset timestamps after it appears. These administrative queue reads are harness preparation, not additional checker permissions.

The harness independently hashes source files and destination originals before and after checker execution. Inventory drift produces saved field-level differences and a failure stating that the destination changed while testing; drift alone is not attributed to checker writes. Only the setup client performs writes; checker request ledgers must contain GET or metadata-search POST exclusively. Test credentials stay in a private scratch state file, outside reports and application persistence.

Actual test execution and detailed results belong in `docs/TESTING.md` and run evidence. The development host's initial Docker startup failure was recovered before the real v3.3.3 suite was executed. No factory reset or secret-store manipulation was performed. Controlled synthetic media validation remains distinct from validation against a permissioned real Takeout sample.
