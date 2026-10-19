"""Deterministic adapter contract checks; these are not live Immich validation."""
import base64
import hashlib
import json
import threading

import httpx
import pytest

from pmc.immich import Cancelled, Immich, ImmichError, decode_checksum, normalize_url

A = "11111111-1111-4111-8111-111111111111"
B = "22222222-2222-4222-8222-222222222222"
ALBUM = "33333333-3333-4333-8333-333333333333"


def asset(ident=A):
    return {"id": ident, "originalFileName": "photo.jpg", "checksum": base64.b64encode(hashlib.sha1(b"photo").digest()).decode(),
            "libraryId": None, "updatedAt": "2024-01-01T00:00:00Z"}


def page(items, cursor=None):
    return {"assets": {"items": items, "count": len(items), "total": len(items), "nextCursor": cursor, "nextPage": None}}


def transport(search=None, albums=None, original=b"photo", read_asset=None):
    def handle(request):
        path = request.url.path
        assert request.headers["x-api-key"] == "local-test-secret"
        assert "apiKey" not in request.url.params
        if path == "/api/server/version":
            return httpx.Response(200, json={"major": 3, "minor": 3, "patch": 3})
        if path == "/api/albums":
            return httpx.Response(200, json=albums or [])
        if path == "/api/search/metadata":
            assert request.method == "POST"
            body = json.loads(request.content)
            assert body["withExif"] is True and body["withStacked"] is True
            assert "filter" in body and "page" not in body
            assert body["filter"]["trashedAt"] == {"eq": None}
            return search(request, body) if search else httpx.Response(200, json=page([asset()]))
        if path == f"/api/assets/{A}/original":
            assert request.url.params["edited"] == "false"
            return httpx.Response(200, content=original)
        if path == f"/api/assets/{A}":
            return httpx.Response(200, json=read_asset() if read_asset else asset())
        raise AssertionError(f"Unexpected checker request: {request.method} {path}")
    return httpx.MockTransport(handle)


def adapter(mock):
    return Immich("http://127.0.0.1:2283", "local-test-secret", transport=mock)


def test_original_stream_inspects_container_without_trusting_filename():
    from pmc.sample import _avi
    content = _avi()
    def handle(request):
        if request.url.path.endswith("/original"):
            assert request.headers["accept-encoding"] == "identity"
            assert request.url.params["edited"] == "false"
            return httpx.Response(200, content=content)
        return httpx.Response(200, json=asset())
    reader = adapter(httpx.MockTransport(handle))
    try:
        proof = reader.hash_original(A)
        assert proof["sha256"] == hashlib.sha256(content).hexdigest()
        assert proof["size"] == len(content)
        assert proof["media"]["family"] == "video"
        assert proof["media"]["container"] == "avi"
        assert proof["media"]["valid"] is True
    finally:
        reader.close()


def test_cursor_inventory_and_album_membership():
    bodies = []
    def search(request, body):
        bodies.append(body)
        if body["filter"].get("albumIds"):
            assert body["filter"] == {"albumIds": {"any": [ALBUM]}, "trashedAt": {"eq": None}}
            return httpx.Response(200, json=page([asset(B)]))
        if body.get("cursor"):
            assert body["cursor"] == "opaque-next"
            return httpx.Response(200, json=page([asset(B)]))
        return httpx.Response(200, json=page([asset()], "opaque-next"))
    with_adapter = adapter(transport(search, [{"id": ALBUM, "albumName": "Trip"}]))
    result = with_adapter.inventory()
    assert result["version"] == "3.3.3" and not result["issues"]
    assert [a["id"] for a in result["assets"]] == [A, B]
    assert result["albums"][0]["asset_ids"] == [B]
    assert len(bodies) == 3
    assert all(m == "GET" or (m == "POST" and p == "/search/metadata") for m, p in with_adapter.requests)
    with_adapter.close()


def test_repeated_cursor_stops_and_marks_incomplete():
    client = adapter(transport(lambda *_: httpx.Response(200, json=page([asset()], "again"))))
    result = client.inventory()
    assert len(result["assets"]) == 1
    assert any(i["kind"] == "pagination" for i in result["issues"])
    assert any(i["kind"] == "destination_changed" for i in result["issues"])
    client.close()


def test_missing_cursor_field_is_incomplete():
    client = adapter(transport(lambda *_: httpx.Response(200, json={"assets": {"items": [asset()]}})))
    result = client.inventory()
    assert any(i["kind"] == "pagination" for i in result["issues"])
    client.close()


@pytest.mark.parametrize("failure", ["permission", "timeout"])
def test_partial_pages_survive_failed_next_request(failure):
    def search(request, body):
        if body.get("cursor"):
            if failure == "timeout":
                raise httpx.ReadTimeout("sensitive-provider-text-local-test-secret", request=request)
            return httpx.Response(403, json={"message": "private-local-test-secret"})
        return httpx.Response(200, json=page([asset()], "next"))
    client = adapter(transport(search))
    result = client.inventory()
    assert len(result["assets"]) == 1
    assert any(i["kind"] == "destination_inaccessible" for i in result["issues"])
    assert "local-test-secret" not in json.dumps(result["issues"])
    client.close()


