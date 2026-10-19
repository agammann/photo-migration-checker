import hashlib
import struct
import threading

import pytest

from pmc.media import MediaCancelled, MediaInspector, inspect_file
from pmc.sample import _avi, _png


def box(kind, payload):
    return struct.pack(">I4s", len(payload) + 8, kind) + payload


def video(handler=b"vide", payload=b"\x01\x02\x03", extended=False):
    # Small structural fixture: it deliberately makes no codec/playback claim.
    hdlr = box(b"hdlr", b"\0" * 8 + handler + b"\0" * 12)
    description = box(b"stsd", b"\0" * 4 + struct.pack(">I", 1) + box(b"avc1", b"\0" * 78))
    media = box(b"mdia", box(b"mdhd", b"\0" * 24) + hdlr + box(b"minf", box(b"stbl", description)))
    movie = box(b"moov", box(b"mvhd", b"\0" * 100) + box(b"trak", box(b"tkhd", b"\0" * 84) + media))
    mdat = box(b"mdat", payload)
    if extended:
        mdat = struct.pack(">I4sQ", 1, b"mdat", len(payload) + 16) + payload
    return box(b"ftyp", b"isom\0\0\0\0isommp42") + movie + mdat


def jpeg(xmp=None):
    def segment(marker, payload):
        return b"\xff" + bytes([marker]) + struct.pack(">H", len(payload) + 2) + payload
    app = segment(0xE1, b"http://ns.adobe.com/xap/1.0/\0" + xmp) if xmp is not None else b""
    return b"\xff\xd8" + app + segment(0xC0, b"\x08\0\x01\0\x01\x01\x01\x11\0") + segment(0xDA, b"\x01\x01\0\0\x3f\0") + b"\x01\xff\0\x02\xff\xd0\x03\xff\xd9"


def xmp(attrs, directory=""):
    return (f'<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"><rdf:Description xmlns:GCamera="http://ns.google.com/photos/1.0/camera/" xmlns:Container="http://ns.google.com/photos/1.0/container/" xmlns:Item="http://ns.google.com/photos/1.0/container/item/" {attrs}>{directory}</rdf:Description></rdf:RDF></x:xmpmeta>').encode()


def legacy(size, extra=""):
    return xmp(f'GCamera:MicroVideo="1" GCamera:MicroVideoVersion="1" GCamera:MicroVideoOffset="{size}" {extra}')


def modern(size, padding=0, extra=""):
    directory = f'<Container:Directory><rdf:Seq><rdf:li rdf:parseType="Resource"><Container:Item Item:Mime="image/jpeg" Item:Semantic="Primary" Item:Padding="{padding}"/></rdf:li><rdf:li rdf:parseType="Resource"><Container:Item Item:Mime="video/mp4" Item:Semantic="MotionPhoto" Item:Length="{size}"/></rdf:li></rdf:Seq></Container:Directory>'
    return xmp(f'GCamera:MotionPhoto="1" GCamera:MotionPhotoVersion="1" {extra}', directory)


def inspect(data, chunk=7, total=True):
    inspector = MediaInspector(len(data) if total else None)
    for start in range(0, len(data), chunk):
        inspector.update(data[start:start + chunk])
    return inspector.finish()


@pytest.mark.parametrize("data,family,container", [(jpeg(), "image", "jpeg"), (_png(1, 2, 3), "image", "png"), (_avi(), "video", "avi"), (video(), "video", "mp4"), (video(extended=True), "video", "mp4")])
@pytest.mark.parametrize("chunk", [1, 7, 1024 * 1024])
def test_container_structure_across_stream_boundaries(data, family, container, chunk):
    result = inspect(data, chunk)
    assert (result["family"], result["container"], result["valid"], result["complete"]) == (family, container, True, True)
    assert result["issues"] == []
    assert "not decoded" in result["evidence"][0]


@pytest.mark.parametrize("data", [jpeg()[:-1], _png(1, 2, 3)[:-1], _avi()[:-1], video()[:-1], box(b"ftyp", b"isom\0\0\0\0"), b"\0\0\0\x04ftyp", b"", b"renamed.jpg"])
def test_truncation_and_signature_spoofs_are_not_valid(data):
    result = inspect(data)
    assert not result["valid"] and not result["complete"]
    assert result["issues"]


def test_audio_handler_and_image_brand_alone_do_not_prove_video():
    assert inspect(video(b"soun"))["family"] == "unknown"
    assert not inspect(video(b"soun"))["valid"]
    assert not inspect(box(b"ftyp", b"heic\0\0\0\0mif1"))["valid"]


@pytest.mark.parametrize("factory", [legacy, modern])
@pytest.mark.parametrize("chunk", [1, 17, 1024 * 1024])
def test_motion_photo_exact_suffix_hashes(factory, chunk):
    clip = video(payload=b"\x11" * 300)
    image = jpeg(factory(len(clip)))
    result = inspect(image + clip, chunk)
    embedded = result["embedded_video"]
    assert result["valid"] and result["motion_photo"]["validated"]
    assert embedded["validated"]
    assert (embedded["offset"], embedded["size"]) == (len(image), len(clip))
    assert embedded["sha256"] == hashlib.sha256(clip).hexdigest()
    assert embedded["sha1"] == hashlib.sha1(clip).hexdigest()
    assert embedded["mime"] == "video/mp4"


