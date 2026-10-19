"""Test-only loopback observer forwarding reads to real disposable Immich.

No credentials or response bodies are recorded. Original responses are forwarded
unchanged; optional rate limiting makes cancellation/interruption reproducible.
This is independent test instrumentation and is never imported by the app.
"""
from __future__ import annotations

import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import sys
import threading
import time
from urllib.parse import urlsplit

import httpx


class LedgerWriteError(RuntimeError):
    """A failed audit persistence operation, never a transport interruption."""


def save_ledger(path: Path, records: list, attempts: int = 8, retry_delay: float = .025):
    """Replace atomically, retrying bounded Windows reader-sharing conflicts."""
    if attempts < 1:
        raise ValueError("Ledger persistence requires at least one attempt.")
    temporary = path.with_suffix(".tmp")
    try:
        temporary.write_text(json.dumps(records, indent=2), encoding="utf-8")
    except OSError as error:
        raise LedgerWriteError("Observer ledger temporary write failed; audit persistence is incomplete.") from error
    for attempt in range(attempts):
        try:
            temporary.replace(path)
            return
        except PermissionError as error:
            if attempt + 1 == attempts:
                raise LedgerWriteError("Observer ledger replacement failed after bounded retries; audit persistence is incomplete.") from error
            time.sleep(retry_delay)
        except OSError as error:
            raise LedgerWriteError("Observer ledger replacement failed; audit persistence is incomplete.") from error


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", default="http://127.0.0.1:22839")
    parser.add_argument("--port", type=int, default=22841)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--bytes-per-second", type=int, default=8 * 1024 * 1024)
    parser.add_argument("--original-header-delay", type=float, default=0, help="Fault injection after receiving real upstream headers")
    args = parser.parse_args()
    upstream = urlsplit(args.upstream)
    if upstream.scheme != "http" or upstream.hostname != "127.0.0.1" or upstream.port != 22839 or upstream.path not in {"", "/"}:
        parser.error("Observer is confined to the harness's disposable loopback server on port 22839.")
    args.ledger.parent.mkdir(parents=True, exist_ok=True)
    records, lock = [], threading.Lock()

    def save():
        try:
            save_ledger(args.ledger, records)
        except LedgerWriteError:
            print("Observer ledger persistence failed; this audit is incomplete.", file=sys.stderr, flush=True)
            raise

    save()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            pass

        def forward(self):
            parsed = urlsplit(self.path)
            path = parsed.path
            allowed = ((self.command == "POST" and path == "/api/search/metadata") or
                       (self.command == "GET" and path in {"/api/server/version", "/api/albums"}) or
                       (self.command == "GET" and re.fullmatch(r"/api/assets/[0-9a-fA-F-]{36}(/original)?", path)))
            record = {"method": self.command, "path": path, "allowed_read": bool(allowed), "status": None,
                      "bytes": 0, "complete": False}
            with lock:
                records.append(record)
                save()
            if not allowed:
                self.send_error(405)
                return
            length = int(self.headers.get("content-length", "0"))
            if length > 2 * 1024 * 1024:
                self.send_error(413)
                return
            body = self.rfile.read(length) if length else None
            headers = {k: v for k, v in self.headers.items() if k.lower() in
                       {"x-api-key", "accept", "accept-encoding", "content-type"}}
            # Query is forwarded but deliberately not recorded. The application
            # uses edited=false; tests verify that contract independently.
            target = args.upstream.rstrip("/") + self.path
            digest = hashlib.sha256()
            started = time.monotonic()
            try:
                with httpx.Client(timeout=35, trust_env=False, follow_redirects=False) as client:
                    with client.stream(self.command, target, headers=headers, content=body) as response:
                        record["status"] = response.status_code
                        if path.endswith("/original") and args.original_header_delay > 0:
                            record["fault_injection"] = "Delayed real upstream original response headers"
                            time.sleep(args.original_header_delay)
                        self.send_response(response.status_code)
                        for name, value in response.headers.items():
                            if name.lower() not in {"connection", "transfer-encoding", "keep-alive", "server", "date"}:
                                self.send_header(name, value)
                        self.send_header("Connection", "close")
                        self.end_headers()
                        for chunk in response.iter_raw(64 * 1024):
                            if path.endswith("/original") and args.bytes_per_second > 0:
                                delay = (record["bytes"] + len(chunk)) / args.bytes_per_second - (time.monotonic() - started)
                                if delay > 0:
                                    time.sleep(delay)
                            self.wfile.write(chunk)
                            self.wfile.flush()
                            digest.update(chunk)
                            record["bytes"] += len(chunk)
                            if record["bytes"] % (1024 * 1024) < len(chunk):
                                with lock:
                                    save()
                        record["complete"] = True
                        record["response_sha256"] = digest.hexdigest()
            except LedgerWriteError:
                record["ledger_write_failed"] = True
                raise
            except (OSError, httpx.HTTPError):
                record["connection_interrupted"] = True
            finally:
                self.close_connection = True
                with lock:
                    save()

        do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = forward

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    server.daemon_threads = True
    print(f"Read observer listening on 127.0.0.1:{args.port}; upstream is the real disposable Immich.", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
