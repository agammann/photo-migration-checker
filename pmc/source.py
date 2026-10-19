"""Read-only, conservative manifest builder for extracted Takeout folders.

Directories alone never prove album membership. A directory becomes an album
only when it contains recognizable album metadata. JSON associations are local
to one directory, and an ambiguous candidate never wins by ordering.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from threading import Event
from typing import Callable

from .media import MediaCancelled, MediaInspector
from .container_dates import ContainerDateInspector

CHUNK_SIZE = 1024 * 1024
MAX_JSON_BYTES = 2 * 1024 * 1024
ALBUM_METADATA_NAMES = frozenset({"metadata.json", "métadonnées.json"})
IMAGE_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".heif", ".avif",
    ".tif", ".tiff", ".bmp", ".dng", ".cr2", ".cr3", ".nef", ".arw",
    ".orf", ".rw2", ".raf", ".pef", ".srw",
}
VIDEO_EXTENSIONS = {
    ".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm", ".mpg", ".mpeg",
    ".mts", ".m2ts", ".3gp", ".3g2", ".wmv",
}
_MIME = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
    ".gif": "image/gif", ".webp": "image/webp", ".heic": "image/heic",
    ".heif": "image/heif", ".avif": "image/avif", ".tif": "image/tiff",
    ".tiff": "image/tiff", ".bmp": "image/bmp", ".mp4": "video/mp4",
    ".mov": "video/quicktime", ".avi": "video/x-msvideo",
    ".webm": "video/webm", ".mkv": "video/x-matroska", ".json": "application/json",
}


class SourceCancelled(Exception):
    """A source scan was cancelled; no partial manifest should be trusted."""


def _check_cancel(cancel: Event | None) -> None:
    if cancel is not None and cancel.is_set():
        raise SourceCancelled("Source scan cancelled")


def _issue(code: str, path: str, message: str, **extra) -> dict:
    return {"code": code, "path": path, "message": message, **extra}


def _is_link(info: os.stat_result) -> bool:
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    )


def _signature(info: os.stat_result) -> tuple:
    return info.st_size, info.st_mtime_ns, info.st_dev, info.st_ino


def _stat_dict(info: os.stat_result) -> dict:
    return {
        "size": info.st_size,
        "mtime_ns": info.st_mtime_ns,
        "device": info.st_dev,
        "inode": info.st_ino,
    }


def _enumerate(root: Path, cancel: Event | None, issues: list[dict]) -> list[tuple[Path, dict]]:
    files: list[tuple[Path, dict]] = []
    pending = [root]
    while pending:
        _check_cancel(cancel)
        directory = pending.pop()
        rel_dir = directory.relative_to(root).as_posix()
        try:
            # Recheck before traversal in case a directory was replaced.
            if _is_link(directory.lstat()):
                issues.append(_issue("symlink_skipped", rel_dir, "Symbolic link or junction was not followed."))
                continue
            with os.scandir(directory) as listing:
                entries = sorted(listing, key=lambda entry: entry.name)
        except OSError as exc:
            issues.append(_issue("directory_unreadable", rel_dir, "Directory could not be listed.", error_type=type(exc).__name__))
            continue
        for entry in entries:
            _check_cancel(cancel)
            path = Path(entry.path)
            rel = path.relative_to(root).as_posix()
            try:
                # Windows DirEntry.stat may report zero device/inode values;
                # lstat supplies signatures comparable to an opened handle.
                info = path.lstat()
            except OSError as exc:
                issues.append(_issue("file_unreadable", rel, "File attributes could not be read.", error_type=type(exc).__name__))
                continue
            if _is_link(info):
                issues.append(_issue("symlink_skipped", rel, "Symbolic link or junction was not followed."))
                continue
            if stat.S_ISDIR(info.st_mode):
                pending.append(path)
            elif stat.S_ISREG(info.st_mode):
                files.append((path, _stat_dict(info)))
            else:
                issues.append(_issue("special_file_skipped", rel, "Non-regular filesystem entry was not read."))
    return sorted(files, key=lambda entry: entry[0].relative_to(root).as_posix())


def _safe_open(path: Path, root: Path):
    """Recheck all parents and open without following a final symlink on POSIX.

    This prevents ordinary symlink traversal and catches replacement between
    enumeration and open. It does not claim protection from a hostile process
    racing filesystem operations on every supported platform.
    """
    current = path
    while True:
        if _is_link(current.lstat()):
            raise OSError("Filesystem entry changed to a symbolic link")
        if current == root:
            break
        current = current.parent
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    return os.fdopen(os.open(path, flags), "rb")


def _hash_file(path: Path, root: Path, initial: dict, cancel: Event | None) -> tuple:
    rel = path.relative_to(root).as_posix()
    sha256, sha1 = hashlib.sha256(), hashlib.sha1()
    try:
        with _safe_open(path, root) as handle:
            before = os.fstat(handle.fileno())
            if _signature(before) != (initial["size"], initial["mtime_ns"], initial["device"], initial["inode"]):
                return None, None, [_issue("source_changed", rel, "Source changed between discovery and hashing.")], {}
            media = MediaInspector(total_size=before.st_size, cancel=cancel)
            dates = ContainerDateInspector(total_size=before.st_size, cancel=cancel)
            while True:
                _check_cancel(cancel)
                block = handle.read(CHUNK_SIZE)
                if not block:
                    break
                sha256.update(block)
                sha1.update(block)
                media.update(block)
                dates.update(block)
            after = os.fstat(handle.fileno())
        final = path.lstat()
        if _is_link(final) or _signature(before) != _signature(after) or _signature(after) != _signature(final):
            return None, None, [_issue("source_changed", rel, "Source changed while its bytes were being read.")], {}
        media_proof = media.finish()
        if media_proof.get("valid") and media_proof.get("complete") and media_proof.get("family") == "video" and media_proof.get("container") in {"mp4", "quicktime"}:
            media_proof["container_creation"] = dates.finish()
        return sha256.hexdigest(), sha1.hexdigest(), [], media_proof
    except MediaCancelled:
        raise SourceCancelled("Source scan cancelled") from None
    except OSError as exc:
        return None, None, [_issue("file_unreadable", rel, "File bytes could not be read.", error_type=type(exc).__name__)], {}


def _read_json(path: Path, root: Path, inventory: dict) -> tuple[dict | None, dict | None]:
    rel = path.relative_to(root).as_posix()
    if inventory["size"] > MAX_JSON_BYTES:
        return None, _issue("sidecar_too_large", rel, "JSON exceeds the 2 MiB metadata limit and was not parsed.")
    if inventory["sha256"] is None:
        return None, None
    try:
        with _safe_open(path, root) as handle:
            raw = handle.read(MAX_JSON_BYTES + 1)
        if len(raw) > MAX_JSON_BYTES:
            return None, _issue("sidecar_too_large", rel, "JSON exceeded the metadata limit while being read.")
        if hashlib.sha256(raw).hexdigest() != inventory["sha256"]:
            return None, _issue("source_changed", rel, "JSON changed after its inventory hash was recorded.")
        data = json.loads(raw.decode("utf-8-sig"))
        if not isinstance(data, dict):
            raise ValueError("JSON root must be an object")
        return data, None
    except (OSError, ValueError, UnicodeError, RecursionError) as exc:
        return None, _issue("sidecar_malformed", rel, "JSON metadata could not be parsed as an object.", error_type=type(exc).__name__)


def _album_title(name: str, data: dict) -> str | None:
    photo_fields = {"photoTakenTime", "creationTime", "googlePhotosOrigin", "imageViews"}
    if photo_fields.intersection(data):
        return None
    album_data = data.get("albumData")
    if isinstance(album_data, dict) and isinstance(album_data.get("title"), str):
        return album_data["title"][:4096]
    normalized = unicodedata.normalize("NFC", name).casefold()
    if normalized not in ALBUM_METADATA_NAMES:
        return None
    if isinstance(data.get("title"), str) and any(key in data for key in ("description", "access", "date", "contentSummary")):
        return data["title"][:4096]
    return None


def _association_candidates(sidecar: Path, data: dict | None, members: list[dict]) -> tuple[list[dict], str]:
    """Exact paths outrank titles; weak matching must yield a single candidate."""
    name = sidecar.name
    stripped = name[:-5]  # .json, case-insensitively selected by caller
    for suffix in (".supplemental-metadata", ".supplemental_metadata"):
        if stripped.casefold().endswith(suffix):
            stripped = stripped[:-len(suffix)]
            break
    exact = [item for item in members if Path(item["path"]).name == stripped]
    title = data.get("title") if data else None
    title_matches = [item for item in members if Path(item["path"]).name == title] if isinstance(title, str) else []
    if exact:
        # Conflicting filename and title evidence must not silently lend one
        # photo's timestamp to another existing photo.
        if title_matches and {item["path"] for item in exact} != {item["path"] for item in title_matches}:
            return list({item["path"]: item for item in exact + title_matches}.values()), "filename_title_conflict"
        return exact, "exact_filename"
    # Takeout may truncate long JSON names. Prefix evidence needs a long prefix;
    # short names and stem-only matches are too easy to misassociate.
    prefix = stripped
    prefix_matches = [item for item in members if len(prefix) >= 30 and Path(item["path"]).name.startswith(prefix)]
    if title_matches:
        if prefix_matches and not ({item["path"] for item in prefix_matches} & {item["path"] for item in title_matches}):
            return list({item["path"]: item for item in prefix_matches + title_matches}.values()), "truncated_filename_title_conflict"
        return title_matches, "sidecar_title"
    return prefix_matches, "truncated_filename"


def _capture(data: dict) -> tuple[dict | None, dict | None]:
    value = data.get("photoTakenTime")
    if not isinstance(value, dict):
        return None, None
    raw = value.get("timestamp")
    formatted = value.get("formatted")
    result = {
        "timestamp": None, "datetime_utc": None, "source": "takeout.photoTakenTime",
        "timezone": "unknown", "timezone_uncertain": True, "original_timezone": None,
        "raw": str(raw)[:256] if raw is not None else (str(formatted)[:256] if formatted is not None else None),
    }
    try:
        if isinstance(raw, bool) or not re.fullmatch(r"-?\d{1,12}", str(raw)):
            raise ValueError("Not an integer timestamp")
        timestamp = int(raw)
        result["datetime_utc"] = datetime.fromtimestamp(timestamp, timezone.utc).isoformat().replace("+00:00", "Z")
        result["timestamp"] = timestamp
        result["timezone"] = "utc"
        return result, None
    except (ValueError, OverflowError, OSError):
        return result, {"code": "capture_time_unresolved", "message": "Capture time has no supported epoch timestamp; formatted text and filesystem dates were not substituted."}


def scan_source(root: Path, cancel: Event | None = None, progress: Callable[[dict], None] | None = None) -> dict:
    """Build a source manifest without modifying the selected tree.

    ``supported`` means a recognized media extension or structurally identified
    media container whose original bytes can be compared. Container inspection
    is separate evidence and does not attest to decoded pixels or playback.
    All regular files are inventoried; unrecognized non-metadata files become
    unsupported items, so they cannot silently disappear from coverage.
    """
    root = Path(root).absolute()
    if not root.is_dir() or _is_link(root.lstat()):
        raise ValueError("Source must be an existing directory, not a symbolic link or junction")
    issues: list[dict] = []
    paths = _enumerate(root, cancel, issues)
    inventory: list[dict] = []
    entries: dict[str, dict] = {}
    bytes_done = 0
    bytes_total = sum(info["size"] for _, info in paths)
    for index, (path, info) in enumerate(paths):
        _check_cancel(cancel)
        rel = path.relative_to(root).as_posix()
        sha256, sha1, file_issues, media = _hash_file(path, root, info, cancel)
        entry = {"path": rel, **info, "sha256": sha256, "sha1": sha1, "issues": file_issues, "media": media}
        inventory.append(entry)
        entries[rel] = entry
        issues.extend(file_issues)
        bytes_done += info["size"]
        if progress:
            progress({"phase": "source", "files_scanned": index + 1, "files_total": len(paths), "bytes_scanned": bytes_done, "bytes_total": bytes_total, "path": rel})

    parsed_json: dict[str, dict | None] = {}
    json_issues: dict[str, dict] = {}
    album_titles: dict[str, str] = {}
    album_metadata_paths: set[str] = set()
    album_candidates: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for path, _ in paths:
        _check_cancel(cancel)
        if path.suffix.casefold() != ".json":
            continue
        rel = path.relative_to(root).as_posix()
        data, error = _read_json(path, root, entries[rel])
        parsed_json[rel] = data
        if error:
            issues.append(error)
            json_issues[rel] = error
        if data is not None:
            title = _album_title(path.name, data)
            if title is not None:
                parent = path.parent.relative_to(root).as_posix()
                album_candidates[parent].append((rel, title))
                album_metadata_paths.add(rel)
    for parent, candidates in album_candidates.items():
        titles = {title for _, title in candidates}
        if any(not title.strip() for title in titles):
            issues.append(_issue(
                "album_metadata_unresolved", parent,
                "Recognizable album metadata has an empty title; no album identity or membership was asserted.",
                metadata_paths=[rel for rel, _ in candidates],
            ))
        elif len(titles) == 1:
            album_titles[parent] = candidates[0][1]
        else:
            issues.append(_issue(
                "album_metadata_conflict", parent,
                "Recognizable album metadata disagrees on this directory's album title; no album identity or membership was asserted.",
                metadata_paths=[rel for rel, _ in candidates], titles=sorted(titles),
            ))

    items: list[dict] = []
    directory_members: dict[str, list[dict]] = defaultdict(list)
    for path, info in paths:
        if path.suffix.casefold() == ".json":
            continue
        rel = path.relative_to(root).as_posix()
        ext = path.suffix.casefold()
        media = entries[rel]["media"]
        recognized = media.get("valid") and media.get("complete") and media.get("family") in {"image", "video"}
        supported = ext in IMAGE_EXTENSIONS or ext in VIDEO_EXTENSIONS or recognized
        extension_type = _MIME.get(ext, "image/x-raw" if ext in IMAGE_EXTENSIONS else "video/unknown" if ext in VIDEO_EXTENSIONS else "application/octet-stream")
        media_type = media.get("mime", extension_type) if recognized else extension_type
        parent = path.parent.relative_to(root).as_posix()
        item = {
            "path": rel, "size": info["size"], "sha256": entries[rel]["sha256"], "sha1": entries[rel]["sha1"],
            "media_type": media_type, "extension_media_type": extension_type, "media": media, "supported": bool(supported), "capture": None,
            "albums": [parent] if parent in album_titles and supported else [],
            "directory_hint": parent, "sidecars": [], "issues": list(entries[rel]["issues"]), "stat": info,
        }
        if not supported:
            issue = _issue("unsupported_format", rel, "Unrecognized file type is included as unsupported; its bytes were inventoried.")
            item["issues"].append(issue)
            issues.append(issue)
        items.append(item)
        directory_members[parent].append(item)

    associations: dict[str, list[tuple[str, dict, str]]] = defaultdict(list)
    auxiliary_files: list[dict] = []
    sidecar_metadata_paths: set[str] = set()
    for rel, data in parsed_json.items():
        _check_cancel(cancel)
        if rel in album_metadata_paths:
            continue
        path = Path(rel)
        members = directory_members[path.parent.as_posix()]
        candidates, method = _association_candidates(path, data, members)
        looks_like_sidecar = bool(candidates) or (data is not None and any(key in data for key in ("photoTakenTime", "creationTime", "googlePhotosOrigin", "geoData", "imageViews", "url"))) or ".supplemental-metadata" in path.name.casefold()
        if len(candidates) == 1:
            sidecar_metadata_paths.add(rel)
            item = candidates[0]
            item["sidecars"].append(rel)
            item.setdefault("sidecar_evidence", []).append({"path": rel, "method": method})
            if rel in json_issues:
                item["issues"].append(json_issues[rel])
            if data is not None:
                associations[item["path"]].append((rel, data, method))
        elif len(candidates) > 1:
            sidecar_metadata_paths.add(rel)
            issue = _issue("sidecar_ambiguous", rel, "Multiple source files fit this sidecar; no association was asserted.", candidates=[item["path"] for item in candidates])
            issues.append(issue)
            for item in candidates:
                item["issues"].append(issue)
        elif looks_like_sidecar:
            sidecar_metadata_paths.add(rel)
            issues.append(_issue("sidecar_unmatched", rel, "Sidecar has no unique source file association."))
        elif path.name.casefold() == "shared_album_comments.json" and data == {} and rel not in json_issues and not entries[rel]["issues"]:
            entry = entries[rel]
            auxiliary_files.append({"path": rel, "size": entry["size"], "sha256": entry["sha256"], "sha1": entry["sha1"],
                                    "role": "auxiliary", "classification": "empty_shared_album_comments", "content_state": "empty_object",
                                    "message": "Known shared-album comments metadata contains an empty JSON object. Its bytes remain inventoried; no destination media asset or comment payload is expected."})
        else:
            entry = entries[rel]
            issue = _issue("unsupported_format", rel, "JSON was not recognized as album metadata or an associated media sidecar.")
            items.append({"path": rel, "size": entry["size"], "sha256": entry["sha256"], "sha1": entry["sha1"], "media_type": "application/json", "supported": False, "capture": None, "albums": [], "directory_hint": path.parent.as_posix(), "sidecars": [], "issues": [*entry["issues"], *([json_issues[rel]] if rel in json_issues else []), issue], "stat": {key: entry[key] for key in ("size", "mtime_ns", "device", "inode")}})
            issues.append(issue)

    for item in items:
        captures: list[dict] = []
        for rel, data, _ in associations[item["path"]]:
            capture, error = _capture(data)
            if capture is not None:
                captures.append(capture)
            if error:
                issue = _issue(error["code"], item["path"], error["message"], sidecar=rel)
                item["issues"].append(issue)
                issues.append(issue)
        distinct = {json.dumps(capture, sort_keys=True) for capture in captures}
        if len(distinct) == 1:
            item["capture"] = captures[0]
        elif len(distinct) > 1:
            issue = _issue("capture_time_conflict", item["path"], "Associated sidecars disagree on capture time; no capture time was selected.")
            item["issues"].append(issue)
            issues.append(issue)

    for members in directory_members.values():
        by_stem: dict[str, list[dict]] = defaultdict(list)
        for item in members:
            if item["supported"]:
                by_stem[Path(item["path"]).stem.casefold()].append(item)
        for group in by_stem.values():
            if any(item["media_type"].startswith("image/") for item in group) and any(item["media_type"].startswith("video/") for item in group):
                proved = set()
                for image in group:
                    embedded = (image.get("media") or {}).get("embedded_video") or {}
                    if not embedded.get("validated"):
                        continue
                    videos = [video for video in group if video.get("sha256") == embedded.get("sha256")
                              and video.get("size") == embedded.get("size")
                              and (video.get("media") or {}).get("valid") is True
                              and (video.get("media") or {}).get("family") == "video"]
                    if videos:
                        proved.add(image["path"])
                        proved.update(video["path"] for video in videos)
                for item in group:
                    if item["path"] in proved:
                        continue
                    issue = _issue("paired_media_uncertain", item["path"], "An image and video share a filename stem. Each component is checked separately; preservation of the pairing is unverified.", components=[other["path"] for other in group])
                    item["issues"].append(issue)
                    issues.append(issue)
    duplicates: dict[str, list[str]] = defaultdict(list)
    for item in items:
        if item["supported"] and item["sha256"]:
            duplicates[item["sha256"]].append(item["path"])
    _check_cancel(cancel)
    return {
        "root_name": root.name, "items": sorted(items, key=lambda item: item["path"]),
        "issues": issues, "inventory": inventory, "total_bytes": sum(item["size"] for item in items),
        "auxiliary_files": auxiliary_files,
        "inventory_summary": {"files": len(inventory), "bytes": bytes_total,
                              "media_files": sum(bool(item.get("supported")) for item in items),
                              "comparison_files": len(items), "auxiliary_files": len(auxiliary_files),
                              "auxiliary_bytes": sum(item["size"] for item in auxiliary_files),
                              "sidecar_files": len(sidecar_metadata_paths), "album_metadata_files": len(album_metadata_paths)},
        "inventory_bytes": bytes_total, "album_titles": album_titles,
        "duplicate_groups": [{"sha256": digest, "paths": names} for digest, names in sorted(duplicates.items()) if len(names) > 1],
        "album_policy": "Only directories with recognizable album metadata assert membership; ordinary directory names are hints only.",
        "capture_policy": "Epoch capture instants are separate from filesystem mtime. Original camera timezone is unknown unless independently established.",
    }
