"""Explicitly generated local examples; these are not real Immich validation.

This module alone writes the demonstration files. The source scanner never
creates, repairs, or modifies source files. A new, empty destination is required.
"""
from __future__ import annotations

import base64
import hashlib
import json
import struct
import uuid
import zlib
from datetime import datetime, timezone
from pathlib import Path

CAPTURE_TIMESTAMP = 1_700_000_000
FIXED_MTIME_NS = 1_700_000_000_000_000_000
NAMESPACE = uuid.UUID("6bc8a5bb-d8db-4aa1-aefe-1a73cfd87555")


def _png(red: int, green: int, blue: int) -> bytes:
    def chunk(name: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + name + data + struct.pack(">I", zlib.crc32(name + data) & 0xFFFFFFFF)
    pixels = bytes((red, green, blue)) * 4
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(b"\0" + pixels[:6] + b"\0" + pixels[6:])) + chunk(b"IEND", b"")


def _avi(variant: int = 0) -> bytes:
    """Two uncompressed 2x2 BGR frames in a valid indexed AVI container."""
    def chunk(name: bytes, data: bytes) -> bytes:
        return name + struct.pack("<I", len(data)) + data + (b"\0" if len(data) % 2 else b"")
    def listing(kind: bytes, content: bytes) -> bytes:
        return chunk(b"LIST", kind + content)
    avih = struct.pack("<14I", 1_000_000, 16, 0, 0x10, 2, 0, 1, 16, 2, 2, 0, 0, 0, 0)
    strh = struct.pack("<4s4sIHHIIIIIIIIhhhh", b"vids", b"DIB ", 0, 0, 0, 0, 1, 1, 0, 2, 16, 0xFFFFFFFF, 0, 0, 0, 2, 2)
    strf = struct.pack("<IiiHHIIiiII", 40, 2, 2, 1, 24, 0, 16, 0, 0, 0, 0)
    header = listing(b"hdrl", chunk(b"avih", avih) + listing(b"strl", chunk(b"strh", strh) + chunk(b"strf", strf)))
    frames = [bytes((0, variant, 255)) * 2 + b"\0\0" + bytes((0, variant, 255)) * 2 + b"\0\0", bytes((255, variant, 0)) * 2 + b"\0\0" + bytes((255, variant, 0)) * 2 + b"\0\0"]
    movie = listing(b"movi", b"".join(chunk(b"00db", frame) for frame in frames))
    index = chunk(b"idx1", b"".join(struct.pack("<4sIII", b"00db", 0x10, 4 + i * 24, 16) for i in range(2)))
    payload = b"AVI " + header + movie + index
    return b"RIFF" + struct.pack("<I", len(payload)) + payload


