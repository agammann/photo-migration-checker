"""Controlled failure checks against the owned real disposable Immich instance.

Source mutation affects a new copy only. Destination mutation creates one unique
test album and deletes only that returned ID. Timeout responses come from the
real server through the separate, explicitly delayed read observer.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import threading
import time
import uuid
from urllib.parse import urlsplit

import httpx

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parents[1]
sys.path.insert(0, str(ROOT))

from pmc.engine import Manager, fingerprint
from pmc.immich import Immich


def dump(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def snapshot(root: Path) -> dict:
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            info = path.stat()
            result[path.relative_to(root).as_posix()] = {
                "sha256": digest.hexdigest(), "size": info.st_size, "mtime_ns": info.st_mtime_ns}
    return result


def raw_originals(client: httpx.Client, base: str, key: str, inventory: dict) -> dict:
    result = {}
    for asset in inventory["assets"]:
        digest, size = hashlib.sha256(), 0
        with client.stream("GET", base + "/api/assets/" + asset["id"] + "/original",
                           headers={"x-api-key": key}, params={"edited": "false"}) as response:
            assert response.status_code == 200, "Independent original observation failed"
            for chunk in response.iter_bytes(1024 * 1024):
                digest.update(chunk)
                size += len(chunk)
        result[asset["id"]] = {"sha256": digest.hexdigest(), "size": size}
    return result


class InventoryBarrier(Immich):
    """Scheduling barrier after one unmodified actual network inventory."""
    def __init__(self, url: str, key: str):
        super().__init__(url, key)
        self.entered = threading.Event()
        self.release = threading.Event()
        self.inventories = 0

    def inventory(self, *args, **kwargs):
        inventory = super().inventory(*args, **kwargs)
        self.inventories += 1
        if self.inventories == 1:
            self.entered.set()
            if not self.release.wait(30):
                raise RuntimeError("Controlled inventory barrier was not released")
        return inventory


def launch(work: Path, label: str, source: Path, adapter: Immich):
    manager = Manager(work / (label + "-state"))
    job = manager.start(manager.source(source), manager.connection(adapter), "original", download_consent=True)
    return manager, job


def finish(manager: Manager, job: dict, timeout: float = 120) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = manager.store.get(job["id"])
        if result["status"] != "running" and manager.active is None:
            assert result["status"] == "completed", "Controlled failure scan did not produce a completed evidence report"
            return result["report"]
        time.sleep(.025)
    manager.cancel(job["id"])
    raise RuntimeError("Controlled failure scan exceeded its deadline")


def check_report(report: dict, kind: str) -> None:
    assert not report["summary"]["coverage_complete"], "Failure incorrectly claimed complete coverage"
    assert any(f["kind"] == kind for f in report["findings"]), "Failure evidence was not recorded"


def read_only(requests: list) -> bool:
    return all(method == "GET" or (method == "POST" and path == "/search/metadata")
               for method, path in requests)


def run(state_path: Path, work: Path, timeout_observer: str, timeout_ledger: Path) -> dict:
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["url"] == "http://127.0.0.1:22839", "Unexpected disposable server URL"
    assert state["version"] == "3.3.3" and state["project"].startswith("pmc-test-"), "Unowned disposable state"
    observer = urlsplit(timeout_observer)
    assert (observer.scheme == "http" and observer.hostname == "127.0.0.1"
            and observer.port is not None and observer.port != 22839
            and observer.path in {"", "/"} and not observer.query and not observer.fragment
            and observer.username is None and observer.password is None), "Timeout checks require a dedicated loopback observer"
    case = state["scenarios"]["correct"]
    source = Path(case["source"]).resolve()
    assert source.is_relative_to(state_path.parent.resolve()), "Fixture source is outside owned work directory"
    work.mkdir(parents=True, exist_ok=True)
    source_copy = work / "source-copy"
    if source_copy.exists():
        raise RuntimeError("Source-copy path already exists; choose a fresh work directory")
    shutil.copytree(source, source_copy)
    source_before = snapshot(source)
    source_copy_before = snapshot(source_copy)
    receipt = {"status": "running", "immich_version": "3.3.3", "checks": {},
               "checker_write_requests": 0, "setup_requests": []}
    key, base = case["key"], state["url"]
    with httpx.Client(timeout=30, trust_env=False, follow_redirects=False) as raw:
        baseline_reader = Immich(base, key)
        try:
            baseline = baseline_reader.inventory()
            assert not baseline["issues"], "Baseline inventory is incomplete"
            originals_before = raw_originals(raw, base, key, baseline)

            source_adapter = InventoryBarrier(base, key)
            try:
                manager, job = launch(work, "source-change", source_copy, source_adapter)
                try:
                    assert source_adapter.entered.wait(30), "Source check missed its inventory barrier"
                    target = next(source_copy.rglob("*.png"))
                    with target.open("ab") as stream:
                        stream.write(b"\nControlled source-change test\n")
                finally:
                    source_adapter.release.set()
                report = finish(manager, job)
                check_report(report, "source_changed")
                assert read_only(source_adapter.requests), "Source check attempted a non-read request"
                assert source_copy_before != snapshot(source_copy), "Controlled source mutation did not occur"
                assert source_before == snapshot(source), "Original correct fixture changed"
                dump(work / "source-change-report.json", report)
                receipt["checks"]["source_change"] = {"status": "passed", "mutation": "Appended bytes to new fixture copy",
                    "original_fixture_unchanged": True, "coverage_complete": False,
                    "checker_requests": source_adapter.requests}
            finally:
                source_adapter.release.set()
                source_adapter.close()

            # This separate setup client is the only writer. The application's
            # restricted key and network adapter never receive its bearer token.
            account = state["correct"]
            login = raw.post(base + "/api/auth/login", json={k: account[k] for k in ("email", "password")})
            receipt["setup_requests"].append({"method": "POST", "path": "/api/auth/login", "status": login.status_code})
            assert login.status_code == 201, "Disposable account login failed"
            authorization = {"Authorization": "Bearer " + login.json()["accessToken"]}
            album_id = None
            destination_adapter = InventoryBarrier(base, key)
            try:
                manager, job = launch(work, "destination-change", source, destination_adapter)
                try:
                    assert destination_adapter.entered.wait(30), "Destination check missed its inventory barrier"
                    created = raw.post(base + "/api/albums", headers=authorization,
                        json={"albumName": "Controlled mutation " + uuid.uuid4().hex, "assetIds": []})
                    receipt["setup_requests"].append({"method": "POST", "path": "/api/albums", "status": created.status_code})
                    assert created.status_code == 201, "Disposable album creation failed"
                    album_id = created.json()["id"]
                finally:
                    destination_adapter.release.set()
                report = finish(manager, job)
                check_report(report, "destination_changed")
                assert read_only(destination_adapter.requests), "Destination check attempted a non-read request"
                dump(work / "destination-change-report.json", report)
                receipt["checks"]["destination_change"] = {"status": "passed", "mutation": "Setup created one unique empty album",
                    "coverage_complete": False, "checker_requests": destination_adapter.requests}
            finally:
                destination_adapter.release.set()
                destination_adapter.close()
                if album_id:
                    removed = raw.delete(base + "/api/albums/" + album_id, headers=authorization)
                    receipt["setup_requests"].append({"method": "DELETE", "path": "/api/albums/" + album_id,
                                                       "status": removed.status_code})
                    assert removed.status_code == 204, "Controlled album cleanup failed"
            restored = baseline_reader.inventory()
            assert fingerprint(baseline) == fingerprint(restored), "Destination baseline was not restored"
            assert originals_before == raw_originals(raw, base, key, restored), "Destination originals changed"
            assert source_before == snapshot(source), "Original fixture changed"
            receipt["destination_restored_before_timeout"] = True
            dump(work / "failure-evidence.json", receipt)
            print("Controlled destination album removed; original inventory and original bytes restored.", flush=True)

            # Responses are genuine Immich responses with an explicit delayed
            # header fault; no mock transport or fabricated data is involved.
            timeout_adapter = Immich(timeout_observer, key, timeout=.4)
            try:
                manager, job = launch(work, "timeout", source, timeout_adapter)
                report = finish(manager, job)
                assert not report["summary"]["coverage_complete"], "Timeout scan incorrectly claimed complete coverage"
                content = [f for f in report["findings"] if f["kind"] == "content"]
                assert content and all(f["status"] == "inaccessible" for f in content), "Timed-out originals were not inaccessible"
                assert not any(f["status"] == "missing" for f in report["findings"]), "Timeout was promoted to absence"
                assert any("timed out" in f["message"].lower() for f in report["findings"]), "Timeout explanation missing"
                assert read_only(timeout_adapter.requests), "Timeout check attempted a non-read request"
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    observed = json.loads(timeout_ledger.read_text(encoding="utf-8"))
                    faulted = [r for r in observed if r.get("fault_injection")]
                    if faulted and all(r.get("complete") or r.get("connection_interrupted") for r in faulted):
                        break
                    time.sleep(.05)
                assert faulted and all(r["status"] == 200 for r in faulted), "Observer did not receive real successful upstream original headers"
                assert all(r["allowed_read"] for r in observed), "Observer saw a non-read request"
                dump(work / "timeout-report.json", report)
                receipt["checks"]["timeout"] = {"status": "passed", "fault_injection": "One-second delay after actual upstream original headers",
                    "client_timeout_seconds": .4, "upstream_successful_original_responses": len(faulted),
                    "content_inaccessible": len(content), "coverage_complete": False,
                    "checker_requests": timeout_adapter.requests, "observer_write_requests": 0}
            finally:
                timeout_adapter.close()
            final_inventory = baseline_reader.inventory()
            assert fingerprint(baseline) == fingerprint(final_inventory), "Final destination inventory differs"
            assert originals_before == raw_originals(raw, base, key, final_inventory), "Final destination originals differ"
            assert source_before == snapshot(source), "Original fixture changed after timeout test"
            receipt.update(status="passed", original_fixture_unchanged=True,
                           destination_inventory_restored=True, destination_originals_unchanged=True)
            dump(work / "failure-evidence.json", receipt)
            return receipt
        finally:
            baseline_reader.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, default=WORKSPACE / "work/immich-live-extended/state.private.json")
    parser.add_argument("--work-dir", type=Path, default=WORKSPACE / "work/live-failures")
    parser.add_argument("--timeout-observer", default="http://127.0.0.1:22842")
    parser.add_argument("--timeout-ledger", type=Path, default=WORKSPACE / "work/real-immich-timeout-observer.json")
    args = parser.parse_args()
    try:
        result = run(args.state.resolve(), args.work_dir.resolve(), args.timeout_observer, args.timeout_ledger.resolve())
        print(json.dumps({"status": result["status"], "checks": list(result["checks"]),
                          "destination_restored": result["destination_inventory_restored"]}))
        return 0
    except Exception as error:
        # Neither credentials nor remote bodies enter diagnostics.
        message = str(error) if isinstance(error, (AssertionError, RuntimeError)) else type(error).__name__
        print("Controlled failure checks failed: " + message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
