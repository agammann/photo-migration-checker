"""Bounded container evidence, without decoding pixels, codecs, or playback.

The inspector consumes the same stream used for content hashes. Google Motion
Photo evidence requires exact XMP bounds and a complete appended video container.
Modern layout: https://developer.android.com/media/platform/motion-photo-format
Deprecated MicroVideo offsets are handled separately as legacy evidence.
"""
from __future__ import annotations

import hashlib
import struct
import xml.etree.ElementTree as ET
import zlib
from pathlib import Path


class MediaCancelled(Exception):
    """Inspection was cancelled by its caller."""


def _cancel(event):
    if event is not None and event.is_set():
        raise MediaCancelled("Media inspection cancelled")


class _Parser:
    def __init__(self, total=None, cancel=None):
        self.total, self.cancel = total, cancel
        self.pos = 0
        self.errors = []

    def fail(self, message):
        if message not in self.errors:
            self.errors.append(message)


class _BMFF(_Parser):
    """Walk box boundaries and video-track handlers; skip media payloads."""
    def __init__(self, total=None, cancel=None):
        super().__init__(total, cancel)
        self.header = bytearray()
        self.stack = []
        self.leaf = None
        self.boxes = 0
        self.moov = self.video = self.mdat = self.ftyp = False
        self.brand = None
        self.tracks = {}
        self.movie_header = False

    def _close(self):
        while self.stack and self.pos == self.stack[-1][0]:
            self.stack.pop()
        if self.stack and self.pos > self.stack[-1][0]:
            self.fail("Box exceeds its parent")

    def _leaf_done(self):
        kind, remaining, capture, path, actual, track = self.leaf
        if kind == b"ftyp":
            self.ftyp = True
            if actual < 8 or (actual - 8) % 4:
                self.fail("Invalid file-type box")
            else:
                self.brand = bytes(capture[:4])
                if self.brand in {b"heic", b"heix", b"hevc", b"hevx", b"mif1", b"msf1", b"avif", b"avis"}:
                    self.fail("ISOBMFF image inspection is unsupported")
        if kind == b"hdlr" and path[-3:] == [b"moov", b"trak", b"mdia"]:
            if actual < 24:
                self.fail("Truncated track handler")
            elif capture[8:12] == b"vide":
                self.tracks.setdefault(track, set()).add("video")
        if kind in {b"mvhd", b"tkhd", b"mdhd"}:
            minimum = {b"mvhd": (100, 112), b"tkhd": (84, 96), b"mdhd": (24, 36)}[kind]
            version = capture[0] if capture else 255
            if version > 1 or actual < minimum[version]:
                self.fail("Invalid movie or track header")
            elif kind == b"mvhd" and path == [b"moov"]:
                self.movie_header = True
            elif kind == b"tkhd" and path[-2:] == [b"moov", b"trak"]:
                self.tracks.setdefault(track, set()).add("track_header")
            elif kind == b"mdhd" and path[-3:] == [b"moov", b"trak", b"mdia"]:
                self.tracks.setdefault(track, set()).add("media_header")
        if kind == b"stsd" and path[-5:] == [b"moov", b"trak", b"mdia", b"minf", b"stbl"]:
            if actual < 16 or capture[:4] != b"\0\0\0\0" or not int.from_bytes(capture[4:8], "big") or not 8 <= int.from_bytes(capture[8:12], "big") <= actual - 8:
                self.fail("Invalid sample-description table")
            else:
                self.tracks.setdefault(track, set()).add("sample_description")
        if kind == b"mdat" and actual:
            self.mdat = True
        self.leaf = None

    def feed(self, data):
        view = memoryview(data)
        index = 0
        while index < len(view) and not self.errors:
            _cancel(self.cancel)
            self._close()
            if self.leaf is not None:
                kind, remaining, capture, path, actual, track = self.leaf
                count = len(view) - index if remaining is None else min(remaining, len(view) - index)
                if kind in {b"ftyp", b"hdlr", b"mvhd", b"tkhd", b"mdhd", b"stsd"} and len(capture) < 64:
                    capture.extend(view[index:index + min(count, 64 - len(capture))])
                self.pos += count
                index += count
                self.leaf = (kind, None if remaining is None else remaining - count, capture, path, actual + count, track)
                if remaining is not None and count == remaining:
                    self._leaf_done()
                continue
            need = 8 if len(self.header) < 8 else (16 if self.header[:4] == b"\0\0\0\1" else 8)
            bound = self.stack[-1][0] if self.stack else self.total
            if bound is not None and need - len(self.header) > bound - self.pos:
                self.fail("Box header exceeds its parent bounds")
                continue
            count = min(need - len(self.header), len(view) - index)
            self.header.extend(view[index:index + count])
            index += count
            self.pos += count
            if len(self.header) < need:
                continue
            if need == 8 and self.header[:4] == b"\0\0\0\1":
                continue
            raw = bytes(self.header)
            self.header.clear()
            size, kind = struct.unpack(">I4s", raw[:8])
            size = struct.unpack(">Q", raw[8:])[0] if size == 1 else size
            start = self.pos - need
            parent_end = self.stack[-1][0] if self.stack else self.total
            if size == 0:
                if parent_end is None:
                    if kind != b"mdat":
                        self.fail("Unbounded non-media box")
                        continue
                    end = None
                else:
                    end = parent_end
            else:
                end = start + size
            self.boxes += 1
            if self.boxes > 100_000 or len(self.stack) > 16:
                self.fail("Container complexity limit exceeded")
            elif end is not None and (end < self.pos or (parent_end is not None and end > parent_end)):
                self.fail("Invalid box bounds")
            elif kind in {b"moov", b"trak", b"mdia", b"minf", b"stbl"}:
                if end is None:
                    self.fail("Unbounded container box")
                else:
                    self.moov |= kind == b"moov" and not self.stack
                    if kind == b"trak" and len(self.tracks) >= 4096:
                        self.fail("Track inspection limit exceeded")
                    self.stack.append((end, kind))
            else:
                track = next((v[0] for v in self.stack if v[1] == b"trak"), None)
                self.leaf = (kind, None if end is None else end - self.pos, bytearray(), [v[1] for v in self.stack], 0, track)
                if end == self.pos:
                    self._leaf_done()

    def finish(self):
        if self.leaf is not None and self.leaf[1] is None:
            self._leaf_done()
        self._close()
        self.video = any({"video", "track_header", "media_header", "sample_description"} <= value for value in self.tracks.values())
        if self.header or self.leaf is not None or self.stack:
            self.fail("Truncated box structure")
        if not self.moov or not self.movie_header or not self.video or not self.mdat:
            self.fail("No complete movie metadata, video track, and media payload")
        if self.total is not None and self.pos != self.total and not self.errors:
            self.fail("Container length differs from observed bytes")
        return not self.errors