def _json(data: dict) -> bytes:
    return (json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _id(value: str) -> str:
    return str(uuid.uuid5(NAMESPACE, value))


def _iso(timestamp: int) -> str:
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat().replace("+00:00", "Z")


def create_sample(base: Path, scenario: str = "problems") -> dict:
    """Create reproducible source and simulated destination bytes in a new folder.

    Returned asset dictionaries use the public Immich-shaped fields consumed by
    the demo adapter. No credentials, network service, or external media is used.
    Existing files are never overwritten. The caller chooses this operation.
    """
    if scenario not in {"correct", "problems"}:
        raise ValueError("Unknown sample scenario")
    base = Path(base)
    if base.exists() and any(base.iterdir()):
        raise ValueError("Sample destination must be empty")
    base.mkdir(parents=True, exist_ok=True)
    source = base / "source"
    destination = base / "destination-originals"
    source.mkdir()
    destination.mkdir()

    file_bytes: dict[str, bytes] = {
        "Family/sunrise.png": _png(255, 180, 20),
        "Family/portrait.png": _png(20, 140, 220),
        "Family/portrait-edited.png": _png(25, 145, 230),
        "Family/collision.png": _png(200, 10, 10),
        "Weekend/sunrise.png": _png(255, 180, 20),
        "Weekend/collision.png": _png(10, 200, 10),
        "Weekend/dated.png": _png(10, 10, 200),
        "Videos/clip.avi": _avi(),
    }
    if scenario == "problems":
        file_bytes.update({
            "Weekend/clock.png": _png(30, 60, 90),
            "Family/broken.png": _png(30, 70, 110),
            "Family/tampered.png": _png(80, 40, 120),
            "Family/this-is-a-very-long-takeout-filename-alpha.png": _png(60, 10, 180),
            "Family/this-is-a-very-long-takeout-filename-beta.png": _png(60, 10, 190),
            "Videos/live.png": _png(100, 150, 200),
            "Videos/live.avi": _avi(1),
        })

    album_titles = {"Family": "Trips", "Weekend": "Trips", "Videos": "Videos"}
    writes: dict[str, bytes] = dict(file_bytes)
    for album, title in album_titles.items():
        writes[f"{album}/metadata.json"] = _json({"title": title, "description": "Deterministic local example", "access": "private"})
    for path in file_bytes:
        if "this-is-a-very-long-" in path:
            continue
        capture = {"timestamp": str(CAPTURE_TIMESTAMP), "formatted": "Nov 14, 2023, 10:13:20 PM UTC"}
        if path == "Weekend/clock.png":
            capture = {"formatted": "Nov 14, 2023, 2:13:20 PM"}
        writes[f"{path}.json"] = _json({"title": Path(path).name, "photoTakenTime": capture, "creationTime": {"timestamp": str(CAPTURE_TIMESTAMP + 500)}})
    if scenario == "problems":
        writes["Family/broken.png.json"] = b'{"title": "broken.png", "photoTakenTime": '
        writes["Family/this-is-a-very-long-takeout-filename-.json"] = _json({"photoTakenTime": {"timestamp": str(CAPTURE_TIMESTAMP)}})
        writes["Unsupported/live.aae"] = b"<plist><dict><key>adjustments</key></dict></plist>\n"
        writes["Unsupported/unknown.bin"] = b"unrecognized sample bytes\0\xff\n"
    import os
    for relative, content in sorted(writes.items()):
        target = source / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        os.utime(target, ns=(FIXED_MTIME_NS, FIXED_MTIME_NS))

    omitted = {"Family/portrait.png", "Family/portrait-edited.png"} if scenario == "problems" else set()
    asset_by_digest: dict[str, dict] = {}
    asset_for_source: dict[str, str] = {}
    originals: dict[str, Path] = {}
    for relative, content in sorted(file_bytes.items()):
        if relative in omitted:
            continue
        digest = hashlib.sha256(content).hexdigest()
        if digest not in asset_by_digest:
            asset_id = _id(f"asset:{digest}")
            created = CAPTURE_TIMESTAMP + (86400 if scenario == "problems" and relative == "Weekend/dated.png" else 0)
            asset = {
                "id": asset_id, "originalFileName": Path(relative).name,
                "checksum": base64.b64encode(hashlib.sha1(content).digest()).decode("ascii"),
                "fileCreatedAt": _iso(created), "updatedAt": _iso(CAPTURE_TIMESTAMP + 1000),
                "localDateTime": _iso(created).removesuffix("Z"),
                "exifInfo": {"fileSizeInByte": len(content)}, "livePhotoVideoId": None,
                "libraryId": None,
                "type": "VIDEO" if Path(relative).suffix == ".avi" else "IMAGE",
            }
            asset_by_digest[digest] = asset
            original = destination / f"{asset_id}{Path(relative).suffix}"
            original.write_bytes(_png(0, 0, 0) if scenario == "problems" and relative == "Family/tampered.png" else content)
            os.utime(original, ns=(FIXED_MTIME_NS, FIXED_MTIME_NS))
            originals[asset_id] = original
        asset_for_source[relative] = asset_by_digest[digest]["id"]

    albums = []
    for directory, title in album_titles.items():
        members = sorted({asset_for_source[path] for path in asset_for_source if Path(path).parent.as_posix() == directory})
        if scenario == "problems" and directory == "Weekend":
            members.remove(asset_for_source["Weekend/sunrise.png"])
        albums.append({"id": _id(f"album:{directory}"), "albumName": title, "asset_ids": members})

    expected = {
        "scenario": scenario,
        "source_media_occurrences": len(file_bytes),
        "source_unique_media": len({hashlib.sha256(content).hexdigest() for content in file_bytes.values()}),
        "destination_assets": len(asset_by_digest),
        "omitted_paths": sorted(omitted),
        "metadata_changed_paths": ["Weekend/dated.png"] if scenario == "problems" else [],
        "mismatched_original_paths": ["Family/tampered.png"] if scenario == "problems" else [],
        "unsupported_paths": ["Unsupported/live.aae", "Unsupported/unknown.bin"] if scenario == "problems" else [],
        "malformed_sidecars": ["Family/broken.png.json"] if scenario == "problems" else [],
        "ambiguous_sidecars": ["Family/this-is-a-very-long-takeout-filename-.json"] if scenario == "problems" else [],
        "uncertain_capture_paths": ["Weekend/clock.png"] if scenario == "problems" else [],
        "paired_paths": ["Videos/live.avi", "Videos/live.png"] if scenario == "problems" else [],
        "missing_memberships": [{"album": "Weekend", "path": "Weekend/sunrise.png"}] if scenario == "problems" else [],
        "duplicate_occurrences": [["Family/sunrise.png", "Weekend/sunrise.png"]],
        "duplicate_album_titles": {"Trips": ["Family", "Weekend"]},
        "hashes": {path: {"sha256": hashlib.sha256(content).hexdigest(), "sha1": hashlib.sha1(content).hexdigest(), "size": len(content)} for path, content in sorted(file_bytes.items())},
    }
    (base / "expected.json").write_bytes(_json(expected))
    return {"source": source, "assets": list(asset_by_digest.values()), "albums": albums, "originals": originals, "expected": expected}
