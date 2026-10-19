"""Small allowlisted read-only Immich adapter. No write operation is exposed."""
from __future__ import annotations

import base64
import hashlib
import json
import re
import threading
from urllib.parse import urlsplit, urlunsplit

import httpx

from .media import MediaCancelled, MediaInspector


class Cancelled(Exception):
    pass


class ImmichError(Exception):
    """A deliberately sanitized error, safe for a local report."""


def normalize_url(url: str) -> str:
    p = urlsplit(url.strip())
    if p.scheme not in {"http", "https"} or not p.hostname or p.username or p.password or p.query or p.fragment:
        raise ValueError("Enter an HTTP(S) server URL without credentials, query, or fragment.")
    path = p.path.rstrip("/")
    if path.endswith("/api"):
        path = path[:-4]
    return urlunsplit((p.scheme, p.netloc, path + "/api", "", ""))


def asset_id(value: str) -> str:
    if not re.fullmatch(r"[0-9a-fA-F-]{36}", value):
        raise ImmichError("Server returned an unsupported asset identifier.")
    return value


def signature(asset: dict) -> str:
    # Include fields affecting bytes, metadata and pairing. Recheck on resume.
    return hashlib.sha256(json.dumps(asset, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def asset_record(raw: dict) -> dict:
    """Keep only evidence fields, excluding GPS, server paths and account data."""
    record = {"id": asset_id(raw["id"])}
    string_fields = {"originalFileName", "checksum", "libraryId", "fileCreatedAt", "localDateTime",
                     "updatedAt", "livePhotoVideoId", "type"}
    bool_fields = {"isEdited", "isOffline", "isTrashed"}
    for name in string_fields | bool_fields:
        if name not in raw:
            continue  # Missing libraryId must remain unknown provenance.
        value = raw[name]
        expected = bool if name in bool_fields else str
        if value is not None and not isinstance(value, expected):
            raise ImmichError("Unexpected destination asset evidence schema.")
        record[name] = value
    if isinstance(raw.get("exifInfo"), dict):
        size = raw["exifInfo"].get("fileSizeInByte")
        if isinstance(size, (int, float)) and not isinstance(size, bool) and size >= 0:
            record["exifInfo"] = {"fileSizeInByte": size}
    if isinstance(raw.get("stack"), dict):
        stack = {}
        for name in ("id", "primaryAssetId"):
            if isinstance(raw["stack"].get(name), str):
                stack[name] = asset_id(raw["stack"][name])
        count = raw["stack"].get("assetCount")
        if isinstance(count, int) and not isinstance(count, bool) and count >= 0:
            stack["assetCount"] = count
        record["stack"] = stack
    return record


def decode_checksum(value: str | None) -> str | None:
    try:
        raw = base64.b64decode(value or "", validate=True)
        return raw.hex() if len(raw) == 20 else None
    except (ValueError, TypeError):
        return None


class Immich:
    def __init__(self, url: str, key: str, timeout: float = 30, transport=None):
        self.url = normalize_url(url)
        self.client = httpx.Client(headers={"x-api-key": key, "accept": "application/json"},
                                   timeout=httpx.Timeout(timeout), follow_redirects=False,
                                   trust_env=False, transport=transport)
        self.requests: list[tuple[str, str]] = []

    def close(self):
        self.client.close()

    def _check(self, method: str, path: str):
        allowed = ((method == "POST" and path == "/search/metadata") or
                   (method == "GET" and path in {"/server/version", "/albums"}) or
                   (method == "GET" and re.fullmatch(r"/assets/[0-9a-fA-F-]{36}(/original)?", path)))
        if not allowed:
            raise ImmichError("Request blocked by the read-only allowlist.")
        self.requests.append((method, path))

    def _json(self, method: str, path: str, body=None, cancel=None):
        self._check(method, path)
        if cancel and cancel.is_set():
            raise Cancelled()
        try:
            with self.client.stream(method, self.url + path, json=body) as r:
                r.raise_for_status()
                chunks, size = [], 0
                for chunk in r.iter_bytes():
                    if cancel and cancel.is_set():
                        raise Cancelled()
                    size += len(chunk)
                    if size > 64 * 1024 * 1024:
                        raise ImmichError("Server response exceeded the 64 MiB page limit.")
                    chunks.append(chunk)
                return json.loads(b"".join(chunks))
        except httpx.HTTPStatusError as e:
            raise ImmichError(f"Immich returned HTTP {e.response.status_code} for {method} {path}.") from None
        except (httpx.HTTPError, ValueError):
            raise ImmichError(f"Immich request failed or timed out for {method} {path}.") from None

    def _pages(self, cancel, album=None):
        items, issues, seen_pages, seen_ids = [], [], set(), set()
        page = "FIRST"
        while page:
            if cancel and cancel.is_set():
                raise Cancelled()
            if page in seen_pages:
                issues.append({"kind": "pagination", "message": "Repeated destination page; coverage is incomplete."})
                break
            seen_pages.add(page)
            # Unlike the legacy flat search, v3 does not implicitly exclude trash.
            body = {"size": 250, "withExif": True, "withStacked": True,
                    "filter": {"trashedAt": {"eq": None}}}
            if page != "FIRST":
                body["cursor"] = page
            if album:
                body["filter"]["albumIds"] = {"any": [album]}
            try:
                response = self._json("POST", "/search/metadata", body, cancel)
                group = response["assets"]
                batch = group["items"]
                if not isinstance(batch, list):
                    raise ValueError()
                for item in batch:
                    item = asset_record(item)
                    ident = item["id"]
                    if item.get("isTrashed"):
                        issues.append({"kind": "destination_changed", "message": "Server returned a trashed asset outside the active-only scope; it was excluded."})
                        continue
                    if ident in seen_ids:
                        issues.append({"kind": "destination_changed", "message": "An asset appeared on multiple pages."})
                    else:
                        items.append(item)
                        seen_ids.add(ident)
                if "nextCursor" not in group:
                    issues.append({"kind": "pagination", "message": "Server lacks the documented v3.3 cursor contract; coverage is incomplete."})
                    break
                page = group["nextCursor"]
                if page is not None and not isinstance(page, str):
                    raise ValueError()
            except (ImmichError, KeyError, TypeError, ValueError) as e:
                issues.append({"kind": "destination_inaccessible", "message": str(e) if isinstance(e, ImmichError) else "Unexpected destination page schema."})
                break
        return items, issues

    def inventory(self, cancel: threading.Event | None = None, progress=None) -> dict:
        issues = []
        version = self._json("GET", "/server/version", cancel=cancel)
        if not isinstance(version, dict) or any(not isinstance(version.get(k), int) or isinstance(version.get(k), bool)
                                                for k in ("major", "minor", "patch")):
            raise ImmichError("Unexpected Immich version response schema.")
        version = ".".join(str(version.get(k, "?")) for k in ("major", "minor", "patch"))
        if not version.startswith("3."):
            raise ImmichError("This adapter targets Immich 3.3.3; this server major version is unsupported.")
        assets, page_issues = self._pages(cancel)
        issues.extend(page_issues)
        assets_by_id = {item["id"]: item for item in assets}
        albums = []
        try:
            listing = self._json("GET", "/albums", cancel=cancel)
            if not isinstance(listing, list):
                raise ImmichError("Unexpected album listing schema.")
            for index, album in enumerate(listing):
                if not isinstance(album, dict):
                    raise ImmichError("Unexpected album listing schema.")
                ident = asset_id(album["id"])
                name = album.get("albumName", "")
                if not isinstance(name, str):
                    raise ImmichError("Unexpected destination album evidence schema.")
                members, errors = self._pages(cancel, ident)
                issues.extend(errors)
                # A readable shared album can contain assets outside the owner's
                # global search universe. Keep those originals in coverage too.
                for member in members:
                    previous = assets_by_id.get(member["id"])
                    if previous is not None and signature(previous) != signature(member):
                        issues.append({"kind": "destination_changed", "message": "Asset metadata changed between library and album enumeration."})
                    elif previous is None:
                        assets.append(member)
                        assets_by_id[member["id"]] = member
                albums.append({"id": ident, "albumName": name,
                               "asset_ids": sorted(a["id"] for a in members)})
                if progress:
                    progress({"phase": "destination", "albums_scanned": index + 1, "assets": len(assets)})
        except (ImmichError, KeyError, TypeError) as e:
            issues.append({"kind": "albums_inaccessible", "message": str(e) if isinstance(e, ImmichError) else "Unexpected album schema."})
        return {"assets": assets, "albums": albums, "version": version, "issues": issues}

    def hash_original(self, ident: str, cancel=None) -> dict:
        ident = asset_id(ident)
        path = f"/assets/{ident}/original"
        before = asset_record(self._json("GET", f"/assets/{ident}", cancel=cancel))
        if before.get("isTrashed"):
            raise ImmichError("Destination asset is now trashed; active original evidence is unavailable.")
        self._check("GET", path)
        sha256, sha1, size = hashlib.sha256(), hashlib.sha1(), 0
        try:
            with self.client.stream("GET", self.url + path, params={"edited": "false"}, headers={"accept-encoding": "identity"}) as r:
                r.raise_for_status()
                expected = r.headers.get("content-length") if r.headers.get("content-encoding", "identity").lower() == "identity" else None
                media = MediaInspector(total_size=int(expected) if expected is not None else None, cancel=cancel)
                for chunk in r.iter_bytes():
                    if cancel and cancel.is_set():
                        raise Cancelled()
                    size += len(chunk)
                    sha256.update(chunk)
                    sha1.update(chunk)
                    media.update(chunk)
                if expected is not None and size != int(expected):
                    raise ImmichError("Original download length did not match Content-Length.")
                media_proof = media.finish()
        except MediaCancelled:
            raise Cancelled() from None
        except httpx.HTTPStatusError as e:
            raise ImmichError(f"Original inaccessible (HTTP {e.response.status_code}).") from None
        except (httpx.HTTPError, ValueError):
            raise ImmichError("Original download failed or timed out.") from None
        after = asset_record(self._json("GET", f"/assets/{ident}", cancel=cancel))
        if signature(before) != signature(after):
            raise ImmichError("Destination asset changed during original download.")
        return {"sha256": sha256.hexdigest(), "sha1": sha1.hexdigest(), "size": size,
                "signature": signature(after), "media": media_proof}
