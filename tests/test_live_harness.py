"""Preparation regression only; live-server results are recorded separately."""
import runpy
from pathlib import Path


def test_quiescence_requires_idle_queues_and_five_stable_inventories(tmp_path, monkeypatch):
    module = runpy.run_path(str(Path(__file__).parents[1] / "scripts" / "immich_integration.py"))
    suite = module["LiveSuite"].__new__(module["LiveSuite"])
    suite.work = tmp_path
    suite.quiescence_observations = []
    busy = {"metadataExtraction": {"active": 1, "waiting": 0, "delayed": 0, "paused": 0, "failed": 0}}
    idle = {"metadataExtraction": {"active": 0, "waiting": 0, "delayed": 0, "paused": 0, "failed": 0}}
    observations = iter([busy, busy, idle, idle, idle, idle, idle])
    suite.queue_snapshot = lambda: next(observations)
    monkeypatch.setattr(module["time"], "sleep", lambda _: None)

    class Reader:
        calls = 0
        def inventory(self):
            self.calls += 1
            return {"assets": [{"id": "fixed", "exifInfo": {"fileSizeInByte": 1}}], "albums": [], "issues": []}

    reader = Reader()
    suite.settle(reader)
    assert reader.calls == 7, "Unchanged EXIF metadata must not bypass pending server work"
    assert suite.quiescence_observations[-1][-1]["stable_repetitions"] == 5
    assert (tmp_path / "quiescence-observations.json").is_file()