def test_modern_primary_padding_and_directory_bounds():
    clip = video()
    image = jpeg(modern(len(clip), 5))
    assert inspect(image + b"\0" * 5 + clip)["embedded_video"]["offset"] == len(image) + 5
    result = inspect(image + clip)
    assert "embedded_video" not in result
    assert not result["motion_photo"]["validated"]
    assert result["motion_photo"]["issues"]


def test_legacy_offset_rejects_unexplained_gap_after_jpeg():
    clip = video()
    result = inspect(jpeg(legacy(len(clip))) + b"unaccounted bytes" + clip)
    assert result["valid"]  # The primary JPEG remains a structural image.
    assert "embedded_video" not in result
    assert not result["motion_photo"]["validated"]
    assert result["motion_photo"]["issues"]


@pytest.mark.parametrize("packet", [legacy(10**12), legacy(0), legacy(5, 'GCamera:MotionPhoto="1" GCamera:MotionPhotoVersion="1"'), modern(4), b"<!DOCTYPE x [<!ENTITY a 'x'>]><x>&a;</x>", b"<broken"])
def test_untrusted_xmp_never_promotes_embedded_video(packet):
    result = inspect(jpeg(packet) + video())
    assert "embedded_video" not in result
    assert result["motion_photo"]["issues"]


def test_modern_disabled_flag_does_not_fall_back_to_legacy():
    clip = video()
    result = inspect(jpeg(legacy(len(clip), 'GCamera:MotionPhoto="0"')) + clip)
    assert "embedded_video" not in result
    assert "motion_photo" not in result


def test_motion_requires_actual_video_track_and_complete_observed_size():
    audio = video(b"soun")
    result = inspect(jpeg(legacy(len(audio))) + audio)
    assert "embedded_video" not in result
    assert result["motion_photo"]["issues"]
    clip = video()
    data = jpeg(legacy(len(clip))) + clip
    inspector = MediaInspector(len(data) + 1)
    inspector.update(data)
    result = inspector.finish()
    assert not result["complete"] and "embedded_video" not in result


def test_unknown_length_container_works_but_motion_bounds_stay_unresolved():
    assert inspect(video(), total=False)["valid"]
    clip = video()
    result = inspect(jpeg(legacy(len(clip))) + clip, total=False)
    assert result["valid"]
    assert "embedded_video" not in result
    assert result["motion_photo"]["issues"]


def test_crc_and_nested_box_bounds_are_checked():
    png = bytearray(_png(1, 2, 3))
    png[40] ^= 1
    assert not inspect(bytes(png))["valid"]
    bad = box(b"ftyp", b"isom\0\0\0\0") + box(b"moov", struct.pack(">I4s", 1000, b"trak"))
    assert not inspect(bad)["valid"]


def test_mp4_child_header_cannot_cross_parent_between_updates():
    prefix = video() + box(b"moov", b"\0\0\0\x08")
    outside = b"abcd" + box(b"free", b"")
    inspector = MediaInspector(len(prefix) + len(outside))
    inspector.update(prefix)
    inspector.update(outside)
    result = inspector.finish()
    assert not result["valid"] and result["family"] == "unknown"
    assert "Box header exceeds its parent bounds" in result["issues"]


def test_avi_child_header_cannot_cross_list_between_updates():
    base = _avi()
    partial_list = b"LIST" + struct.pack("<I", 8) + b"testJUNK"
    outside = b"\0" * 4 + b"JUNK" + b"\0" * 4
    prefix = base[:4] + struct.pack("<I", len(base) + len(partial_list) + len(outside) - 8) + base[8:] + partial_list
    inspector = MediaInspector(len(prefix) + len(outside))
    inspector.update(prefix)
    inspector.update(outside)
    result = inspector.finish()
    assert not result["valid"] and result["family"] == "unknown"
    assert "AVI chunk header exceeds its list bounds" in result["issues"]


@pytest.mark.parametrize("total", [-1, 1.5, "100", True, 2**90])
def test_invalid_expected_lengths_are_safe_unresolved_results(total):
    inspector = MediaInspector(total)
    inspector.update(video())
    result = inspector.finish()
    assert result["family"] == "unknown"
    assert not result["valid"] and not result["complete"]
    assert "Invalid expected complete length" in result["issues"]


def test_cancellation_and_file_helper(tmp_path):
    path = tmp_path / "name.is.not.evidence"
    path.write_bytes(_avi())
    assert inspect_file(path)["family"] == "video"
    event = threading.Event()
    event.set()
    with pytest.raises(MediaCancelled):
        MediaInspector(cancel=event).update(b"anything")
    with pytest.raises(MediaCancelled):
        inspect_file(path, event)


def test_large_payload_is_skipped_without_retaining_it():
    inspector = MediaInspector(total_size=16 + 8 + 32 * 1024 * 1024)
    inspector.update(box(b"ftyp", b"isom\0\0\0\0"))
    inspector.update(struct.pack(">I4s", 32 * 1024 * 1024 + 8, b"mdat"))
    chunk = b"x" * (1024 * 1024)
    for _ in range(32):
        inspector.update(chunk)
    result = inspector.finish()
    assert not result["valid"]  # Movie metadata is deliberately absent.
    assert len(inspector.parser.header) <= 16
    assert len(inspector.probe) <= 16
    assert inspector.parser.leaf is None or len(inspector.parser.leaf[2]) <= 64
