"""The normal launcher owns its endpoint before releasing a session link."""
import os
from pathlib import Path
import queue
import re
import socket
import subprocess
import sys
import threading
import time
from urllib.parse import urlsplit

import httpx


def launch_environment():
    return {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1])}


def test_launcher_link_authorizes_real_loopback_requests(tmp_path):
    process = subprocess.Popen([sys.executable, "-m", "pmc", "--port", "0", "--data-dir", str(tmp_path / "data")],
                               cwd=tmp_path, env=launch_environment(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        lines = queue.Queue()
        threading.Thread(target=lambda: lines.put(process.stdout.readline()), daemon=True).start()
        line = lines.get(timeout=15)
        match = re.fullmatch(r"Photo Migration Checker: (http://127\.0\.0\.1:\d+/#session=[A-Za-z0-9_-]{43})\n", line)
        assert match is not None, "The launcher did not provide its private session link"
        address = urlsplit(match[1])
        with httpx.Client(base_url=f"{address.scheme}://{address.netloc}", timeout=5) as client:
            for _ in range(100):
                try:
                    assert client.get("/api/bootstrap").status_code == 403
                    break
                except httpx.TransportError:
                    time.sleep(0.05)
            else:
                raise AssertionError("The owned loopback endpoint did not become ready")
            client.headers["x-pmc-token"] = address.fragment.removeprefix("session=")
            assert client.get("/api/bootstrap").status_code == 200
            assert client.post("/api/demo", json={"scenario": "correct"}).status_code == 200
    finally:
        process.terminate()
        process.communicate(timeout=10)


def test_occupied_port_exits_without_releasing_any_session_link(tmp_path):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as unrelated:
        if os.name == "nt":
            unrelated.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        unrelated.bind(("127.0.0.1", 0))
        unrelated.listen(1)
        port = unrelated.getsockname()[1]
        result = subprocess.run([sys.executable, "-m", "pmc", "--port", str(port), "--data-dir", str(tmp_path / "data")],
                                cwd=tmp_path, env=launch_environment(), capture_output=True, text=True, timeout=15)
    assert result.returncode == 1
    assert "http://" not in result.stdout + result.stderr
    assert "session=" not in result.stdout + result.stderr
    assert "port is unavailable" in result.stderr
    assert not (tmp_path / "data").exists()
