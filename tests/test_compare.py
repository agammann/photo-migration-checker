"""Evidence rules: filenames/counts cannot establish identical original bytes."""
from __future__ import annotations

import copy
import hashlib
import tempfile
import unittest
from pathlib import Path

from pmc.compare import compare
from pmc.engine import SampleDestination
from pmc.sample import create_sample
from pmc.source import scan_source


class CompareTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="pmc-compare-test-")
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)

    def fixture(self, scenario="correct"):
        sample = create_sample(self.base / scenario, scenario)
        adapter = SampleDestination(sample)
        source = scan_source(sample["source"])
        destination = copy.deepcopy(adapter.inventory())
        verified = {asset["id"]: adapter.hash_original(asset["id"]) for asset in destination["assets"]}
        return sample, source, destination, verified

    def test_correct_fixture_both_modes_zero_false_alarms(self):
        _, source, destination, verified = self.fixture()
        for mode in ("original", "checksum"):
            with self.subTest(mode=mode):
                report = compare(source, destination, mode, verified)
                self.assertTrue(report["summary"]["coverage_complete"])
                self.assertEqual(report["summary"]["attention"], 0)
                self.assertEqual(report["summary"]["matched"], 8)
                self.assertEqual(report["summary"]["destination_assets"], 7)
                self.assertEqual(report["summary"]["source_albums"], 3)
                self.assertEqual(report["summary"]["content_counts"], {mode: 8})
                self.assertTrue(all(finding["status"] == mode for finding in report["findings"]))
                self.assertEqual(report["coverage"]["capture_dates"], {"comparable": 8, "total": 8,
                    "asserted": 8, "agreements": 8, "differences": 0, "unresolved": 0, "container_only": 0})
                self.assertEqual(report["coverage"]["album_membership"]["asserted_occurrences"], 8)

    def test_seeded_original_byte_omissions_edits_dates_and_unknowns_detected(self):
        sample, source, destination, verified = self.fixture("problems")
        report = compare(source, destination, "original", verified)
        content = {finding["path"]: finding for finding in report["findings"] if finding["kind"] == "content"}
        for path in sample["expected"]["omitted_paths"]:
            self.assertEqual(content[path]["status"], "missing")
        self.assertEqual(content["Family/tampered.png"]["status"], "mismatched")
        self.assertTrue(content["Family/tampered.png"]["destination_sha256"])
        for path in sample["expected"]["unsupported_paths"]:
            self.assertEqual(content[path]["status"], "unsupported")
        self.assertTrue(any(f["kind"] == "metadata" and f["status"] == "difference" and f["path"] == "Weekend/dated.png" for f in report["findings"]))
        self.assertTrue(any(f["status"] == "unresolved" and f["path"] == "Weekend/clock.png" for f in report["findings"]))
        self.assertFalse(report["summary"]["coverage_complete"])
        self.assertTrue(all("safe" not in f.get("message", "").lower() for f in report["findings"]))

    def test_duplicate_album_names_without_full_membership_stay_unresolved(self):
        _, source, destination, verified = self.fixture("problems")
        report = compare(source, destination, "original", verified)
        album = next(f for f in report["findings"] if f["kind"] == "album" and f["path"] == "Weekend")
        self.assertEqual(album["status"], "unresolved")
        self.assertIn("Duplicate", album["message"])
        self.assertEqual(len(album["album_ids"]), 2)

    def test_membership_difference_uses_matched_assets_not_count_or_title(self):
        _, source, destination, verified = self.fixture()
        # A unique name makes the missing membership count independently visible.
        source["album_titles"]["Weekend"] = "Weekend"
        weekend = destination["albums"][1]
        weekend["albumName"] = "Weekend"
        sunrise = next(f for f in source["items"] if f["path"] == "Weekend/sunrise.png")
        sunrise_id = next(ident for ident, proof in verified.items() if proof["sha256"] == sunrise["sha256"])
        weekend["asset_ids"].remove(sunrise_id)
        report = compare(source, destination, "original", verified)
        finding = next(f for f in report["findings"] if f["kind"] == "album" and f["path"] == "Weekend")
        self.assertEqual(finding["status"], "difference")
        self.assertIn("1 matched source content group(s) absent", finding["message"])

    def test_same_filename_and_size_without_hash_match_is_only_possible(self):
        _, source, destination, _ = self.fixture()
        selected = source["items"][0]
        source["items"] = [selected]
        selected["albums"] = []
        asset = destination["assets"][0]
        destination["assets"] = [asset]
        destination["albums"] = []
        asset["originalFileName"] = Path(selected["path"]).name
        asset["exifInfo"]["fileSizeInByte"] = selected["size"]
        import base64
        asset["checksum"] = base64.b64encode(hashlib.sha1(b"different bytes").digest()).decode("ascii")
        report = compare(source, destination, "checksum")
        finding = next(f for f in report["findings"] if f["kind"] == "content")
        self.assertEqual(finding["status"], "possible")
        self.assertEqual(report["summary"]["matched"], 0)
        self.assertFalse(report["summary"]["coverage_complete"])

    def test_external_library_and_unknown_checksum_provenance_are_incomplete(self):
        _, source, destination, _ = self.fixture()
        for provenance in ("external", "absent", "unknown-checksum", "different-version"):
            with self.subTest(provenance=provenance):
                changed = copy.deepcopy(destination)
                asset = changed["assets"][0]
                if provenance == "external":
                    asset["libraryId"] = "external-library"
                elif provenance == "absent":
                    asset.pop("libraryId", None)
                elif provenance == "unknown-checksum":
                    asset["checksum"] = "not-documented-sha1"
                else:
                    changed["version"] = "3.4.0"
                report = compare(source, changed, "checksum")
                self.assertFalse(report["summary"]["coverage_complete"])
                self.assertTrue(any(f["kind"] == "destination" and asset["id"] in f["asset_ids"] for f in report["findings"]))
                self.assertFalse(any(f["status"] == "missing" for f in report["findings"]))

    def test_destination_permission_failure_never_promotes_absence_to_missing(self):
        _, source, destination, _ = self.fixture()
        destination["assets"] = []
        destination["albums"] = []
        destination["issues"] = [{"kind": "destination_inaccessible", "message": "HTTP 403 on page 2"}]
        for mode in ("original", "checksum"):
            report = compare(source, destination, mode)
            content = [f for f in report["findings"] if f["kind"] == "content"]
            self.assertTrue(all(f["status"] == "inaccessible" for f in content))
            self.assertFalse(report["summary"]["coverage_complete"])

    def test_failed_original_download_never_promotes_absence_to_missing(self):
        _, source, destination, verified = self.fixture()
        ident = destination["assets"][0]["id"]
        verified[ident] = {"error": "Original inaccessible (HTTP 403)."}
        report = compare(source, destination, "original", verified)
        self.assertFalse(any(f["status"] == "missing" for f in report["findings"]))
        self.assertTrue(any(f["kind"] == "content" and f["status"] == "inaccessible" for f in report["findings"]))
        self.assertFalse(report["summary"]["coverage_complete"])

    def test_checksum_match_is_never_labeled_independent_original_proof(self):
        _, source, destination, _ = self.fixture("problems")
        report = compare(source, destination, "checksum")
        tampered = next(f for f in report["findings"] if f["kind"] == "content" and f["path"] == "Family/tampered.png")
        self.assertEqual(tampered["status"], "checksum")
        self.assertEqual(tampered["evidence"], "Server-reported checksum match")
        self.assertEqual(tampered["destination_sha256"], {})
        self.assertIn("were not downloaded", tampered["message"])

    def test_unreadable_source_never_becomes_missing(self):
        _, source, destination, verified = self.fixture()
        source["items"][0]["sha256"] = None
        source["items"][0]["sha1"] = None
        report = compare(source, destination, "original", verified)
        self.assertEqual(report["findings"][0]["status"], "inaccessible")
        self.assertFalse(report["summary"]["coverage_complete"])

    def test_absent_sidecar_date_cannot_claim_metadata_coverage(self):
        _, source, destination, verified = self.fixture()
        source["items"][0]["capture"] = None
        source["items"][0]["sidecars"] = []
        report = compare(source, destination, "original", verified)
        self.assertEqual(report["coverage"]["capture_dates"], {"comparable": 7, "total": 8,
            "asserted": 7, "agreements": 7, "differences": 0, "unresolved": 1, "container_only": 0})
        self.assertFalse(report["summary"]["coverage_complete"])
        self.assertTrue(any(f["kind"] == "metadata" and f["status"] == "unresolved" and f["path"] == source["items"][0]["path"] for f in report["findings"]))

    def test_offline_original_prevents_complete_checksum_coverage(self):
        _, source, destination, _ = self.fixture()
        destination["assets"][0]["isOffline"] = True
        report = compare(source, destination, "checksum")
        self.assertFalse(report["summary"]["coverage_complete"])
        self.assertTrue(any(f["kind"] == "destination" and f["status"] == "inaccessible" and "offline" in f["message"]
                            for f in report["findings"]))

    def test_unasserted_directory_membership_reports_limited_album_scope(self):
        _, source, destination, verified = self.fixture()
        source["items"][0]["albums"] = []
        report = compare(source, destination, "original", verified)
        membership = report["coverage"]["album_membership"]
        self.assertEqual(membership["asserted_occurrences"], 7)
        self.assertEqual(membership["total"], 8)
        self.assertTrue(membership["policy"])


if __name__ == "__main__":
    unittest.main()
