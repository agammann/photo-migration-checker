import struct
import threading

import pytest

from pmc.container_dates import ContainerDateInspector, MediaCancelled


UNIX_OFFSET = 2_082_844_800
STAMP = 1_583_525_797


def box(kind, payload):
    return struct.pack(">I4s", len(payload) + 8, kind) + payload


def date_header(kind, timestamp, version=0):
    width = 8 if version == 1 else 4
    size = {b"mvhd": (100, 112), b"tkhd": (84, 96), b"mdhd": (24, 36)}[kind][version]
    value = timestamp + UNIX_OFFSET
    data = bytes([version]) + b"\0" * 3 + value.to_bytes(width, "big") * 2
    return box(kind, data + b"\0" * (size - len(data)))


def video(timestamp=STAMP, version=0, track_time=None, media_time=None, handler=b"vide", duplicate=False, track_count=1):
    hdlr = box(b"hdlr", b"\0" * 8 + handler + b"\0" * 12)
    stsd = box(b"stsd", b"\0" * 4 + struct.pack(">I", 1) + box(b"avc1", b"\0" * 78))
    mdhd = date_header(b"mdhd", timestamp if media_time is None else media_time, version)
    mdia = box(b"mdia", mdhd + hdlr + box(b"minf", box(b"stbl", stsd)))
    tkhd = date_header(b"tkhd", timestamp if track_time is None else track_time, version)
    mvhd = date_header(b"mvhd", timestamp, version)
    movie = box(b"moov", mvhd + (mvhd if duplicate else b"") + box(b"trak", tkhd + mdia) * track_count)
    return box(b"ftyp", b"isom\0\0\0\0isommp42") + movie + box(b"mdat", b"\1\2\3")


def inspect(data, chunk=7, total=True):
    inspector = ContainerDateInspector(len(data) if total else None)
    for start in range(0, len(data), chunk):
        inspector.update(data[start:start + chunk])
    return inspector.finish()


@pytest.mark.parametrize("version", [0, 1])
@pytest.mark.parametrize("chunk", [1, 7, 1024 * 1024])
@pytest.mark.parametrize("total", [False, True])
def test_agreeing_creation_fields_streamed_with_explicit_semantics(version, chunk, total):
    result = inspect(video(version=version), chunk, total)
    assert result["valid"] and result["complete"]
    assert result["timestamp"] == STAMP
    assert result["datetime_utc"] == "2020-03-06T20:16:37Z"
    assert result["source"] == "iso_bmff.creation_time"
    assert result["semantics"] == "container_creation"
    assert result["timezone"] == "nominal_utc"
    assert result["capture_instant_verified"] is False
    assert len(result["fields"]) == 3
    assert {f["timestamp"] for f in result["fields"]} == {STAMP}
    assert result["issues"] == []


@pytest.mark.parametrize("change", [{"track_time": STAMP + 1}, {"media_time": STAMP - 1}, {"duplicate": True}])
def test_conflicting_or_duplicate_fields_are_not_selected(change):
    result = inspect(video(**change))
    assert not result["valid"] and not result["complete"]
    assert result["timestamp"] is None and result["datetime_utc"] is None
    assert result["issues"]


@pytest.mark.parametrize("data", [b"", b"file named .mp4", box(b"ftyp", b"isom\0\0\0\0"), video()[:-1], video(handler=b"soun"), video(timestamp=-UNIX_OFFSET)])
def test_unset_truncated_non_video_and_signature_only_inputs_are_unresolved(data):
    result = inspect(data)
    assert not result["valid"] and result["timestamp"] is None
    assert result["capture_instant_verified"] is False
    assert result["issues"]


def test_out_of_range_64_bit_value_is_safe():
    result = inspect(video(timestamp=(2**64 - 1) - UNIX_OFFSET, version=1))
    assert not result["valid"] and result["timestamp"] is None
    assert any("date range" in issue for issue in result["issues"])


def test_pre_unix_epoch_is_not_mistaken_for_unset():
    result = inspect(video(timestamp=-1))
    assert result["valid"] and result["timestamp"] == -1
    assert result["datetime_utc"] == "1969-12-31T23:59:59Z"


def test_true_64_bit_creation_value_and_unsupported_version():
    result = inspect(video(timestamp=5_000_000_000, version=1))
    assert result["valid"] and result["timestamp"] == 5_000_000_000
    data = bytearray(video())
    data[40] = 2  # Movie-header FullBox version, beyond the supported 0/1.
    assert not inspect(data)["valid"]


def test_date_field_limit_remains_bounded():
    inspector = ContainerDateInspector()
    inspector.update(video(track_count=64))
    result = inspector.finish()
    assert not result["valid"]
    assert any("inspection limit" in issue for issue in result["issues"])
    assert len(inspector.parser.date_fields) <= 128
    assert len(inspector.parser.date_keys) <= 128


@pytest.mark.parametrize("total", [-1, True, 1.5, "123", 2**90])
def test_invalid_expected_lengths_are_unresolved(total):
    inspector = ContainerDateInspector(total)
    inspector.update(video())
    result = inspector.finish()
    assert not result["valid"] and not result["complete"] and result["timestamp"] is None


def test_observed_length_mismatch_and_child_header_boundary():
    data = video()
    inspector = ContainerDateInspector(len(data) + 1)
    inspector.update(data)
    assert not inspector.finish()["valid"]
    prefix = video() + box(b"moov", b"\0\0\0\x08")
    suffix = b"abcd" + box(b"free", b"")
    inspector = ContainerDateInspector(len(prefix) + len(suffix))
    inspector.update(prefix)
    inspector.update(suffix)
    assert not inspector.finish()["valid"]


def test_cancellation_is_shared_and_finish_is_idempotent():
    event = threading.Event()
    inspector = ContainerDateInspector(cancel=event)
    event.set()
    with pytest.raises(MediaCancelled):
        inspector.update(video())
    with pytest.raises(MediaCancelled):
        inspector.finish()
    event.clear()
    inspector.update(video())
    assert inspector.finish() == inspector.finish()


def test_payload_is_skipped_with_bounded_state():
    # A 32 MiB media payload is not kept in the date inspector.
    data = video()
    prefix = data[:-11] + struct.pack(">I4s", 32 * 1024 * 1024 + 8, b"mdat")
    inspector = ContainerDateInspector(len(prefix) + 32 * 1024 * 1024)
    inspector.update(prefix)
    chunk = b"x" * (1024 * 1024)
    for _ in range(32):
        inspector.update(chunk)
    assert inspector.finish()["valid"]
    assert len(inspector.parser.date_fields) == 3
    assert len(inspector.parser.header) <= 16
