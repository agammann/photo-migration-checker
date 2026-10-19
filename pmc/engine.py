"""SQLite checkpoints and a single bounded background worker per application."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .compare import compare
from .immich import Cancelled, Immich, ImmichError, signature
from .media import MediaCancelled, MediaInspector
from .source import SourceCancelled, scan_source


def now():
    return datetime.now(timezone.utc).isoformat()


def fingerprint(destination):
    return hashlib.sha256(json.dumps({"assets": sorted(destination["assets"], key=lambda a: a["id"]),
                                      "albums": sorted(destination["albums"], key=lambda a: a["id"])},
                                     sort_keys=True).encode()).hexdigest()


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self.connect() as db:
            db.executescript("""CREATE TABLE IF NOT EXISTS scans(id TEXT PRIMARY KEY, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS originals(scan_id TEXT, asset_id TEXT, signature TEXT, data TEXT,
            PRIMARY KEY(scan_id, asset_id));
            CREATE TABLE IF NOT EXISTS manifests(scan_id TEXT PRIMARY KEY, source TEXT, destination TEXT);""")
        # Process shutdown is not completion. Re-entry requires a new in-memory key.
        for job in self.list():
            if job["status"] == "running":
                job["status"] = "interrupted"
                job["phase"] = "Interrupted; reconnect to resume"
                self.save(job)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        try:
            with db:
                yield db
        finally:
            db.close()

    def save(self, job):
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO scans VALUES(?,?)", (job["id"], json.dumps(job)))

    def get(self, ident):
        with self.connect() as db:
            row = db.execute("SELECT data FROM scans WHERE id=?", (ident,)).fetchone()
        if not row:
            raise KeyError(ident)
        return json.loads(row[0])

    def list(self):
        with self.connect() as db:
            return [json.loads(row[0]) for row in db.execute("SELECT data FROM scans ORDER BY rowid DESC")]

    def original(self, scan_id, ident, sig):
        with self.connect() as db:
            row = db.execute("SELECT data FROM originals WHERE scan_id=? AND asset_id=? AND signature=?", (scan_id, ident, sig)).fetchone()
        return json.loads(row[0]) if row else None

    def checkpoint(self, scan_id, ident, sig, data):
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO originals VALUES(?,?,?,?)", (scan_id, ident, sig, json.dumps(data)))

    def manifest(self, scan_id, source, destination):
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO manifests VALUES(?,?,?)", (scan_id, json.dumps(source), json.dumps(destination)))


def public_job(job):
    return {k: v for k, v in job.items() if k not in {"source_path", "destination_url", "manifest", "destination"}}


class SampleDestination:
    """A real local byte fixture, explicitly not an Immich server."""
    def __init__(self, fixture):
        self.fixture = fixture
        self.url = "sample://" + fixture.get("scenario", "problems")

    def inventory(self, cancel=None, progress=None):
        return {"assets": self.fixture["assets"], "albums": self.fixture["albums"], "version": "3.3.3", "issues": []}

    def hash_original(self, ident, cancel=None):
        s256, s1, size = hashlib.sha256(), hashlib.sha1(), 0
        path = Path(self.fixture["originals"][ident])
        media = MediaInspector(total_size=path.stat().st_size, cancel=cancel)
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                if cancel and cancel.is_set():
                    raise Cancelled()
                s256.update(chunk)
                s1.update(chunk)
                size += len(chunk)
                try:
                    media.update(chunk)
                except MediaCancelled:
                    raise Cancelled() from None
        try:
            media_proof = media.finish()
        except MediaCancelled:
            raise Cancelled() from None
        return {"sha256": s256.hexdigest(), "sha1": s1.hexdigest(), "size": size, "media": media_proof}


class Manager:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.store = Store(data_dir / "scans.sqlite3")
        self.connections, self.sources = {}, {}
        self.lock = threading.Lock()
        self.cancellations = {}
        self.active = None

    def connection(self, adapter):
        ident = str(uuid.uuid4())
        self.connections[ident] = adapter
        return ident

    def source(self, path):
        ident = str(uuid.uuid4())
        root = Path(path).resolve(strict=True)
        if self.data_dir.resolve().is_relative_to(root):
            raise ValueError("The checkpoint directory must be outside the source folder.")
        self.sources[ident] = str(root)
        return ident

    def start(self, source_id, connection_id, mode, download_consent=False, demo=False):
        if mode not in {"original", "checksum"}:
            raise ValueError("Choose a documented verification mode.")
        if mode == "original" and not download_consent:
            raise ValueError("Original verification requires explicit download consent.")
        source = self.sources[source_id]
        adapter = self.connections[connection_id]
        job = {"id": str(uuid.uuid4()), "source_path": source, "destination_url": adapter.url,
               "mode": mode, "demo": demo or isinstance(adapter, SampleDestination), "created_at": now(),
               "demo_scenario": adapter.fixture.get("scenario", "problems") if isinstance(adapter, SampleDestination) else None,
               "status": "running", "phase": "Queued", "progress": {}, "report": None, "error": None}
        self._launch(job, adapter)
        return public_job(job)

    def resume(self, ident, connection_id):
        job = self.store.get(ident)
        if job["status"] not in {"cancelled", "interrupted", "failed"}:
            raise ValueError("Only stopped or interrupted scans can resume.")
        adapter = self.connections[connection_id]
        if adapter.url != job["destination_url"]:
            raise ValueError("Reconnect to the same destination to resume this scan.")
        job.update(status="running", phase="Resuming; rechecking source and destination", error=None, report=None)
        self._launch(job, adapter)
        return public_job(job)

    def _launch(self, job, adapter):
        with self.lock:
            if self.active:
                raise ValueError("Another scan is running. Cancel or finish it first.")
            self.active = job["id"]
            event = threading.Event()
            self.cancellations[job["id"]] = event
            self.store.save(job)
            threading.Thread(target=self._run, args=(job, adapter, event), daemon=True).start()

    def cancel(self, ident):
        if ident in self.cancellations:
            self.cancellations[ident].set()
        return public_job(self.store.get(ident))

    def _run(self, job, adapter, event):
        def progress(data):
            job["progress"] = data
            job["phase"] = data.get("phase", "Scanning")
            self.store.save(job)
        try:
            manifest = scan_source(Path(job["source_path"]), event, progress)
            progress({"phase": "Reading destination inventory"})
            destination = adapter.inventory(event, progress)
            self.store.manifest(job["id"], manifest, destination)
            verified, transferred, reused = {}, 0, 0
            if job["mode"] == "original":
                for index, asset in enumerate(destination["assets"]):
                    if event.is_set():
                        raise Cancelled()
                    ident = asset["id"]
                    sig = signature(asset)
                    # Deliberately redownload on resume: unchanged database metadata
                    # does not prove unchanged bytes on disk. Checkpoints preserve
                    # work/evidence for audit but are not promoted to fresh proof.
                    try:
                        verified[ident] = adapter.hash_original(ident, event)
                        transferred += verified[ident]["size"]
                        self.store.checkpoint(job["id"], ident, sig, verified[ident])
                    except ImmichError as e:
                        verified[ident] = {"error": str(e)}
                    progress({"phase": "Hashing destination originals", "assets_scanned": index + 1,
                              "assets_total": len(destination["assets"]), "bytes_transferred": transferred, "checkpoints_reused": reused})
            if event.is_set():
                raise Cancelled()
            progress({"phase": "Rechecking source and destination for changes"})
            final_source = scan_source(Path(job["source_path"]), event)
            if manifest["inventory"] != final_source["inventory"]:
                manifest["issues"].append({"kind": "source_changed", "message": "Source files or metadata changed during this scan. Results are incomplete; rescan a stable folder."})
            final_destination = adapter.inventory(event)
            if fingerprint(destination) != fingerprint(final_destination):
                destination["issues"].append({"kind": "destination_changed", "message": "Destination assets or album memberships changed during this scan; coverage is incomplete."})
            destination["issues"].extend(final_destination.get("issues", []))
            report = compare(manifest, destination, job["mode"], verified)
            report.update(created_at=now(), scan_id=job["id"], demo=job["demo"], bytes_transferred=transferred)
            # No local root, server URL, GPS, API key, or raw server payload is exported.
            job.update(status="completed", phase="Scan finished; review evidence", report=report)
        except (Cancelled, SourceCancelled):
            job.update(status="cancelled", phase="Cancelled; reconnect to resume")
        except (OSError, ValueError, ImmichError):
            job.update(status="failed", phase="Scan stopped", error="Scan could not finish. Check folder access, server connection, permissions and the supported API version, then resume.")
        except Exception:
            job.update(status="failed", phase="Scan stopped", error="Unexpected scan failure. No completion claim was made; reconnect and retry.")
        finally:
            job["finished_at"] = now()
            self.store.save(job)
            with self.lock:
                self.active = None
                self.cancellations.pop(job["id"], None)
