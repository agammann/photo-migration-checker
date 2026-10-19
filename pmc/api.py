"""Loopback UI endpoints, guarded against cross-origin browser requests."""
from __future__ import annotations

import os
import secrets
import uuid
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field, SecretStr

from .engine import Manager, SampleDestination, public_job
from . import __version__
from .immich import Immich, ImmichError
from .reports import export_html, export_json


class SourceRequest(BaseModel):
    path: str = Field(min_length=1, max_length=32768)


class ConnectionRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2048)
    api_key: SecretStr


class ScanRequest(BaseModel):
    source_id: str
    connection_id: str
    mode: str = "checksum"
    download_consent: bool = False


class ResumeRequest(BaseModel):
    connection_id: str


class DemoRequest(BaseModel):
    scenario: str = "problems"


def source_preview(root: Path):
    if not root.is_dir() or root.is_symlink() or getattr(root, "is_junction", lambda: False)():
        raise ValueError("Choose a real extracted folder, not a symlink or junction.")
    count, size, skipped = 0, 0, 0
    for directory, dirs, files in os.walk(root, followlinks=False):
        safe = []
        for name in dirs:
            child = Path(directory) / name
            if child.is_symlink() or getattr(child, "is_junction", lambda: False)():
                skipped += 1
            else:
                safe.append(name)
        dirs[:] = safe
        for name in files:
            child = Path(directory) / name
            if child.is_symlink():
                skipped += 1
                continue
            if child.suffix.lower() != ".json":
                count += 1
                size += child.stat().st_size
    return {"root_name": root.name, "files": count, "total_bytes": size, "skipped_links": skipped}


def destination_preview(dest):
    sizes = [(a.get("exifInfo") or {}).get("fileSizeInByte") for a in dest["assets"]]
    return {"version": dest["version"], "asset_count": len(dest["assets"]),
            "known_bytes": sum(s for s in sizes if isinstance(s, (int, float)) and s >= 0),
            "unknown_sizes": sum(not isinstance(s, (int, float)) or s < 0 for s in sizes),
            "issues": dest.get("issues", []), "album_count": len(dest["albums"])}


