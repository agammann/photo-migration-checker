"""Original generated-byte regressions; no external corpus content is copied."""
import json

import pytest

from pmc.source import scan_source


def put(root, name, value):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False).encode())


@pytest.mark.parametrize("name", ["métadonnées.json", "me\u0301tadonne\u0301es.json", "MÉTADONNÉES.JSON"])
def test_french_album_metadata_preserves_title_and_membership(tmp_path, name):
    put(tmp_path, "Album/picture.jpg", b"generated test content")
    put(tmp_path, "Album/picture.jpg.json", {"title": "picture.jpg", "photoTakenTime": {"timestamp": "100"}})
    put(tmp_path, "Album/" + name, {"title": "Known album title", "description": "", "access": "private"})
    manifest = scan_source(tmp_path)
    assert manifest["album_titles"] == {"Album": "Known album title"}
    assert [item["path"] for item in manifest["items"]] == ["Album/picture.jpg"]
    assert manifest["items"][0]["albums"] == ["Album"]
    assert not manifest["issues"]


@pytest.mark.parametrize("name,data", [
    ("métadonnées.json", {"title": "Arbitrary object"}),
    ("métadonnées.json", {"title": "picture.jpg", "description": "", "photoTakenTime": {"timestamp": "100"}}),
    ("métadonnées.json", {"title": "picture.jpg", "description": "", "googlePhotosOrigin": {"mobileUpload": {}}}),
    ("métadonnées.json", {"albumData": {"title": "Photo wrapper"}, "photoTakenTime": {"timestamp": "100"}}),
    ("unknown-translated-name.json", {"title": "Not asserted", "description": ""}),
])
def test_unproven_json_or_photo_sidecar_does_not_assert_album(tmp_path, name, data):
    put(tmp_path, "Album/picture.jpg", b"generated test content")
    put(tmp_path, "Album/" + name, data)
    manifest = scan_source(tmp_path)
    assert manifest["album_titles"] == {}
    assert all(not item["albums"] for item in manifest["items"])


def test_conflicting_localized_album_metadata_stays_unresolved(tmp_path):
    put(tmp_path, "Album/picture.jpg", b"generated test content")
    put(tmp_path, "Album/metadata.json", {"title": "One", "description": ""})
    put(tmp_path, "Album/métadonnées.json", {"title": "Two", "description": ""})
    manifest = scan_source(tmp_path)
    assert manifest["album_titles"] == {}
    assert all(not item["albums"] for item in manifest["items"])
    assert any(issue["code"] == "album_metadata_conflict" for issue in manifest["issues"])


@pytest.mark.parametrize("title", ["", "   "])
def test_empty_localized_album_title_is_explicitly_unresolved(tmp_path, title):
    put(tmp_path, "Album/picture.jpg", b"generated test content")
    put(tmp_path, "Album/métadonnées.json", {"title": title, "description": ""})
    manifest = scan_source(tmp_path)
    assert manifest["album_titles"] == {}
    assert len(manifest["items"]) == 1 and not manifest["items"][0]["albums"]
    assert any(issue["code"] == "album_metadata_unresolved" for issue in manifest["issues"])
