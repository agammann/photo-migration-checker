"""Atomic audit persistence regressions using ordinary temporary JSON files."""
import json
from pathlib import Path
import runpy

import pytest


def observer():
    return runpy.run_path(str(Path(__file__).parents[1] / "scripts" / "observe_immich.py"))


def test_ledger_retries_reader_sharing_conflicts_then_replaces_valid_json(tmp_path, monkeypatch):
    module = observer()
    path = tmp_path / "ledger.json"
    path.write_text('[{"old": true}]', encoding="utf-8")
    actual_replace = Path.replace
    calls, sleeps = [], []
    def replace(temporary, target):
        calls.append(target)
        if len(calls) <= 2:
            raise PermissionError("Simulated Windows reader sharing conflict")
        return actual_replace(temporary, target)
    monkeypatch.setattr(Path, "replace", replace)
    monkeypatch.setattr(module["time"], "sleep", sleeps.append)
    records = [{"method": "GET", "status": 200, "complete": True}]
    module["save_ledger"](path, records)
    assert len(calls) == 3 and len(sleeps) == 2
    assert json.loads(path.read_text(encoding="utf-8")) == records
    assert not path.with_suffix(".tmp").exists()


def test_ledger_retry_limit_propagates_audit_failure_and_preserves_old_json(tmp_path, monkeypatch):
    module = observer()
    path = tmp_path / "ledger.json"
    path.write_text('[{"old": true}]', encoding="utf-8")
    calls, sleeps = [], []
    def replace(temporary, target):
        calls.append(target)
        raise PermissionError("Simulated persistent Windows sharing conflict")
    monkeypatch.setattr(Path, "replace", replace)
    monkeypatch.setattr(module["time"], "sleep", sleeps.append)
    with pytest.raises(module["LedgerWriteError"], match="audit persistence is incomplete") as error:
        module["save_ledger"](path, [{"new": True}], attempts=3)
    assert isinstance(error.value.__cause__, PermissionError)
    assert not isinstance(error.value, OSError), "Audit failure must not be swallowed as a transport interruption"
    assert len(calls) == 3 and len(sleeps) == 2
    assert json.loads(path.read_text(encoding="utf-8")) == [{"old": True}]