def create_app(data_dir: Path | None = None):
    data_dir = data_dir or Path(os.environ.get("PMC_DATA_DIR", ".pmc"))
    manager = Manager(data_dir)
    token = secrets.token_urlsafe(32)
    app = FastAPI(title="Photo Migration Checker", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.manager = manager
    app.state.token = token

    @app.middleware("http")
    async def local_guard(request: Request, call_next):
        try:
            host = urlsplit("http://" + request.headers.get("host", "")).hostname
        except ValueError:
            host = None
        if host not in {"127.0.0.1", "localhost", "::1"}:
            return JSONResponse({"detail": "Local host required."}, 403)
        origin = request.headers.get("origin")
        expected_origin = str(request.base_url).rstrip("/")
        if (origin and origin != expected_origin) or request.headers.get("sec-fetch-site") == "cross-site":
            return JSONResponse({"detail": "Cross-origin browser request blocked."}, 403)
        if request.url.path.startswith("/api/") and request.url.path != "/api/bootstrap":
            supplied = request.headers.get("x-pmc-token", "")
            if not secrets.compare_digest(supplied, token):
                return JSONResponse({"detail": "Local session token required. Reload the app."}, 403)
        response = await call_next(request)
        response.headers.update({"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
                                 "Referrer-Policy": "no-referrer", "X-Frame-Options": "DENY",
                                 "Content-Security-Policy": "default-src 'self'; connect-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"})
        return response

    # Suppress validation input echoes: a malformed connection must not echo the key.
    from fastapi.exceptions import RequestValidationError

    @app.exception_handler(RequestValidationError)
    async def invalid(request, error):
        return JSONResponse({"detail": "Invalid request fields. Check the form and try again."}, 422)

    def job(ident):
        try:
            return manager.store.get(ident)
        except KeyError:
            raise HTTPException(404, "Scan not found.") from None

    @app.get("/api/bootstrap")
    def bootstrap():
        return {"token": token, "title": "Photo Migration Checker", "version": __version__}

    @app.post("/api/source")
    def source(body: SourceRequest):
        try:
            root = Path(body.path).expanduser()
            preview = source_preview(root)
            return {"source_id": manager.source(root), **preview}
        except (OSError, ValueError):
            raise HTTPException(400, "Folder is unavailable. Choose a locally extracted Takeout folder with read access.") from None

    @app.post("/api/folder")
    def folder():
        try:
            import tkinter
            from tkinter.filedialog import askdirectory
            window = tkinter.Tk()
            window.withdraw()
            window.attributes("-topmost", True)
            try:
                selected = askdirectory(parent=window, title="Choose extracted Google Takeout folder", mustexist=True)
            finally:
                window.destroy()
            return {"path": selected}
        except Exception:
            raise HTTPException(400, "Native folder picker unavailable. Enter the folder path instead.") from None

    @app.post("/api/connect")
    def connect(body: ConnectionRequest):
        adapter = None
        try:
            adapter = Immich(body.url, body.api_key.get_secret_value())
            inventory = adapter.inventory()
            return {"connection_id": manager.connection(adapter), **destination_preview(inventory)}
        except (ValueError, ImmichError) as e:
            if adapter:
                adapter.close()
            raise HTTPException(400, str(e)) from None

    @app.post("/api/demo")
    def demo(body: DemoRequest):
        if body.scenario not in {"correct", "problems"}:
            raise HTTPException(400, "Choose a documented sample scenario.")
        from .sample import create_sample
        fixture = create_sample(data_dir / "samples" / str(uuid.uuid4()), body.scenario)
        fixture["scenario"] = body.scenario
        adapter = SampleDestination(fixture)
        return {"source_id": manager.source(fixture["source"]), "connection_id": manager.connection(adapter),
                "source": source_preview(fixture["source"]), "destination": destination_preview(adapter.inventory()), "demo": True}

    @app.post("/api/scans")
    def start(body: ScanRequest):
        try:
            return manager.start(**body.model_dump())
        except KeyError:
            raise HTTPException(400, "Select a source and reconnect to the destination first.") from None
        except ValueError as e:
            raise HTTPException(409, str(e)) from None

    @app.get("/api/scans")
    def scans():
        return [public_job(s) for s in manager.store.list()]

    @app.get("/api/scans/{ident}")
    def status(ident: str):
        return public_job(job(ident))

    @app.post("/api/scans/{ident}/cancel")
    def cancel(ident: str):
        job(ident)
        return manager.cancel(ident)

    @app.post("/api/scans/{ident}/resume")
    def resume(ident: str, body: ResumeRequest):
        job(ident)
        try:
            return manager.resume(ident, body.connection_id)
        except KeyError:
            raise HTTPException(400, "Reconnect to the same destination first. Keys are not persisted.") from None
        except ValueError as e:
            raise HTTPException(409, str(e)) from None

    @app.get("/api/scans/{ident}/export")
    def export(ident: str, format: str = "json"):
        report = job(ident).get("report")
        if not report:
            raise HTTPException(409, "This scan has no finished report.")
        if format not in {"html", "json"}:
            raise HTTPException(400, "Choose HTML or JSON.")
        content = export_html(report) if format == "html" else export_json(report)
        return Response(content, media_type="text/html" if format == "html" else "application/json",
                        headers={"Content-Disposition": f'attachment; filename="migration-report.{format}"'})

    web = Path(__file__).parent / "web"

    @app.get("/{path:path}")
    def frontend(path: str):
        if path.startswith("api/"):
            raise HTTPException(404, "Endpoint not found.")
        target = (web / (path or "index.html")).resolve()
        if not target.is_relative_to(web.resolve()) or not target.is_file():
            if path:
                raise HTTPException(404)
            return Response("Frontend is not built. Run the documented frontend build first.", status_code=503)
        return FileResponse(target)

    return app