class _JPEG(_Parser):
    def __init__(self, total=None, cancel=None):
        super().__init__(total, cancel)
        self.state = "soi"
        self.buf = bytearray()
        self.marker = None
        self.remaining = 0
        self.capture = bytearray()
        self.sof = self.sos = False
        self.eoi = None
        self.xmp = []
        self.xmp_bytes = 0
        self.markers = 0

    def _segment(self):
        payload = bytes(self.capture)
        if self.marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
            if len(payload) < 6 or not int.from_bytes(payload[1:3], "big") or not int.from_bytes(payload[3:5], "big") or not payload[5] or len(payload) != 6 + 3 * payload[5]:
                self.fail("Invalid JPEG frame header")
            self.sof = True
        if self.marker == 0xDA:
            if not self.sof or len(payload) < 4 or not payload[0] or len(payload) != 1 + 2 * payload[0] + 3:
                self.fail("Invalid JPEG scan header")
            self.sos = True
        if self.marker == 0xE1 and payload.startswith(b"http://ns.adobe.com/xap/1.0/\0"):
            packet = payload[29:]
            self.xmp_bytes += len(packet)
            if self.xmp_bytes > 262_144 or len(self.xmp) >= 8:
                self.fail("XMP inspection limit exceeded")
            else:
                self.xmp.append(packet)
        self.state = "entropy" if self.marker == 0xDA else "marker_ff"
        self.capture.clear()

    def feed(self, data):
        if not isinstance(data, bytes):
            data = bytes(data)
        index = 0
        while index < len(data) and not self.errors and self.eoi is None:
            _cancel(self.cancel)
            if self.state == "segment":
                count = min(self.remaining, len(data) - index)
                if self.marker in {0xE1, 0xDA, 0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
                    self.capture.extend(data[index:index + count])
                self.pos += count
                index += count
                self.remaining -= count
                if not self.remaining:
                    self._segment()
                continue
            if self.state == "entropy":
                found = data.find(b"\xff", index)
                if found < 0:
                    self.pos += len(data) - index
                    return
                self.pos += found - index + 1
                index = found + 1
                self.state = "entropy_ff"
                continue
            byte = data[index]
            self.pos += 1
            index += 1
            if self.state == "soi":
                self.buf.append(byte)
                if len(self.buf) == 2:
                    if self.buf != b"\xff\xd8":
                        self.fail("Missing JPEG start marker")
                    self.buf.clear()
                    self.state = "marker_ff"
            elif self.state == "marker_ff":
                if byte != 0xFF:
                    self.fail("Invalid JPEG marker boundary")
                else:
                    self.state = "marker"
            elif self.state in {"marker", "entropy_ff"}:
                entropy = self.state == "entropy_ff"
                if byte == 0xFF:
                    continue
                if entropy and (byte == 0 or 0xD0 <= byte <= 0xD7):
                    self.state = "entropy"
                elif byte == 0xD9:
                    self.eoi = self.pos
                elif byte in {0, 0xD8} or 0xD0 <= byte <= 0xD7:
                    self.fail("Unexpected JPEG standalone marker")
                elif byte == 1:
                    self.state = "marker_ff"
                else:
                    self.markers += 1
                    if self.markers > 100_000:
                        self.fail("JPEG marker inspection limit exceeded")
                    self.marker = byte
                    self.state = "length"
            elif self.state == "length":
                self.buf.append(byte)
                if len(self.buf) == 2:
                    self.remaining = int.from_bytes(self.buf, "big") - 2
                    self.buf.clear()
                    if self.remaining < 0:
                        self.fail("Invalid JPEG segment length")
                    elif self.remaining:
                        self.state = "segment"
                    else:
                        self._segment()

    def finish(self):
        if not self.sof or not self.sos or self.eoi is None:
            self.fail("Truncated JPEG or missing frame/scan/end marker")
        return not self.errors


class _PNG(_Parser):
    def __init__(self, total=None, cancel=None):
        super().__init__(total, cancel)
        self.buf = bytearray()
        self.state = "signature"
        self.remaining = 0
        self.kind = None
        self.crc = 0
        self.ihdr = self.idat = self.iend = False
        self.capture = bytearray()
        self.chunks = 0

    def feed(self, data):
        index = 0
        while index < len(data) and not self.errors:
            _cancel(self.cancel)
            if self.iend:
                self.fail("Trailing bytes after PNG end")
                return
            if self.state == "data":
                count = min(self.remaining, len(data) - index)
                chunk = data[index:index + count]
                self.crc = zlib.crc32(chunk, self.crc)
                if self.kind == b"IHDR":
                    self.capture.extend(chunk)
                self.remaining -= count
                self.pos += count
                index += count
                if not self.remaining:
                    self.state = "crc"
                continue
            need = 8 if self.state in {"signature", "header"} else 4
            count = min(need - len(self.buf), len(data) - index)
            self.buf.extend(data[index:index + count])
            index += count
            self.pos += count
            if len(self.buf) != need:
                continue
            raw = bytes(self.buf)
            self.buf.clear()
            if self.state == "signature":
                if raw != b"\x89PNG\r\n\x1a\n":
                    self.fail("Invalid PNG signature")
                self.state = "header"
            elif self.state == "header":
                self.remaining, self.kind = struct.unpack(">I4s", raw)
                self.chunks += 1
                if self.chunks > 100_000 or self.remaining > 0x7FFFFFFF:
                    self.fail("PNG bounds or complexity limit exceeded")
                if not self.ihdr and (self.kind != b"IHDR" or self.remaining != 13):
                    self.fail("Missing PNG image header")
                if self.kind == b"IHDR" and (self.ihdr or self.remaining != 13):
                    self.fail("Invalid PNG image header")
                if self.kind == b"IEND" and self.remaining:
                    self.fail("Invalid PNG end chunk")
                self.capture.clear()
                self.crc = zlib.crc32(self.kind)
                self.state = "data" if self.remaining else "crc"
            else:
                if int.from_bytes(raw, "big") != self.crc & 0xFFFFFFFF:
                    self.fail("PNG chunk CRC mismatch")
                if self.kind == b"IHDR":
                    width, height, depth, color, compression, filtering, interlace = struct.unpack(">IIBBBBB", self.capture)
                    depths = {0: {1, 2, 4, 8, 16}, 2: {8, 16}, 3: {1, 2, 4, 8}, 4: {8, 16}, 6: {8, 16}}
                    if not 0 < width <= 0x7FFFFFFF or not 0 < height <= 0x7FFFFFFF or depth not in depths.get(color, set()) or compression or filtering or interlace not in {0, 1}:
                        self.fail("Invalid PNG dimensions")
                    self.ihdr = True
                self.idat |= self.kind == b"IDAT"
                self.iend |= self.kind == b"IEND"
                self.state = "header"

    def finish(self):
        if not self.ihdr or not self.idat or not self.iend:
            self.fail("Truncated PNG or missing required chunks")
        return not self.errors


class _AVI(_Parser):
    def __init__(self, total=None, cancel=None):
        super().__init__(total, cancel)
        self.buf = bytearray()
        self.stack = []
        self.leaf = None
        self.need_list = None
        self.first = True
        self.end = None
        self.video = self.hdrl = self.movi = False
        self.chunks = 0

    def feed(self, data):
        index = 0
        while index < len(data) and not self.errors:
            _cancel(self.cancel)
            while self.stack and self.pos == self.stack[-1][0]:
                self.stack.pop()
            if self.leaf is not None:
                remaining, capture, kind, path, size = self.leaf
                count = min(remaining, len(data) - index)
                if kind == b"strh" and len(capture) < 56:
                    capture.extend(data[index:index + min(count, 56 - len(capture))])
                self.pos += count
                index += count
                remaining -= count
                self.leaf = (remaining, capture, kind, path, size)
                if not remaining:
                    if kind == b"strh" and path[-2:] == [b"hdrl", b"strl"] and size >= 56 and capture[:4] == b"vids":
                        self.video = True
                    if path and path[-1] == b"movi" and size:
                        self.movi = True
                    self.leaf = None
                continue
            need = 12 if self.first else (4 if self.need_list is not None else 8)
            bound = self.need_list if self.need_list is not None else (self.stack[-1][0] if self.stack else self.end)
            if not self.first and bound is not None and need - len(self.buf) > bound - self.pos:
                self.fail("AVI chunk header exceeds its list bounds")
                continue
            count = min(need - len(self.buf), len(data) - index)
            self.buf.extend(data[index:index + count])
            self.pos += count
            index += count
            if len(self.buf) < need:
                continue
            raw = bytes(self.buf)
            self.buf.clear()
            if self.first:
                self.first = False
                if raw[:4] != b"RIFF" or raw[8:] != b"AVI ":
                    self.fail("Invalid AVI RIFF header")
                self.end = int.from_bytes(raw[4:8], "little") + 8
                if self.end < 12 or (self.total is not None and self.end != self.total):
                    self.fail("Invalid AVI RIFF bounds")
                self.stack.append((self.end, b"AVI "))
            elif self.need_list is not None:
                end = self.need_list
                self.need_list = None
                self.hdrl |= raw == b"hdrl"
                self.stack.append((end, raw))
            else:
                kind, size = raw[:4], int.from_bytes(raw[4:], "little")
                end = self.pos + size + size % 2
                self.chunks += 1
                if self.chunks > 100_000 or len(self.stack) > 16 or not self.stack or end > self.stack[-1][0]:
                    self.fail("Invalid AVI chunk bounds")
                elif kind == b"LIST":
                    if size < 4 or size % 2:
                        self.fail("Invalid AVI list length")
                    else:
                        self.need_list = end
                else:
                    self.leaf = (size + size % 2, bytearray(), kind, [entry[1] for entry in self.stack], size)
                    if not size:
                        self.leaf = None

    def finish(self):
        while self.stack and self.pos == self.stack[-1][0]:
            self.stack.pop()
        if self.first or self.buf or self.leaf or self.need_list is not None or self.stack or self.pos != self.end:
            self.fail("Truncated AVI structure")
        if not self.video or not self.hdrl or not self.movi:
            self.fail("No complete AVI video header and media payload")
        return not self.errors


_CAM = "http://ns.google.com/photos/1.0/camera/"
_CONT = "http://ns.google.com/photos/1.0/container/"
_ITEM = "http://ns.google.com/photos/1.0/container/item/"
_RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"


def _number(value, label, optional=False):
    if value is None and optional:
        return 0
    if not isinstance(value, str) or not value.isascii() or not value.isdecimal() or len(value) > 20:
        raise ValueError("Invalid " + label)
    result = int(value)
    if result > 2**63 - 1:
        raise ValueError("Out-of-range " + label)
    return result


def _motion_plan(packets, total):
    """Return declarations and a candidate range, never trust a stale flag alone."""
    attrs, directories = {}, []
    for packet in packets:
        if b"<!DOCTYPE" in packet.upper() or b"<!ENTITY" in packet.upper():
            raise ValueError("Unsafe XMP declaration")
        try:
            root = ET.fromstring(packet)
        except ET.ParseError as error:
            raise ValueError("Malformed XMP packet") from error
        count = 0
        for element in root.iter():
            count += 1
            if count > 4096:
                raise ValueError("XMP element limit exceeded")
            for key, value in element.attrib.items():
                if key.startswith("{" + _CAM + "}"):
                    if key in attrs and attrs[key] != value:
                        raise ValueError("Conflicting Motion Photo XMP")
                    attrs[key] = value
            if element.tag == "{" + _CONT + "}Directory":
                directories.append(element)
    modern = attrs.get("{" + _CAM + "}MotionPhoto")
    legacy = attrs.get("{" + _CAM + "}MicroVideo")
    if modern is not None:
        if modern == "0":
            return None
        if modern != "1":
            raise ValueError("Invalid MotionPhoto flag")
        result = {"declared": True, "format": "google-motion-photo-v1", "validated": False, "issues": []}
        if attrs.get("{" + _CAM + "}MotionPhotoVersion") != "1" or len(directories) != 1:
            raise ValueError("Motion Photo v1 requires one complete directory")
        directory = directories[0]
        sequences = list(directory)
        if len(sequences) != 1 or sequences[0].tag != "{" + _RDF + "}Seq":
            raise ValueError("Invalid Motion Photo directory sequence")
        items = []
        for member in sequences[0]:
            if member.tag != "{" + _RDF + "}li" or len(member) != 1 or member[0].tag != "{" + _CONT + "}Item":
                raise ValueError("Invalid Motion Photo directory item")
            item = member[0].attrib
            items.append({key: item.get("{" + _ITEM + "}" + key) for key in ("Mime", "Semantic", "Length", "Padding")})
        if len(items) < 2 or len(items) > 32 or items[0]["Semantic"] != "Primary" or items[0]["Mime"] != "image/jpeg":
            raise ValueError("Unsupported Motion Photo primary item")
        if _number(items[0]["Length"], "primary length", True) != 0:
            raise ValueError("Invalid primary length")
        padding = _number(items[0]["Padding"], "primary padding", True)
        before = 0
        for item in items[1:-1]:
            if not item["Mime"] or not item["Semantic"] or item["Semantic"] in {"Primary", "MotionPhoto"} or _number(item["Padding"], "secondary padding", True):
                raise ValueError("Invalid secondary directory item")
            length = _number(item["Length"], "secondary length")
            if not length:
                raise ValueError("Shared Motion Photo resources are unsupported")
            before += length
        last = items[-1]
        if last["Semantic"] != "MotionPhoto" or last["Mime"] not in {"video/mp4", "video/quicktime"} or _number(last["Padding"], "video padding", True):
            raise ValueError("Invalid final Motion Photo item")
        size = _number(last["Length"], "video length")
        if not size:
            raise ValueError("Empty Motion Photo video")
        result.update(size=size, padding=padding, before=before, mime=last["Mime"])
    elif legacy == "1":
        result = {"declared": True, "format": "google-microvideo-legacy", "validated": False, "issues": [], "mime": "video/mp4"}
        if attrs.get("{" + _CAM + "}MicroVideoVersion") != "1":
            raise ValueError("Unsupported legacy MicroVideo version")
        result["size"] = _number(attrs.get("{" + _CAM + "}MicroVideoOffset"), "legacy video offset")
        if not result["size"]:
            raise ValueError("Empty legacy Motion Photo video")
    elif legacy not in {None, "0"}:
        raise ValueError("Invalid MicroVideo flag")
    else:
        return None
    if total is None:
        result["issues"].append("Known complete length required for embedded-video bounds")
    elif result["size"] >= total:
        result["issues"].append("Embedded video is outside the primary image bounds")
    else:
        result["offset"] = total - result["size"]
    return result


class MediaInspector:
    """Incremental inspection with bounded state, independent of file names."""
    def __init__(self, total_size=None, cancel=None):
        valid_total = isinstance(total_size, int) and not isinstance(total_size, bool) and 0 <= total_size <= 2**63 - 1
        self.total = total_size if valid_total else None
        self.input_issue = total_size is not None and not valid_total
        self.cancel = cancel
        self.size = 0
        self.probe = bytearray()
        self.parser = None
        self.kind = "unknown"
        self.motion = None
        self.motion_seen = -1
        self.motion_errors = []
        self.embedded = None
        self.finished = None

    def _choose(self):
        data = bytes(self.probe)
        if data[:2] == b"\xff\xd8":
            self.kind, cls = "jpeg", _JPEG
        elif data[:8] == b"\x89PNG\r\n\x1a\n":
            self.kind, cls = "png", _PNG
        elif data[:4] == b"RIFF" and data[8:12] == b"AVI ":
            self.kind, cls = "avi", _AVI
        elif data[4:8] in {b"ftyp", b"moov", b"mdat", b"free", b"wide"}:
            self.kind, cls = "mp4", _BMFF
        else:
            return
        self.parser = cls(self.total, self.cancel)
        self.parser.feed(bytes(data))
        self.probe.clear()

    def _plan(self, start):
        if not isinstance(self.parser, _JPEG) or len(self.parser.xmp) == self.motion_seen:
            return
        self.motion_seen = len(self.parser.xmp)
        try:
            plan = _motion_plan(self.parser.xmp, self.total)
        except ValueError as error:
            self.motion_errors.append(str(error))
            self.motion = {"declared": True, "format": "unresolved-google-xmp", "validated": False, "issues": list(self.motion_errors)}
            self.embedded = None
            return
        if self.motion_errors:
            return
        if plan != self.motion:
            self.motion = plan
            self.embedded = None
            if plan is not None and "offset" in plan:
                if plan["offset"] < start:
                    plan["issues"].append("Embedded range preceded complete XMP evidence")
                else:
                    self.embedded = (_BMFF(plan["size"], self.cancel), hashlib.sha256(), hashlib.sha1(), 0)

    def update(self, chunk):
        _cancel(self.cancel)
        if self.finished is not None:
            raise ValueError("Inspection already finished")
        if not isinstance(chunk, (bytes, bytearray, memoryview)):
            raise TypeError("Media chunks must be bytes")
        start = self.size
        self.size += len(chunk)
        if self.parser is None:
            count = min(16 - len(self.probe), len(chunk))
            self.probe.extend(chunk[:count])
            if len(self.probe) >= 12 or self.size == self.total:
                self._choose()
            if self.parser is not None and len(chunk) > count:
                self.parser.feed(chunk[count:])
        else:
            self.parser.feed(chunk)
        self._plan(start)
        if self.embedded is not None and self.motion is not None:
            left = max(start, self.motion["offset"])
            right = min(self.size, self.motion["offset"] + self.motion["size"])
            if right > left:
                parser, sha256, sha1, size = self.embedded
                part = chunk[left - start:right - start]
                parser.feed(part)
                sha256.update(part)
                sha1.update(part)
                self.embedded = parser, sha256, sha1, size + len(part)

    def finish(self):
        _cancel(self.cancel)
        if self.finished is not None:
            return self.finished
        if self.parser is None and self.probe:
            self._choose()
        issues = []
        valid = self.parser.finish() if self.parser is not None else False
        if self.parser is not None:
            issues.extend(self.parser.errors)
        else:
            issues.append("Unsupported or unrecognized media container")
        complete = self.total is None or self.size == self.total
        if self.input_issue:
            issues.append("Invalid expected complete length")
            complete = False
            valid = False
        if not complete:
            issues.append("Observed byte count differs from expected complete length")
            valid = False
        family = "image" if self.kind in {"jpeg", "png"} else "video" if self.kind in {"mp4", "avi"} else "unknown"
        if isinstance(self.parser, _BMFF) and not self.parser.video:
            family = "unknown"
        if not valid:
            family = "unknown"
        container = "quicktime" if isinstance(self.parser, _BMFF) and self.parser.brand == b"qt  " else self.kind
        mime = {"jpeg": "image/jpeg", "png": "image/png", "mp4": "video/mp4", "quicktime": "video/quicktime", "avi": "video/x-msvideo"}.get(container)
        result = {"family": family, "mime": mime, "container": container, "evidence": ["Bounded container structure; media payloads were not decoded"] if valid else [], "valid": bool(valid), "complete": bool(complete and valid), "issues": issues}
        if self.motion is not None:
            motion = dict(self.motion)
            motion["issues"] = list(motion["issues"])
            if self.embedded is not None:
                parser, sha256, sha1, size = self.embedded
                embedded_valid = parser.finish()
                eoi = self.parser.eoi if isinstance(self.parser, _JPEG) else None
                bounds = eoi is not None and self.motion["offset"] == eoi
                if self.motion["format"] == "google-motion-photo-v1":
                    bounds = eoi is not None and self.motion["offset"] == eoi + self.motion["padding"] + self.motion["before"]
                if not bounds:
                    motion["issues"].append("Embedded-video bounds disagree with the JPEG end and directory")
                if not embedded_valid:
                    motion["issues"].extend(parser.errors)
                if size != self.motion["size"]:
                    motion["issues"].append("Incomplete embedded-video range")
                if valid and complete and bounds and embedded_valid and size == self.motion["size"] and not motion["issues"]:
                    motion["validated"] = True
                    result["embedded_video"] = {"offset": self.motion["offset"], "size": size, "sha256": sha256.hexdigest(), "sha1": sha1.hexdigest(), "mime": self.motion["mime"], "container": "quicktime" if parser.brand == b"qt  " else "mp4", "validated": True, "evidence": [motion["format"], "Exact appended range, complete box structure and video-track handler"]}
            elif not motion["issues"]:
                motion["issues"].append("No safely inspectable embedded-video range")
            result["motion_photo"] = {key: motion[key] for key in ("declared", "format", "validated", "issues")}
        self.finished = result
        return result


def inspect_file(path, cancel=None):
    """Read a file in bounded chunks; callers still own source-change checks."""
    path = Path(path)
    inspector = MediaInspector(path.stat().st_size, cancel)
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            inspector.update(chunk)
    return inspector.finish()
