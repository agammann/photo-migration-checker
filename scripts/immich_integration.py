"""Optional real Immich test. Setup writes are confined to a fresh disposable server.

The application itself never imports this setup script. No personal-server URL
or credential is accepted. A working Docker Linux engine is required for --run.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import uuid
import random
import re

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
VERSION = "v3.3.3"
COMMIT = "d2dac658fe1c67e8bbd08aa18200a32e5d45b9e4"
COMPOSE_URL = f"https://raw.githubusercontent.com/immich-app/immich/{COMMIT}/docker/docker-compose.yml"
PORT = 22839


def assert_owned_stack(project: str) -> None:
    """Check the actual container and binding before any setup writes."""
    if not re.fullmatch(r"pmc-test-[a-f0-9]{12}", project):
        raise RuntimeError("Disposable project identity is invalid.")
    fields = '{"labels":{{json .Config.Labels}},"image":{{json .Config.Image}},"ports":{{json .NetworkSettings.Ports}}}'
    result = subprocess.run(["docker", "inspect", "--format", fields, project + "-server-1"], capture_output=True, timeout=15)
    if result.returncode:
        raise RuntimeError("The owned disposable Immich container is unavailable.")
    details = json.loads(result.stdout)
    labels = details.get("labels", {})
    bindings = details.get("ports", {}).get("2283/tcp", []) or []
    if (labels.get("com.docker.compose.project") != project or
        details.get("image") != "ghcr.io/immich-app/immich-server:" + VERSION or
        bindings != [{"HostIp": "127.0.0.1", "HostPort": str(PORT)}]):
        raise RuntimeError("The container or loopback binding does not match the disposable harness ownership contract.")


def dump(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def snapshot(root: Path) -> dict:
    return {p.relative_to(root).as_posix(): {
        "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
        "size": p.stat().st_size, "mtime_ns": p.stat().st_mtime_ns,
    } for p in sorted(root.rglob("*")) if p.is_file()}


def prepare(work: Path) -> tuple[Path, str]:
    from PIL import Image

    # A fresh directory avoids touching files from any previous test run.
    work.mkdir(parents=True, exist_ok=False)
    project = "pmc-test-" + uuid.uuid4().hex[:12]
    dump(work / "owner.json", {"project": project, "version": VERSION, "port": PORT})
    source = work / "takeout" / "Google Photos"
    palette = {"correct.jpg": "teal", "omitted.jpg": "orange",
               "garden.jpg": "green", "garden-edited.jpg": "lime", "shared.jpg": "purple"}
    epoch = "1704110400"
    for name, color in palette.items():
        dest = source / "Photos from 2024" / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        exif = Image.Exif()
        exif[36867] = "2024:01:01 12:00:00"
        exif[36881] = "+00:00"
        Image.new("RGB", (64, 48), color).save(dest, exif=exif)
        dump(dest.with_name(name + ".json"), {
            "title": name, "photoTakenTime": {"timestamp": epoch,
            "formatted": "Jan 1, 2024, 12:00:00 PM UTC"}})
    for album in ("Album One", "Album Two"):
        folder = source / album
        folder.mkdir()
        dump(folder / "metadata.json", {"title": album, "description": ""})
        for suffix in ("", ".json"):
            shutil.copyfile(source / "Photos from 2024" / ("shared.jpg" + suffix), folder / ("shared.jpg" + suffix))
    # Kept as unsupported evidence; this is deliberately not uploaded as media.
    (source / "Photos from 2024" / "motion.aae").write_text("<adjustment/>\n", encoding="utf-8")
    expected = {"missing_paths": ["Photos from 2024/omitted.jpg", "Photos from 2024/garden-edited.jpg"],
                "matched_names": ["correct.jpg", "garden.jpg", "shared.jpg"],
                "missing_album_membership": "Album Two", "duplicate_occurrences": 3,
                "unsupported": "Photos from 2024/motion.aae"}
    dump(work / "expected.json", expected)
    with urllib.request.urlopen(COMPOSE_URL, timeout=30) as response:
        original = response.read(1024 * 1024)
    (work / "docker-compose.official.yml").write_bytes(original)
    # Derived from the pinned official file: isolated named volumes, loopback
    # port, unique project, no container_name and no restart-at-boot behavior.
    compose = f"""services:
  server:
    image: ghcr.io/immich-app/immich-server:{VERSION}
    ports: [\"127.0.0.1:{PORT}:2283\"]
    environment:
      DB_HOSTNAME: database
      DB_USERNAME: postgres
      DB_PASSWORD: ${{DB_PASSWORD}}
      DB_DATABASE_NAME: immich
      REDIS_HOSTNAME: redis
      IMMICH_MACHINE_LEARNING_ENABLED: 'false'
    volumes: [\"media:/data\"]
    depends_on:
      database:
        condition: service_healthy
      redis:
        condition: service_healthy
    restart: 'no'
  redis:
    image: docker.io/valkey/valkey:9@sha256:c123e3715db63d06d4ad6964884037aa0d5d4d703939b9929954112889708e1d
    healthcheck:
      test: ["CMD", "valkey-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 20
    restart: 'no'
  database:
    image: ghcr.io/immich-app/postgres:14-vectorchord0.4.3-pgvectors0.2.0@sha256:bcf63357191b76a916ae5eb93464d65c07511da41e3bf7a8416db519b40b1c23
    environment:
      POSTGRES_PASSWORD: ${{DB_PASSWORD}}
      POSTGRES_USER: postgres
      POSTGRES_DB: immich
      POSTGRES_INITDB_ARGS: '--data-checksums'
    volumes: [\"database:/var/lib/postgresql/data\"]
    shm_size: 128mb
    restart: 'no'
volumes:
  media:
  database:
"""
    (work / "compose.yml").write_text(compose, encoding="utf-8")
    env = work / ".env"
    env.write_text("DB_PASSWORD=" + secrets.token_urlsafe(32) + "\n", encoding="utf-8")
    if os.name != "nt":
        env.chmod(0o600)
    return source, project


def docker(work: Path, project: str, *args, timeout=600) -> None:
    # No shell and no credential on the command line.
    command = ["docker", "compose", "--project-name", project, "--file", str(work / "compose.yml"),
               "--env-file", str(work / ".env"), *args]
    result = subprocess.run(command, capture_output=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError("Docker Compose operation failed; inspect Docker locally (output suppressed).")


def run(work: Path, source: Path, project: str, extra_video: Path | None = None) -> dict:
    result = subprocess.run(["docker", "version", "--format", "{{.Server.Version}}"], capture_output=True, timeout=15)
    if result.returncode:
        raise RuntimeError("Docker Linux engine is unavailable; no real Immich integration ran.")
    (work / "compose-start-attempted").write_text("true\n", encoding="utf-8")
    docker(work, project, "up", "--detach")
    return LiveSuite(work / "extended", work, extra_video).execute()

class LiveSuite:
    """Setup writer and read-only checker execution remain separate clients."""
    def __init__(self, work: Path, existing: Path, extra_video: Path | None = None):
        import httpx
        self.work = work
        self.extra_video = extra_video
        self.work.mkdir(parents=True, exist_ok=True)
        owner = json.loads((existing / "owner.json").read_text(encoding="utf-8"))
        if not owner["project"].startswith("pmc-test-") or owner["version"] != VERSION or owner["port"] != PORT:
            raise RuntimeError("Existing project does not match this disposable harness ownership contract.")
        self.url = f"http://127.0.0.1:{PORT}"
        self.state_path = work / "state.private.json"
        self.state = json.loads(self.state_path.read_text(encoding="utf-8")) if self.state_path.exists() else {
            "url": self.url, "version": "3.3.3", "scenarios": {}, "project": owner["project"]}
        self.setup_requests = []
        self.client = httpx.Client(base_url=self.url + "/api", timeout=120, trust_env=False, follow_redirects=False)
        self.queue_client = None
        self.quiescence_observations = []

    def save(self):
        dump(self.state_path, self.state)
        if os.name != "nt":
            self.state_path.chmod(0o600)

    def setup(self, method: str, path: str, **kwargs):
        response = self.client.request(method, path, **kwargs)
        self.setup_requests.append({"method": method, "path": path, "status": response.status_code})
        if response.status_code >= 400:
            # Never expose the body, credentials or headers in logs or reports.
            (self.work / "setup-error.private.txt").write_text(response.text, encoding="utf-8")
            raise RuntimeError(f"Disposable setup returned HTTP {response.status_code} for {method} {path}.")
        return response.json() if response.content else None

    def wait(self):
        import httpx
        assert_owned_stack(self.state["project"])
        deadline = time.monotonic() + 300
        while time.monotonic() < deadline:
            try:
                response = self.client.get("/server/version")
                if response.status_code == 200:
                    version = response.json()
                    if [version.get(k) for k in ("major", "minor", "patch")] != [3, 3, 3]:
                        raise RuntimeError("Disposable server version differs from pinned v3.3.3.")
                    return
            except httpx.HTTPError:
                pass
            time.sleep(2)
        raise RuntimeError("Disposable Immich did not become healthy within 300 seconds.")

    def account(self, name: str):
        if name not in self.state:
            self.state[name] = {"email": f"{name}-{uuid.uuid4().hex[:10]}@example.invalid", "password": secrets.token_urlsafe(32)}
            self.save()
        account = self.state[name]
        body = {"email": account["email"], "password": account["password"], "name": "Disposable " + name}
        if not account.get("registered"):
            if name == "admin":
                self.setup("POST", "/auth/admin-sign-up", json=body)
            else:
                self.setup("POST", "/admin/users", json={**body, "shouldChangePassword": False, "notify": False})
            account["registered"] = True
            self.save()
        login = self.setup("POST", "/auth/login", json={k: body[k] for k in ("email", "password")})
        self.client.headers["Authorization"] = "Bearer " + login["accessToken"]
        return account

    def login_admin(self):
        self.account("admin")

    def key(self, permissions, name):
        return self.setup("POST", "/api-keys", json={"name": name, "permissions": permissions})["secret"]

    def seed(self, scenario: str):
        from pmc.sample import create_sample, CAPTURE_TIMESTAMP, _iso
        from PIL import Image

        base = self.work / scenario
        description = base / "fixture.private.json"
        if description.exists():
            fixture = json.loads(description.read_text(encoding="utf-8"))
            fixture["source"] = Path(fixture["source"])
            fixture["originals"] = {k: Path(v) for k, v in fixture["originals"].items()}
        else:
            fixture = create_sample(base, scenario)
            # Distinct album identity matters even when member bytes coincide.
            shared = fixture["source"] / "Family" / "sunrise.png"
            shared_old_id = next(a["id"] for a in fixture["assets"] if a["originalFileName"] == "sunrise.png")
            identity_paths = ["Mirror One", "Mirror Two"] if scenario == "correct" else ["Identity One", "Identity Two"]
            for index, directory in enumerate(identity_paths):
                folder = fixture["source"] / directory
                folder.mkdir()
                shutil.copyfile(shared, folder / shared.name)
                shutil.copyfile(shared.with_name(shared.name + ".json"), folder / (shared.name + ".json"))
                title = directory if scenario == "correct" else "Shared Trip"
                dump(folder / "metadata.json", {"title": title, "description": "Album identity fixture"})
                if scenario == "correct" or index == 0:
                    fixture["albums"].append({"id": str(uuid.uuid4()), "albumName": title, "asset_ids": [shared_old_id]})
            fixture["expected"]["identity_paths"] = identity_paths
            empty_name = "Empty Album" if scenario == "correct" else "Empty Missing"
            empty = fixture["source"] / empty_name
            empty.mkdir()
            dump(empty / "metadata.json", {"title": empty_name, "description": "Empty album fixture"})
            fixture["expected"]["empty_album"] = empty_name
            if scenario == "correct":
                fixture["albums"].append({"id": str(uuid.uuid4()), "albumName": empty_name, "asset_ids": []})
            if scenario == "problems":
                # A real valid PNG, large enough to exercise streamed downloads.
                data = random.Random(20261018).randbytes(4096 * 4096 * 3)
                large = fixture["source"] / "large-transfer.png"
                Image.frombytes("RGB", (4096, 4096), data).save(large, compress_level=1)
                dump(large.with_name(large.name + ".json"), {"title": large.name, "photoTakenTime": {"timestamp": str(CAPTURE_TIMESTAMP)}})
                digest = hashlib.sha256(large.read_bytes()).hexdigest()
                ident = str(uuid.uuid4())
                fixture["assets"].append({"id": ident, "originalFileName": large.name,
                    "fileCreatedAt": _iso(CAPTURE_TIMESTAMP), "type": "IMAGE"})
                fixture["originals"][ident] = large
                fixture["expected"]["large_path"] = large.name
                fixture["expected"]["hashes"][large.name] = {"sha256": digest,
                    "sha1": hashlib.sha1(large.read_bytes()).hexdigest(), "size": large.stat().st_size}
            serializable = {**fixture, "source": str(fixture["source"]),
                            "originals": {k: str(v) for k, v in fixture["originals"].items()}}
            dump(description, serializable)
        if scenario == "problems" and self.extra_video and not fixture["expected"].get("mp4_path"):
            target = fixture["source"] / "Videos" / "clip-extra.mp4"
            shutil.copyfile(self.extra_video, target)
            dump(target.with_name(target.name + ".json"), {"title": target.name,
                "photoTakenTime": {"timestamp": str(CAPTURE_TIMESTAMP)}})
            ident = str(uuid.uuid4())
            fixture["assets"].append({"id": ident, "originalFileName": target.name,
                "fileCreatedAt": _iso(CAPTURE_TIMESTAMP), "type": "VIDEO"})
            fixture["originals"][ident] = target
            next(a for a in fixture["albums"] if a["albumName"] == "Videos")["asset_ids"].append(ident)
            fixture["expected"]["mp4_path"] = "Videos/clip-extra.mp4"
            fixture["expected"]["hashes"]["Videos/clip-extra.mp4"] = {
                "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                "sha1": hashlib.sha1(target.read_bytes()).hexdigest(), "size": target.stat().st_size}
            dump(description, {**fixture, "source": str(fixture["source"]),
                "originals": {k: str(v) for k, v in fixture["originals"].items()}})
        self.login_admin()
        account = self.account(scenario)
        current = self.state["scenarios"].setdefault(scenario, {"source": str(fixture["source"]),
            "expected": str(base / "expected-live.json"), "static_expected": str(base / "expected.json"), "ids": {}, "albums": {}})
        self.save()
        for asset in fixture["assets"]:
            old = asset["id"]
            if old in current["ids"]:
                continue
            path = fixture["originals"][old]
            mime = "video/x-msvideo" if path.suffix == ".avi" else "video/mp4" if path.suffix == ".mp4" else "image/png"
            with path.open("rb") as stream:
                uploaded = self.setup("POST", "/assets", files={"assetData": (asset["originalFileName"], stream, mime)},
                    data={"filename": asset["originalFileName"], "fileCreatedAt": asset["fileCreatedAt"], "fileModifiedAt": asset["fileCreatedAt"]})
            current["ids"][old] = uploaded["id"]
            self.save()
        for album in fixture["albums"]:
            live_members = [current["ids"][v] for v in album["asset_ids"]]
            if album["id"] not in current["albums"]:
                created = self.setup("POST", "/albums", json={"albumName": album["albumName"],
                    "assetIds": live_members})
                current["albums"][album["id"]] = created["id"]
                self.save()
            elif live_members != current.setdefault("album_members", {}).get(album["id"]):
                self.setup("PUT", f'/albums/{current["albums"][album["id"]]}/assets', json={"ids": live_members})
            current.setdefault("album_members", {})[album["id"]] = live_members
            self.save()
        if "key" not in current:
            current["key"] = self.key(["asset.read", "album.read", "asset.download"], "Minimum checker permissions")
            current["checksum_key"] = self.key(["asset.read", "album.read"], "Checksum-only checker")
            current["no_albums_key"] = self.key(["asset.read"], "Permission failure fixture")
            self.save()
        return fixture, current

    def queue_snapshot(self):
        """Read server work queues using the separate setup administrator.

        This is test preparation, never a checker key permission requirement.
        Media jobs can update timestamps after EXIF byte size first appears.
        """
        import httpx
        if self.queue_client is None:
            self.queue_client = httpx.Client(base_url=self.url + "/api", timeout=30,
                                            trust_env=False, follow_redirects=False)
            account = self.state["admin"]
            response = self.queue_client.post("/auth/login", json={k: account[k] for k in ("email", "password")})
            self.setup_requests.append({"method": "POST", "path": "/auth/login", "status": response.status_code,
                                        "role": "quiescence-audit"})
            if response.status_code != 201:
                raise RuntimeError("Disposable admin could not authenticate for queue observation.")
            self.queue_client.headers["Authorization"] = "Bearer " + response.json()["accessToken"]
        response = self.queue_client.get("/queues")
        self.setup_requests.append({"method": "GET", "path": "/queues", "status": response.status_code,
                                    "role": "quiescence-audit"})
        if response.status_code != 200:
            raise RuntimeError("Disposable admin could not read server queue status.")
        queues = response.json()
        if not isinstance(queues, list):
            raise RuntimeError("Unexpected disposable server queue status schema.")
        names = {"metadataExtraction", "thumbnailGeneration", "videoConversion", "sidecar", "library",
                 "backgroundTask", "storageTemplateMigration", "migration", "search", "duplicateDetection",
                 "workflow", "editor", "faceDetection", "facialRecognition", "smartSearch", "ocr"}
        status = {q["name"]: {k: q["statistics"].get(k, 0) for k in ("active", "waiting", "delayed", "paused", "failed")}
                  for q in queues if isinstance(q, dict) and q.get("name") in names}
        if not {"metadataExtraction", "thumbnailGeneration", "videoConversion"}.issubset(status):
            raise RuntimeError("Disposable server did not expose required media queues.")
        return status

    def settle(self, adapter):
        from pmc.engine import fingerprint
        previous, stable = None, 0
        started = time.monotonic()
        deadline = started + 180
        observations = []
        while time.monotonic() < deadline:
            queues = self.queue_snapshot()
            idle = not any(v for stats in queues.values() for k, v in stats.items() if k != "failed")
            dest = adapter.inventory()
            if any(issue.get("kind") != "destination_changed" for issue in dest["issues"]):
                raise RuntimeError("Live inventory did not provide complete request coverage.")
            current = fingerprint(dest)
            ready = idle and not dest["issues"] and all((a.get("exifInfo") or {}).get("fileSizeInByte") for a in dest["assets"])
            stable = stable + 1 if current == previous and ready else (1 if ready else 0)
            observations.append({"elapsed_seconds": round(time.monotonic() - started, 3),
                                 "queues_idle": idle, "stable_repetitions": stable,
                                 "inventory_fingerprint": current, "queues": queues})
            if stable >= 5:
                self.quiescence_observations.append(observations)
                dump(self.work / "quiescence-observations.json", self.quiescence_observations)
                return dest
            previous = current
            # Poll the observed queue/inventory conditions, with a bounded deadline.
            time.sleep(1)
        self.quiescence_observations.append(observations)
        dump(self.work / "quiescence-observations.json", self.quiescence_observations)
        raise RuntimeError("Disposable media queues and inventory did not become quiescent within 180 seconds.")

    def manager_scan(self, source, adapter, mode, label):
        from pmc.engine import Manager
        manager = Manager(self.work / "checker-state" / label)
        job = manager.start(manager.source(Path(source)), manager.connection(adapter), mode, mode == "original")
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            saved = manager.store.get(job["id"])
            if saved["status"] != "running":
                if saved["status"] != "completed":
                    raise RuntimeError("Live Manager scan failed: " + saved["status"])
                report = saved["report"]
                dump(self.work / (label + "-report.json"), report)
                return report
            time.sleep(.05)
        manager.cancel(job["id"])
        raise RuntimeError("Live Manager scan exceeded 180 seconds.")

    def assert_fixture(self, fixture, report, mode):
        expected = fixture["expected"]
        findings = report["findings"]
        content = {f["path"]: f for f in findings if f["kind"] == "content"}
        if expected["scenario"] == "correct":
            assert report["summary"]["attention"] == 0, "Clean live fixture has false alarms"
            assert all(f["status"] == mode for f in content.values()), "Clean live original content was not matched"
        else:
            for path in expected["omitted_paths"]:
                assert content[path]["status"] == "missing", "Live omitted original/edit was not detected"
            for path in expected["mismatched_original_paths"]:
                assert content[path]["status"] == ("mismatched" if mode == "original" else "possible"), "Live changed bytes not detected"
            for path in expected["metadata_changed_paths"]:
                assert any(f["kind"] == "metadata" and f["path"] == path and f["status"] == "difference" for f in findings), "Live date change not detected"
            for path in expected["unsupported_paths"]:
                assert content[path]["status"] == "unsupported", "Live unsupported file disappeared"
            for path in expected["paired_paths"]:
                assert any(f["path"] == path and f["status"] == "unresolved" for f in findings), "Live paired component uncertainty missing"
            for path in expected["malformed_sidecars"] + expected["ambiguous_sidecars"]:
                assert any(f["path"] == path and f["status"] == "unresolved" for f in findings), "Live malformed/ambiguous sidecar disappeared"
            for path in expected["uncertain_capture_paths"]:
                assert any(f["kind"] == "metadata" and f["path"] == path and f["status"] == "unresolved" for f in findings), "Live uncertain timezone was guessed"
            assert any(f["path"] == "Weekend" and f["kind"] == "album" and f["status"] in {"difference", "unresolved"} for f in findings), "Live missing album membership not detected"
            assert any(f["path"] in expected["identity_paths"] and f["kind"] == "album" for f in findings), "Live collapsed album identity was not detected"
            assert any(f["path"] == expected["empty_album"] and f["kind"] == "album" for f in findings), "Live missing empty album was not detected"
            assert not report["summary"]["coverage_complete"], "Seeded unresolved cases reported complete"
            if expected.get("mp4_path"):
                assert content[expected["mp4_path"]]["status"] == mode, "Live H264 MP4 did not match original bytes"
        for pair in expected["duplicate_occurrences"]:
            assert content[pair[0]]["asset_ids"] == content[pair[1]]["asset_ids"], "Deduplicated source occurrences lost"
        assert content["Family/collision.png"]["asset_ids"] != content["Weekend/collision.png"]["asset_ids"], "Identical filenames conflated distinct content"
        return {"summary": report["summary"], "findings": [{k: f[k] for k in ("path", "kind", "status")} for f in findings]}

    def check(self, fixture, current, scenario):
        from pmc.immich import Immich, ImmichError
        from pmc.engine import fingerprint
        before_source = snapshot(fixture["source"])
        reader = Immich(self.url, current["key"])
        try:
            before = self.settle(reader)
            dump(self.work / (scenario + "-inventory-before.json"), before)
            before_hashes = {a["id"]: reader.hash_original(a["id"])["sha256"] for a in before["assets"]}
            reports = {}
            for mode in ("checksum", "original"):
                adapter = reader if mode == "original" else Immich(self.url, current["checksum_key"])
                try:
                    report = self.manager_scan(fixture["source"], adapter, mode, scenario + "-" + mode)
                    reports[mode] = self.assert_fixture(fixture, report, mode)
                    assert all(m == "GET" or (m == "POST" and p == "/search/metadata") for m, p in adapter.requests)
                finally:
                    if adapter is not reader:
                        adapter.close()
            after = reader.inventory()
            dump(self.work / (scenario + "-inventory-after.json"), after)
            after_hashes = {a["id"]: reader.hash_original(a["id"])["sha256"] for a in after["assets"]}
            if fingerprint(before) != fingerprint(after):
                old, new = ({a["id"]: a for a in d["assets"]} for d in (before, after))
                changes = {ident: {field: {"before": old[ident].get(field), "after": new[ident].get(field)}
                           for field in old[ident].keys() | new[ident].keys()
                           if old[ident].get(field) != new[ident].get(field)}
                           for ident in old.keys() & new.keys() if old[ident] != new[ident]}
                dump(self.work / (scenario + "-inventory-drift.json"), {"changed_asset_fields": changes,
                     "added_ids": sorted(new.keys() - old.keys()), "removed_ids": sorted(old.keys() - new.keys()),
                     "album_membership_changed": before["albums"] != after["albums"], "queues_after": self.queue_snapshot()})
                raise AssertionError("Destination inventory changed while testing; inspect field-level drift evidence before attributing a cause.")
            assert before_hashes == after_hashes, "Destination original bytes changed while testing"
            assert before_source == snapshot(fixture["source"]), "Source bytes or mtimes changed while testing"
            dump(Path(current["expected"]), {"immich_version": "3.3.3", **reports})
            return {"status": "passed", "source_unchanged": True, "destination_originals_unchanged": True,
                    "destination_inventory_unchanged": True, "destination_assets": len(before["assets"]),
                    "checker_write_requests": 0, "checker_requests": reader.requests,
                    "media_queues_quiescent_before_scan": True,
                    "modes": {m: r["summary"] for m, r in reports.items()}}
        finally:
            reader.close()

    def pagination(self):
        from pmc.sample import _png, _iso, CAPTURE_TIMESTAMP
        from pmc.immich import Immich, ImmichError
        self.login_admin()
        self.account("pagination_user")
        case = self.state.setdefault("pagination", {"source": str(self.work / "pagination-source"), "ids": []})
        source = Path(case["source"])
        source.mkdir(exist_ok=True)
        self.save()
        for i in range(260):
            path = source / f"page-{i:03d}.png"
            if not path.exists():
                path.write_bytes(_png(i % 256, i // 256, 90))
                dump(path.with_name(path.name + ".json"), {"title": path.name, "photoTakenTime": {"timestamp": str(CAPTURE_TIMESTAMP)}})
            if i < len(case["ids"]):
                continue
            with path.open("rb") as media:
                uploaded = self.setup("POST", "/assets", files={"assetData": (path.name, media, "image/png")},
                    data={"filename": path.name, "fileCreatedAt": _iso(CAPTURE_TIMESTAMP), "fileModifiedAt": _iso(CAPTURE_TIMESTAMP)})
            case["ids"].append(uploaded["id"])
            self.save()
        if "key" not in case:
            case["key"] = self.key(["asset.read", "album.read", "asset.download"], "Pagination read only")
            case["checksum_key"] = self.key(["asset.read", "album.read"], "No download permission")
            case["no_albums_key"] = self.key(["asset.read"], "No album permission")
            self.save()
        reader = Immich(self.url, case["key"])
        before_source = snapshot(source)
        try:
            inventory = self.settle(reader)
            assert len(inventory["assets"]) == 260 and len(set(a["id"] for a in inventory["assets"])) == 260
            assert len([r for r in reader.requests if r == ("POST", "/search/metadata")]) >= 2
            report = self.manager_scan(source, reader, "original", "pagination-original")
            assert report["summary"]["matched"] == 260 and report["summary"]["attention"] == 0
            assert before_source == snapshot(source)
            limited = Immich(self.url, case["checksum_key"])
            try:
                try:
                    limited.hash_original(case["ids"][0])
                except ImmichError as error:
                    assert "403" in str(error), "Download permission did not fail with HTTP 403"
                else:
                    raise AssertionError("Original download succeeded without permission")
            finally:
                limited.close()
            denied = Immich(self.url, case["no_albums_key"])
            try:
                incomplete = denied.inventory()
                assert len(incomplete["assets"]) == 260 and any(i["kind"] == "albums_inaccessible" for i in incomplete["issues"])
            finally:
                denied.close()
            return {"status": "passed", "assets": 260, "page_size": 250, "source_unchanged": True,
                    "minimum_read_permissions_passed": True, "download_permission_403": True,
                    "missing_album_permission_incomplete": True, "checker_write_requests": 0,
                    "checker_requests": reader.requests}
        finally:
            reader.close()

    def execute(self):
        self.wait()
        evidence = {"status": "running", "immich_version": "3.3.3", "commit": COMMIT,
                    "test_kind": "Real disposable Immich controlled synthetic media", "scenarios": {}}
        try:
            for scenario in ("correct", "problems"):
                fixture, current = self.seed(scenario)
                evidence["scenarios"][scenario] = self.check(fixture, current, scenario)
                dump(self.work / "live-evidence.json", evidence)
            evidence["pagination"] = self.pagination()
            evidence.update(status="passed", setup_requests=self.setup_requests,
                limitations=["Controlled synthetic media, not a permissioned real Takeout sample", "No atomic server snapshot"])
            dump(self.work / "live-evidence.json", evidence)
            return evidence
        except Exception as error:
            message = str(error) if isinstance(error, (AssertionError, RuntimeError)) else type(error).__name__
            evidence.update(status="failed", reason=message, setup_requests=self.setup_requests)
            dump(self.work / "live-evidence.json", evidence)
            raise
        finally:
            self.client.close()
            if self.queue_client is not None:
                self.queue_client.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="Start and seed a fresh disposable Immich, then test the checker")
    parser.add_argument("--prepare-only", action="store_true", help="Prepare fixtures and Compose without starting containers")
    parser.add_argument("--keep", action="store_true", help="Keep disposable containers after a run for local inspection")
    parser.add_argument("--work-dir", type=Path, default=ROOT / "work" / ("immich-" + uuid.uuid4().hex[:8]))
    parser.add_argument("--suite-existing-work", type=Path, help="Run the extended live suite against a stack owned by a prepared harness folder; never starts or removes that stack")
    parser.add_argument("--extra-video", type=Path, help="Add a supplied controlled H264 MP4 to the live problems fixture")
    args = parser.parse_args()
    if not (args.run or args.prepare_only or args.suite_existing_work):
        parser.error("Choose --prepare-only, --run, or --suite-existing-work")
    work = args.work_dir.resolve()
    project = None
    try:
        if args.suite_existing_work:
            evidence = LiveSuite(work, args.suite_existing_work.resolve(), args.extra_video).execute()
            print(json.dumps({"status": evidence["status"], "evidence": str(work / "live-evidence.json")}))
            return 0
        source, project = prepare(work)
        if args.run:
            evidence = run(work, source, project, args.extra_video)
        else:
            evidence = {"status": "prepared_only", "immich_version": VERSION, "commit": COMMIT,
                        "real_integration_executed": False, "compose_source": COMPOSE_URL}
        dump(work / "integration-evidence.json", evidence)
        print(json.dumps({"status": evidence["status"], "evidence": str(work / "integration-evidence.json")}))
        return 0
    except Exception as error:
        # Exception messages from our code contain no response bodies/credentials.
        message = str(error) if isinstance(error, (RuntimeError, AssertionError)) else type(error).__name__
        if work.is_dir():
            dump(work / "integration-evidence.json", {"status": "blocked_or_failed", "immich_version": VERSION,
                 "real_integration_passed": False, "reason": message})
        print("Integration did not pass: " + message, file=sys.stderr)
        return 1
    finally:
        if args.run and project and not args.keep and (work / "compose-start-attempted").exists():
            try:
                docker(work, project, "down", "--volumes", "--remove-orphans", timeout=60)
            except Exception:
                print("Disposable teardown did not complete. When Docker works, run:", file=sys.stderr)
                print(f'docker compose --project-name {project} --file "{work / "compose.yml"}" --env-file "{work / ".env"}" down --volumes --remove-orphans', file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
