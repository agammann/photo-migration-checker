"""Bounded ISO BMFF creation-field evidence, separate from capture instants.

Movie, track and media header creation times describe container metadata. Their
nominal UTC interpretation does not establish when the camera exposed a frame,
or establish that a particular writer actually used UTC. See Apple's creation
field definition: https://developer.apple.com/documentation/quicktime-file-format/movie_header_atom/creation_time
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .media import MediaCancelled, _BMFF, _cancel


_EPOCH = datetime(1904, 1, 1, tzinfo=timezone.utc)
_UNIX_OFFSET = 2_082_844_800
_FIELD_LIMIT = 128


class _CreationBMFF(_BMFF):
    """Collect only small creation fields during the existing bounded box walk."""
    def __init__(self, total=None, cancel=None):
        super().__init__(total, cancel)
        self.date_fields = []
        self.date_keys = set()

    def _leaf_done(self):
        kind, remaining, capture, path, actual, track = self.leaf
        supported_path = ((kind == b"mvhd" and path == [b"moov"])
                          or (kind == b"tkhd" and path == [b"moov", b"trak"])
                          or (kind == b"mdhd" and path == [b"moov", b"trak", b"mdia"]))
        if supported_path:
            key = (kind, track)
            if key in self.date_keys:
                self.fail("Duplicate container creation field")
            elif len(self.date_fields) >= _FIELD_LIMIT:
                self.fail("Container date field inspection limit exceeded")
            else:
                self.date_keys.add(key)
                version = capture[0] if capture else 255
                width = 8 if version == 1 else 4
                if version not in {0, 1} or len(capture) < 4 + width:
                    self.fail("Truncated or unsupported container creation field")
                else:
                    raw = int.from_bytes(capture[4:4 + width], "big")
                    field = {"field": "/".join(part.decode("ascii") for part in [*path, kind]) + ".creation_time",
                             "version": version, "raw_seconds_since_1904": raw,
                             "timestamp": None, "datetime_utc": None}
                    if not raw:
                        self.fail("Container creation field is zero or unset")
                    else:
                        try:
                            moment = _EPOCH + timedelta(seconds=raw)
                            field["timestamp"] = raw - _UNIX_OFFSET
                            field["datetime_utc"] = moment.isoformat().replace("+00:00", "Z")
                        except (OverflowError, ValueError):
                            self.fail("Container creation field is outside the supported date range")
                    self.date_fields.append(field)
        super()._leaf_done()

    def finish(self):
        super().finish()
        if (b"mvhd", None) not in self.date_keys:
            self.fail("Movie creation field is unavailable")
        tracks = {track for kind, track in self.date_keys if kind in {b"tkhd", b"mdhd"}}
        if not tracks or any((b"tkhd", track) not in self.date_keys or (b"mdhd", track) not in self.date_keys for track in tracks):
            self.fail("Track and media creation fields are incomplete")
        values = {field["timestamp"] for field in self.date_fields if field["timestamp"] is not None}
        if len(values) > 1:
            self.fail("Container creation fields disagree")
        if len(values) != 1:
            self.fail("No single nonzero container creation timestamp is available")
        return not self.errors


class ContainerDateInspector:
    """Incrementally inspect nominal container creation metadata.

    A positive result requires complete movie/video structure and agreement of
    every observed movie/track/media creation field. Unknown or conflicting
    fields remain unresolved; filenames, filesystem dates and photo-pair dates
    are never inputs. At most 128 small field records and bounded parser state
    are retained. Cancellation raises the same MediaCancelled as MediaInspector.
    """
    def __init__(self, total_size=None, cancel=None):
        valid_total = isinstance(total_size, int) and not isinstance(total_size, bool) and 0 <= total_size <= 2**63 - 1
        self.total = total_size if valid_total else None
        self.input_issue = total_size is not None and not valid_total
        self.cancel = cancel
        self.size = 0
        self.probe = bytearray()
        self.parser = None
        self.finished = None

    def _choose(self):
        if bytes(self.probe[4:8]) in {b"ftyp", b"moov", b"mdat", b"free", b"wide"}:
            self.parser = _CreationBMFF(self.total, self.cancel)
            self.parser.feed(bytes(self.probe))
            self.probe.clear()

    def update(self, chunk):
        _cancel(self.cancel)
        if self.finished is not None:
            raise ValueError("Container date inspection already finished")
        if not isinstance(chunk, (bytes, bytearray, memoryview)):
            raise TypeError("Container date chunks must be bytes")
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

    def finish(self):
        _cancel(self.cancel)
        if self.finished is not None:
            return self.finished
        if self.parser is None and self.probe:
            self._choose()
        valid = self.parser.finish() if self.parser is not None else False
        issues = list(self.parser.errors) if self.parser is not None else ["Unsupported or unrecognized movie container"]
        complete = self.total is None or self.size == self.total
        if self.input_issue:
            issues.append("Invalid expected complete length")
            valid = complete = False
        if not complete:
            if not self.input_issue:
                issues.append("Observed bytes differ from expected complete length")
            valid = False
        fields = [dict(field) for field in self.parser.date_fields] if self.parser is not None else []
        timestamp = fields[0]["timestamp"] if valid and fields else None
        self.finished = {"timestamp": timestamp,
                         "datetime_utc": fields[0]["datetime_utc"] if timestamp is not None else None,
                         "source": "iso_bmff.creation_time", "semantics": "container_creation",
                         "timezone": "nominal_utc", "capture_instant_verified": False,
                         "fields": fields, "valid": bool(valid), "complete": bool(valid and complete),
                         "issues": issues}
        return self.finished
