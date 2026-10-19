"""Durable checkpoints and controlled changes/cancellation using local bytes."""
from __future__ import annotations

import copy
import hashlib
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import tempfile
import threading
import unittest
import uuid
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from pmc.engine import Manager, SampleDestination, Store
from pmc.immich import Cancelled, Immich, ImmichError, signature
from pmc.sample import create_sample
from pmc.source import scan_source


def snapshot(root):
    return {path.relative_to(root).as_posix(): (path.stat().st_size, path.stat().st_mtime_ns, hashlib.sha256(path.read_bytes()).hexdigest()) for path in root.rglob("*") if path.is_file()}


class ObservedManager(Manager):
    def __init__(self, data_dir):
        self.finished = threading.Event()
        super().__init__(data_dir)
    def _run(self, *args):
        try:
            return super()._run(*args)
        finally:
            self.finished.set()


class CountingDestination(SampleDestination):
    def __init__(self, sample):
        super().__init__(sample)
        self.downloads = []
        self.inventories = 0
    def inventory(self, *args, **kwargs):
        self.inventories += 1
        return copy.deepcopy(super().inventory(*args, **kwargs))
    def hash_original(self, ident, cancel=None):
        self.downloads.append(ident)
        return super().hash_original(ident, cancel)


class EngineTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="pmc-engine-test-")
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.sample = create_sample(self.base / "fixture", "correct")

    def launch(self, adapter=None, mode="original"):
        manager = ObservedManager(self.base / str(uuid.uuid4()))
        adapter = adapter or CountingDestination(self.sample)
        source_id = manager.source(self.sample["source"])
        connection_id = manager.connection(adapter)
        job = manager.start(source_id, connection_id, mode, download_consent=mode == "original")
        return manager, adapter, job, connection_id

    def finish(self, manager, job):
        self.assertTrue(manager.finished.wait(10), "Scan worker did not finish")
        result = manager.store.get(job["id"])
        self.assertIsNone(manager.active)
        return result

    def test_complete_original_scan_persists_manifest_and_evidence_without_source_changes(self):
        before = snapshot(self.sample["source"])
        manager, adapter, job, _ = self.launch()
        result = self.finish(manager, job)
        self.assertEqual(result["status"], "completed", result.get("error"))
        self.assertEqual(result["report"]["summary"]["attention"], 0)
        self.assertTrue(result["report"]["summary"]["coverage_complete"])
        self.assertEqual(len(adapter.downloads), 7)
        self.assertEqual(adapter.inventories, 2)
        self.assertEqual(snapshot(self.sample["source"]), before)
        self.assertEqual(result["report"]["bytes_transferred"], sum(path.stat().st_size for path in self.sample["originals"].values()))
        with manager.store.connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM originals WHERE scan_id=?", (job["id"],)).fetchone()[0], 7)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM manifests WHERE scan_id=?", (job["id"],)).fetchone()[0], 1)

    def test_checksum_mode_does_not_download_originals(self):
        manager, adapter, job, _ = self.launch(mode="checksum")
        result = self.finish(manager, job)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(adapter.downloads, [])
        self.assertEqual(result["report"]["bytes_transferred"], 0)
        self.assertEqual(result["report"]["summary"]["content_counts"], {"checksum": 8})

    def test_original_download_requires_explicit_choice(self):
        manager = Manager(self.base / "no-consent")
        source_id = manager.source(self.sample["source"])
        connection_id = manager.connection(CountingDestination(self.sample))
        with self.assertRaisesRegex(ValueError, "explicit"):
            manager.start(source_id, connection_id, "original")
        self.assertEqual(manager.store.list(), [])

    def test_source_changes_during_scan_are_detected(self):
        sample = self.sample
        class Mutating(CountingDestination):
            def hash_original(self, ident, cancel=None):
                result = super().hash_original(ident, cancel)
                if len(self.downloads) == 1:
                    with (sample["source"] / "Family/sunrise.png").open("ab") as handle:
                        handle.write(b"change made during controlled test")
                return result
        manager, _, job, _ = self.launch(Mutating(sample))
        result = self.finish(manager, job)
        self.assertEqual(result["status"], "completed")
        self.assertFalse(result["report"]["summary"]["coverage_complete"])
        self.assertTrue(any(f["kind"] == "source_changed" for f in result["report"]["findings"]))

    def test_destination_metadata_changes_during_scan_are_detected(self):
        class Mutating(CountingDestination):
            def inventory(self, *args, **kwargs):
                inventory = super().inventory(*args, **kwargs)
                if self.inventories > 1:
                    inventory["assets"][0]["updatedAt"] = "2024-01-01T00:00:00Z"
                return inventory
        manager, _, job, _ = self.launch(Mutating(self.sample))
        result = self.finish(manager, job)
        self.assertFalse(result["report"]["summary"]["coverage_complete"])
        self.assertTrue(any(f["kind"] == "destination_changed" for f in result["report"]["findings"]))

    def test_original_permission_failure_keeps_coverage_incomplete(self):
        class Blocked(CountingDestination):
            def hash_original(self, ident, cancel=None):
                raise ImmichError("Original inaccessible (HTTP 403).")
        manager, _, job, _ = self.launch(Blocked(self.sample))
        result = self.finish(manager, job)
        self.assertEqual(result["status"], "completed")
        self.assertFalse(result["report"]["summary"]["coverage_complete"])
        self.assertFalse(any(f["status"] == "missing" for f in result["report"]["findings"]))

    def test_cancel_and_resume_rechecks_bytes_instead_of_promoting_checkpoint(self):
        entered, release = threading.Event(), threading.Event()
        class Blocking(CountingDestination):
            def hash_original(self, ident, cancel=None):
                if len(self.downloads) == 1:
                    entered.set()
                    if not release.wait(10):
                        raise AssertionError("Test did not release the controlled download")
                    if cancel.is_set():
                        raise Cancelled()
                return super().hash_original(ident, cancel)
        manager, adapter, job, connection_id = self.launch(Blocking(self.sample))
        try:
            self.assertTrue(entered.wait(10), "Scan did not reach controlled second download")
            manager.cancel(job["id"])
        finally:
            release.set()
        cancelled = self.finish(manager, job)
        self.assertEqual(cancelled["status"], "cancelled")
        self.assertIsNone(cancelled["report"])
        self.assertEqual(len(adapter.downloads), 1)
        manager.finished.clear()
        manager.resume(job["id"], connection_id)
        resumed = self.finish(manager, job)
        self.assertEqual(resumed["status"], "completed")
        self.assertEqual(len(adapter.downloads), 8, "Resume must redownload all 7 originals, including the prior checkpoint")
        self.assertTrue(resumed["report"]["summary"]["coverage_complete"])

    def test_restart_marks_interrupted_and_requires_new_connection_before_resume(self):
        data_dir = self.base / "restart"
        store = Store(data_dir / "scans.sqlite3")
        destination = CountingDestination(self.sample)
        ident = str(uuid.uuid4())
        job = {"id": ident, "source_path": str(self.sample["source"]), "destination_url": destination.url,
               "status": "running", "phase": "Hashing", "mode": "original", "demo": True,
               "created_at": "2026-10-18T00:00:00Z", "progress": {}, "report": None, "error": None}
        store.save(job)
        asset = self.sample["assets"][0]
        original = destination.hash_original(asset["id"])
        store.checkpoint(ident, asset["id"], signature(asset), original)
        store.manifest(ident, scan_source(self.sample["source"]), destination.inventory())
        manager = ObservedManager(data_dir)
        self.assertEqual(manager.store.get(ident)["status"], "interrupted")
        self.assertEqual(manager.connections, {})
        self.assertEqual(manager.store.original(ident, asset["id"], signature(asset)), original)
        self.assertIsNone(manager.store.original(ident, asset["id"], "changed signature"))
        reconnected = CountingDestination(self.sample)
        connection_id = manager.connection(reconnected)
        manager.resume(ident, connection_id)
        result = self.finish(manager, job)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(len(reconnected.downloads), 7, "Historical checkpoint is audit evidence, never fresh byte proof")
        self.assertEqual(result["report"]["summary"]["attention"], 0)

    def test_resume_rejects_different_destination(self):
        data_dir = self.base / "different"
        manager = Manager(data_dir)
        job = {"id": "stopped", "status": "cancelled", "destination_url": "sample://different"}
        manager.store.save(job)
        connection_id = manager.connection(CountingDestination(self.sample))
        with self.assertRaisesRegex(ValueError, "same destination"):
            manager.resume("stopped", connection_id)

    def test_real_loopback_http_protocol_fixture_downloads_bytes_read_only(self):
        """Exercise actual sockets; this service is explicitly not real Immich."""
        sample, calls = self.sample, []
        asset_map = {asset["id"]: asset for asset in sample["assets"]}
        class ProtocolFixture(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass
            def payload(self, data, status=200):
                content = json.dumps(data).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
            def authorized(self):
                calls.append((self.command, self.path))
                if self.headers.get("x-api-key") != "local-protocol-fixture-key":
                    self.payload({}, 401)
                    return False
                return True
            def do_GET(self):
                if not self.authorized():
                    return
                url = urlsplit(self.path)
                if url.path == "/api/server/version":
                    self.payload({"major": 3, "minor": 3, "patch": 3})
                elif url.path == "/api/albums":
                    self.payload(sample["albums"])
                elif url.path.startswith("/api/assets/"):
                    ident = url.path.split("/")[3]
                    if url.path.endswith("/original"):
                        if parse_qs(url.query) != {"edited": ["false"]}:
                            return self.payload({}, 400)
                        original = sample["originals"][ident]
                        self.send_response(200)
                        self.send_header("Content-Length", str(original.stat().st_size))
                        self.end_headers()
                        with original.open("rb") as stream:
                            for chunk in iter(lambda: stream.read(7), b""):
                                self.wfile.write(chunk)
                    else:
                        self.payload(asset_map[ident])
                else:
                    self.payload({}, 404)
            def do_POST(self):
                if not self.authorized():
                    return
                if self.path != "/api/search/metadata":
                    return self.payload({}, 405)
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                assets = sample["assets"]
                album_ids = body.get("filter", {}).get("albumIds", {}).get("any", [])
                if album_ids:
                    album = next(album for album in sample["albums"] if album["id"] == album_ids[0])
                    assets = [asset for asset in assets if asset["id"] in album["asset_ids"]]
                offset = int(body.get("cursor", 0))
                page = assets[offset:offset + 2]
                cursor = str(offset + 2) if offset + 2 < len(assets) else None
                self.payload({"assets": {"items": page, "nextCursor": cursor}})
        server = ThreadingHTTPServer(("127.0.0.1", 0), ProtocolFixture)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        adapter = Immich(f"http://127.0.0.1:{server.server_port}", "local-protocol-fixture-key")
        before = snapshot(sample["source"])
        try:
            manager, _, job, _ = self.launch(adapter)
            result = self.finish(manager, job)
            self.assertEqual(result["status"], "completed", result.get("error"))
            self.assertEqual(result["report"]["summary"]["attention"], 0)
            self.assertEqual(result["report"]["summary"]["matched"], 8)
            self.assertGreater(result["report"]["bytes_transferred"], 0)
            self.assertEqual(snapshot(sample["source"]), before)
            self.assertTrue(calls)
            self.assertTrue(all(method == "GET" or (method == "POST" and path == "/api/search/metadata") for method, path in calls))
            self.assertEqual(len([path for method, path in calls if "/original?" in path]), 7)
        finally:
            adapter.close()
            server.shutdown()
            server.server_close()
            worker.join(5)


if __name__ == "__main__":
    unittest.main()
