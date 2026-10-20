import json
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pmc.api import create_app
from pmc.engine import SampleDestination
from pmc.reports import export_html


@pytest.fixture
def app_client(tmp_path):
    app = create_app(tmp_path / "data")
    with TestClient(app, base_url="http://127.0.0.1") as client:
        client.headers["x-pmc-token"] = app.state.token
        token = client.get("/api/bootstrap").json()["token"]
        client.headers["x-pmc-token"] = token
        yield app, client


def finish(client, ident):
    for _ in range(500):
        job = client.get(f"/api/scans/{ident}").json()
        if job["status"] != "running":
            assert job["status"] == "completed", job
            return job
        time.sleep(0.01)
    pytest.fail("Worker did not finish")


@pytest.mark.parametrize("scenario", ["correct", "problems"])
def test_sample_entire_http_flow_and_reports(app_client, scenario):
    app, client = app_client
    demo = client.post("/api/demo", json={"scenario": scenario}).json()
    job = client.post("/api/scans", json={"source_id": demo["source_id"], "connection_id": demo["connection_id"],
                                         "mode": "original", "download_consent": True}).json()
    job = finish(client, job["id"])
    assert job["demo"] is True
    assert job["report"]["summary"]["attention"] == 0 if scenario == "correct" else job["report"]["summary"]["attention"] > 0
    assert "source_path" not in job and "destination_url" not in job
    exported = client.get(f'/api/scans/{job["id"]}/export?format=json')
    report = exported.json()
    html = client.get(f'/api/scans/{job["id"]}/export?format=html').text
    assert report["demo"] is True
    assert "not a real Immich validation" in html
    assert "Content-Security-Policy" in html
    assert str(app.state.manager.data_dir) not in html
    assert "attachment" in exported.headers["content-disposition"]
    assert client.get(f'/api/scans/{job["id"]}/export?format=csv').status_code == 400
    assert client.get("/api/scans").json()[0]["id"] == job["id"]
    with app.state.manager.store.connect() as db:
        assert db.execute("SELECT count(*) FROM manifests").fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM originals").fetchone()[0] > 0


def test_browser_guards(app_client):
    app, client = app_client
    assert client.get("/api/scans", headers={"x-pmc-token": "bad"}).status_code == 403
    assert client.get("/api/bootstrap", headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.get("/api/bootstrap", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert client.get("/api/bootstrap", headers={"Host": "attacker.example"}).status_code == 403
    assert client.post("/api/source", json={"path": "."}, headers={"Origin": "null"}).status_code == 403
    r = client.get("/api/bootstrap")
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["cache-control"] == "no-store"


def test_local_http_client_cannot_obtain_or_reuse_another_launch_capability(tmp_path):
    first = create_app(tmp_path / "data")
    with TestClient(first, base_url="http://127.0.0.1") as owner, TestClient(first, base_url="http://127.0.0.1") as unrelated:
        owner.headers["x-pmc-token"] = first.state.token
        demo = owner.post("/api/demo", json={"scenario": "correct"}).json()
        started = owner.post("/api/scans", json={"source_id": demo["source_id"], "connection_id": demo["connection_id"]}).json()
        finish(owner, started["id"])
        for headers in ({}, {"x-pmc-token": "bad"}, {"x-pmc-token": "x" * 43}, {"x-pmc-token": "\u00e9".encode("utf-8")}):
            assert unrelated.get("/api/bootstrap", headers=headers).status_code == 403
            assert unrelated.get("/api/scans", headers=headers).status_code == 403
            assert unrelated.get(f'/api/scans/{started["id"]}/export', headers=headers).status_code == 403
            assert unrelated.post("/api/demo", json={"scenario": "correct"}, headers=headers).status_code == 403
        assert first.state.token not in unrelated.get("/").text
    restarted = create_app(tmp_path / "data")
    with TestClient(restarted, base_url="http://127.0.0.1") as client:
        assert client.get("/api/bootstrap", headers={"x-pmc-token": first.state.token}).status_code == 403
        client.headers["x-pmc-token"] = restarted.state.token
        assert client.get("/api/bootstrap").status_code == 200
        assert len(client.get("/api/scans").json()) == 1


def test_checkpoint_directory_cannot_be_inside_selected_source(app_client):
    app, client = app_client
    assert client.post("/api/source", json={"path": str(app.state.manager.data_dir)}).status_code == 400
    assert client.post("/api/source", json={"path": str(app.state.manager.data_dir.parent)}).status_code == 400


def test_consent_validation_errors_do_not_echo_keys(app_client):
    _, client = app_client
    demo = client.post("/api/demo", json={"scenario": "correct"}).json()
    assert client.post("/api/scans", json={"source_id": demo["source_id"], "connection_id": demo["connection_id"],
                                         "mode": "original"}).status_code == 409
    secret = "private-test-key-do-not-echo"
    r = client.post("/api/connect", json={"url": [], "api_key": secret})
    assert r.status_code == 422 and secret not in r.text
    assert client.post("/api/connect", json={"url": "https://user:pass@example.com", "api_key": secret}).status_code == 400
    assert secret not in client.get("/api/scans").text


def test_html_escapes_untrusted_paths_and_report_content(app_client):
    _, client = app_client
    demo = client.post("/api/demo", json={"scenario": "correct"}).json()
    job = client.post("/api/scans", json={"source_id": demo["source_id"], "connection_id": demo["connection_id"]}).json()
    report = finish(client, job["id"])["report"]
    report["findings"][0]["path"] = '<script>alert("bad")</script>'
    report["findings"][0]["message"] = '<img src="https://example.com/track">'
    document = export_html(report).decode()
    assert '<script>' not in document and '<img src=' not in document
    assert '&lt;script&gt;' in document and '&lt;img' in document


def test_cancel_resume_routes_real_worker(app_client):
    app, client = app_client
    demo = client.post("/api/demo", json={"scenario": "correct"}).json()
    adapter = app.state.manager.connections[demo["connection_id"]]
    entered = threading.Event()
    original = adapter.hash_original

    def blocked(ident, cancel):
        entered.set()
        cancel.wait(5)
        return original(ident, cancel)

    adapter.hash_original = blocked
    job = client.post("/api/scans", json={"source_id": demo["source_id"], "connection_id": demo["connection_id"],
                                         "mode": "original", "download_consent": True}).json()
    assert entered.wait(5)
    assert client.post(f'/api/scans/{job["id"]}/cancel').status_code == 200
    for _ in range(500):
        stopped = client.get(f'/api/scans/{job["id"]}').json()
        if stopped["status"] == "cancelled":
            break
        time.sleep(0.01)
    assert stopped["status"] == "cancelled"
    adapter.hash_original = original
    assert client.post(f'/api/scans/{job["id"]}/resume', json={"connection_id": demo["connection_id"]}).status_code == 200
    assert finish(client, job["id"])["report"]["summary"]["matched"] == 8