def test_original_hash_uses_original_endpoint_and_both_hashes():
    media = b"original-media\x00" * 150000
    client = adapter(transport(original=media))
    result = client.hash_original(A)
    assert result["sha256"] == hashlib.sha256(media).hexdigest()
    assert result["sha1"] == hashlib.sha1(media).hexdigest()
    assert result["size"] == len(media)
    assert client.requests == [("GET", f"/assets/{A}"), ("GET", f"/assets/{A}/original"), ("GET", f"/assets/{A}")]
    client.close()


def test_original_asset_change_invalidates_hash():
    calls = []
    def read():
        calls.append(1)
        return {**asset(), "updatedAt": str(len(calls))}
    client = adapter(transport(read_asset=read))
    with pytest.raises(ImmichError, match="changed"):
        client.hash_original(A)
    client.close()


def test_unexpected_trashed_asset_is_excluded_and_marks_incomplete():
    client = adapter(transport(lambda *_: httpx.Response(200, json=page([{**asset(), "isTrashed": True}]))))
    result = client.inventory()
    assert result["assets"] == []
    assert any(i["kind"] == "destination_changed" for i in result["issues"])
    client.close()


def test_shared_album_only_asset_is_included_without_private_metadata():
    def search(request, body):
        if body["filter"].get("albumIds"):
            private = {**asset(B), "originalPath": "/private/server/library/photo.jpg",
                       "owner": {"email": "private@example.invalid"},
                       "exifInfo": {"fileSizeInByte": 100, "latitude": 42.1, "longitude": -71.2},
                       "stack": {"id": ALBUM, "primaryAssetId": B, "assetCount": 2}}
            return httpx.Response(200, json=page([private]))
        return httpx.Response(200, json=page([asset()]))
    client = adapter(transport(search, [{"id": ALBUM, "albumName": "Shared"}]))
    result = client.inventory()
    assert not result["issues"]
    assert {a["id"] for a in result["assets"]} == {A, B}
    member = next(a for a in result["assets"] if a["id"] == B)
    assert member["exifInfo"] == {"fileSizeInByte": 100}
    assert member["stack"]["assetCount"] == 2
    assert not {"originalPath", "owner"} & member.keys()
    assert "latitude" not in json.dumps(result)
    client.close()


def test_repeated_asset_changed_between_library_and_album_is_flagged():
    def search(request, body):
        value = asset()
        if body["filter"].get("albumIds"):
            value["updatedAt"] = "2025-01-01T00:00:00Z"
        return httpx.Response(200, json=page([value]))
    client = adapter(transport(search, [{"id": ALBUM, "albumName": "Trip"}]))
    result = client.inventory()
    assert len(result["assets"]) == 1
    assert any(i["kind"] == "destination_changed" for i in result["issues"])
    client.close()


def test_private_gps_change_does_not_invalidate_original_content_evidence():
    calls = []
    def read():
        calls.append(1)
        return {**asset(), "exifInfo": {"fileSizeInByte": 5, "latitude": len(calls)}, "originalPath": "/private.jpg"}
    client = adapter(transport(read_asset=read))
    assert client.hash_original(A)["sha256"] == hashlib.sha256(b"photo").hexdigest()
    client.close()


def test_newly_trashed_original_is_not_downloaded():
    client = adapter(transport(read_asset=lambda: {**asset(), "isTrashed": True}))
    with pytest.raises(ImmichError, match="trashed"):
        client.hash_original(A)
    assert client.requests == [("GET", f"/assets/{A}")]
    client.close()


def test_cancelled_inventory_and_original_stop():
    cancel = threading.Event()
    cancel.set()
    client = adapter(transport())
    with pytest.raises(Cancelled):
        client.inventory(cancel)
    with pytest.raises(Cancelled):
        client.hash_original(A, cancel)
    client.close()


@pytest.mark.parametrize("method,path", [("POST", "/assets"), ("PUT", f"/assets/{A}"),
                                           ("DELETE", f"/assets/{A}"), ("PATCH", "/albums"),
                                           ("GET", "/users/me"), ("POST", "/search/metadata/other")])
def test_allowlist_blocks_unapproved_methods_before_transport(method, path):
    client = adapter(httpx.MockTransport(lambda _: pytest.fail("Blocked request reached transport")))
    with pytest.raises(ImmichError, match="allowlist"):
        client._json(method, path)
    assert not client.requests
    client.close()


def test_checksum_decoding_requires_documented_sha1_shape():
    expected = hashlib.sha1(b"photo").hexdigest()
    assert decode_checksum(base64.b64encode(bytes.fromhex(expected)).decode()) == expected
    for value in ("not base64", expected, "", None, base64.b64encode(b"short").decode()):
        assert decode_checksum(value) is None


@pytest.mark.parametrize("value", ["https://user:secret@example.com", "https://example.com?key=secret", "file:///secret", "https://example.com/#fragment"])
def test_server_urls_disallow_credentials_and_non_http_inputs(value):
    with pytest.raises(ValueError):
        normalize_url(value)
