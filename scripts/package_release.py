"""Bundle source and the built local interface, without private runtime state."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED = {".git", ".venv", "node_modules", "__pycache__", ".pytest_cache", ".pmc", "dist", "build", "test-results"}
ALLOWED_ROOTS = {".github", "docs", "frontend", "pmc", "scripts", "tests"}
ALLOWED_FILES = {".gitignore", "LICENSE", "README.md", "CHANGELOG.md", "pyproject.toml", "requirements.lock"}


def private_or_runtime(relative: Path) -> bool:
    """Reject private state even if it was accidentally placed in a source folder."""
    name = relative.name.casefold()
    return (name == ".env" or name.startswith(".env.") or ".private." in name
            or ".sqlite" in name or name.endswith((".db-wal", ".db-shm"))
            or relative.suffix.casefold() in {".pyc", ".key", ".pem", ".p12", ".pfx", ".dump", ".db", ".log"})


def bundle(destination: Path):
    if not (ROOT / "pmc/web/index.html").is_file():
        raise SystemExit("Build the frontend before packaging.")
    if destination.resolve().is_relative_to(ROOT.resolve()):
        raise SystemExit("Write release archives outside the project folder.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    included = []
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        for file in sorted(ROOT.rglob("*")):
            relative = file.relative_to(ROOT)
            if (not file.is_file() or file.is_symlink() or any(p in EXCLUDED or p.endswith(".egg-info") for p in relative.parts)
                or private_or_runtime(relative)
                or not (relative.parts[0] in ALLOWED_ROOTS or str(relative) in ALLOWED_FILES)):
                continue
            archive.write(file, "photo-migration-checker/" + relative.as_posix())
            included.append(relative.as_posix())
    digest = hashlib.sha256(destination.read_bytes()).hexdigest()
    destination.with_suffix(destination.suffix + ".sha256").write_text(f"{digest}  {destination.name}\n", encoding="utf-8")
    print(f"Packaged {len(included)} files: {destination.name}\nSHA-256 {digest}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("destination", type=Path)
    bundle(parser.parse_args().destination.resolve())
