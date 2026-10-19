"""Regression cases discovered while reviewing disposable live-server coverage."""
from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from pmc.compare import compare
from pmc.engine import SampleDestination
from pmc.sample import create_sample
from pmc.source import scan_source


class AlbumIdentityRegressions(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="pmc-live-review-")
        self.addCleanup(temporary.cleanup)
        sample = create_sample(Path(temporary.name) / "fixture", "correct")
        adapter = SampleDestination(sample)
        manifest = scan_source(sample["source"])
        inventory = adapter.inventory()
        selected = manifest["items"][0]
        originals = {a["id"]: adapter.hash_original(a["id"]) for a in inventory["assets"]}
        ident = next(i for i, proof in originals.items() if proof["sha256"] == selected["sha256"])
        self.manifest = {**manifest, "items": [], "total_bytes": selected["size"] * 2,
                         "album_titles": {"Album One": "Album One", "Album Two": "Album Two"}}
        for album in ("Album One", "Album Two"):
            occurrence = copy.deepcopy(selected)
            occurrence.update(path=album + "/shared.jpg", albums=[album])
            self.manifest["items"].append(occurrence)
        self.destination = {**inventory, "assets": [a for a in inventory["assets"] if a["id"] == ident],
                            "albums": [
                                {"id": "11111111-1111-1111-1111-111111111111", "albumName": "Album One", "asset_ids": [ident]},
                                {"id": "22222222-2222-2222-2222-222222222222", "albumName": "Album Two", "asset_ids": [ident]},
                            ]}
        self.verified = {ident: originals[ident]}

    def test_unique_titles_disambiguate_correct_albums_with_identical_membership(self):
        report = compare(self.manifest, self.destination, "original", self.verified)
        self.assertEqual(report["summary"]["attention"], 0,
                         "Distinct matching album titles should disambiguate equal content memberships")
        self.assertTrue(report["summary"]["coverage_complete"])
        self.assertEqual(report["summary"]["matched"], 2)

    def test_one_destination_album_cannot_satisfy_two_same_title_source_albums(self):
        self.manifest["album_titles"] = {"Album One": "Trip", "Album Two": "Trip"}
        self.destination["albums"] = self.destination["albums"][:1]
        self.destination["albums"][0]["albumName"] = "Trip"
        report = compare(self.manifest, self.destination, "original", self.verified)
        self.assertTrue(any(f["kind"] == "album" for f in report["findings"]),
                        "Two source album identities require two destination album identities")
        self.assertGreater(report["summary"]["attention"], 0)

    def empty_album_report(self, destination_albums):
        with tempfile.TemporaryDirectory(prefix="pmc-empty-album-") as directory:
            root = Path(directory)
            album = root / "Empty Album"
            album.mkdir()
            (album / "metadata.json").write_text(
                '{"title":"Empty Album","description":"Recognizable album metadata"}',
                encoding="utf-8",
            )
            manifest = scan_source(root)
        destination = {"assets": [], "albums": destination_albums,
                       "issues": [], "version": "3.3.3"}
        return compare(manifest, destination, "original")

    def test_recognized_missing_empty_album_is_reported(self):
        report = self.empty_album_report([])
        self.assertEqual(report["summary"]["source_albums"], 1)
        self.assertEqual(report["summary"]["attention"], 1)
        self.assertTrue(any(f["kind"] == "album" and f["path"] == "Empty Album"
                            for f in report["findings"]))

    def test_recognized_correct_empty_album_has_no_false_alarm(self):
        report = self.empty_album_report([
            {"id": "33333333-3333-3333-3333-333333333333",
             "albumName": "Empty Album", "asset_ids": []}
        ])
        self.assertEqual(report["summary"]["source_albums"], 1)
        self.assertEqual(report["summary"]["attention"], 0)
        self.assertTrue(report["summary"]["coverage_complete"])


if __name__ == "__main__":
    unittest.main()
