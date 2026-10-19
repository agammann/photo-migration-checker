"""Release archives must not publish private state placed among source files."""
import importlib.util
from pathlib import Path
import tempfile
from unittest.mock import patch
import zipfile


def test_release_includes_docs_and_built_notices_but_excludes_private_state():
    source = Path(__file__).resolve().parents[1] / "scripts/package_release.py"
    spec = importlib.util.spec_from_file_location("release_packager", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory) / "project"
        public = {"README.md", "CHANGELOG.md", "LICENSE", "pyproject.toml", "requirements.lock", "requirements.txt",
                  "pmc/web/index.html", "pmc/web/THIRD-PARTY-NOTICES.txt", "docs/RELEASE.md", "tests/test_example.py"}
        private = {"pmc/connection.private.json", "docs/.env.local", "tests/fixture.private.json",
                   "pmc/scan.sqlite3-wal", "pmc/scan.sqlite-shm", "docs/database.dump",
                   "pmc/client.pem", "pmc/identity.pfx", "pmc/identity.p12", "docs/log.log",
                   "pmc/checkpoint.db", "pmc/checkpoint.db-wal", "pmc/checkpoint.db-shm", "pmc/token.key", ".env", "frontend/node_modules/cache.js"}
        for name in public | private:
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("private-test-value" if name in private else "public", encoding="utf-8")
        archive = Path(directory) / "release.zip"
        with patch.object(module, "ROOT", root):
            module.bundle(archive)
        with zipfile.ZipFile(archive) as contents:
            assert {name.removeprefix("photo-migration-checker/") for name in contents.namelist()} == public
            assert all(b"private-test-value" not in contents.read(name) for name in contents.namelist())
