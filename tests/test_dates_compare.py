"""A lower-priority nominal date must never become a camera-capture assertion."""
import copy
import unittest

from pmc.dates_compare import date_findings


class DateComparisonTests(unittest.TestCase):
    def fixture(self):
        item = {"path": "clip.jpg", "capture": None, "sidecars": [], "issues": [], "media": {
            "valid": True, "complete": True, "family": "video", "container": "mp4",
            "container_creation": {"valid": True, "complete": True, "source": "iso_bmff.creation_time",
                "timestamp": 1577836800, "datetime_utc": "2020-01-01T00:00:00Z",
                "fields": [{"field": "moov/mvhd.creation_time", "timestamp": 1577836800}]}}}
        return {"items": [item]}, {"clip.jpg": ["asset"]}, {"asset": {"fileCreatedAt": "2020-01-01T00:00:00Z"}}

    def test_nominal_agreement_does_not_inflate_capture_coverage(self):
        for mode in ("original", "checksum"):
            findings, capture, container = date_findings(*self.fixture(), mode)
            self.assertEqual(capture, {"comparable": 0, "total": 1, "asserted": 0, "agreements": 0,
                "differences": 0, "unresolved": 0, "container_only": 1})
            self.assertEqual(container["agreements"], 1)
            self.assertEqual(container["comparable"], 1)
            finding = findings[0]
            self.assertEqual(finding["status"], mode)
            self.assertEqual(finding["date_kind"], "container_creation")
            provenance = finding["source_date_provenance"]
            self.assertFalse(provenance["capture_instant_verified"])
            self.assertEqual(provenance["timezone"], "nominal_utc")
            self.assertTrue(provenance["fields"])
            self.assertIn("does not establish", finding["message"])

    def test_capture_uses_own_sidecar_and_wins_over_container(self):
        manifest, matches, assets = self.fixture()
        item = manifest["items"][0]
        item["capture"] = {"timestamp": 1577836860, "datetime_utc": "2020-01-01T00:01:00Z"}
        item["sidecars"] = ["clip.jpg.json"]
        rows, capture, container = date_findings(manifest, matches, assets, "original")
        self.assertEqual(rows[0]["status"], "difference")
        self.assertEqual(rows[0]["date_kind"], "capture_instant")
        self.assertEqual(rows[0]["source_date_provenance"]["source_paths"], item["sidecars"])
        self.assertEqual(capture["differences"], 1)
        self.assertEqual(container["total"], 0)

    def test_bad_ambiguous_or_conflicting_sidecar_cannot_be_bypassed(self):
        for edit in ({"sidecars": ["clip.jpg.json"]}, {"issues": [{"code": "sidecar_ambiguous"}]},
                     {"capture": {"timestamp": None}}, {"issues": [{"code": "capture_time_conflict"}]}):
            with self.subTest(edit=edit):
                manifest, matches, assets = self.fixture()
                manifest["items"][0].update(edit)
                rows, capture, container = date_findings(manifest, matches, assets, "original")
                self.assertEqual(rows[0]["status"], "unresolved")
                self.assertEqual(capture["unresolved"], 1)
                self.assertEqual(container["total"], 0)

    def test_invalid_incomplete_or_nonvideo_date_cannot_be_used(self):
        for field, value in (("valid", False), ("complete", False), ("family", "image"), ("container", "unknown")):
            manifest, matches, assets = self.fixture()
            manifest["items"][0]["media"][field] = value
            rows, _, container = date_findings(manifest, matches, assets, "original")
            self.assertEqual(rows[0]["status"], "unresolved")
            self.assertEqual(container["total"], 0)
        for field, value in (("valid", False), ("complete", False), ("source", "filename"), ("timestamp", None), ("timestamp", True)):
            manifest, matches, assets = self.fixture()
            manifest["items"][0]["media"]["container_creation"][field] = value
            rows, _, _ = date_findings(manifest, matches, assets, "original")
            self.assertEqual(rows[0]["status"], "unresolved")

    def test_unknown_destination_timezone_does_not_agree(self):
        for value in (None, "2020-01-01T00:00:00", "malformed"):
            manifest, matches, assets = self.fixture()
            assets["asset"]["fileCreatedAt"] = value
            rows, _, coverage = date_findings(manifest, matches, assets, "original")
            self.assertEqual(rows[0]["status"], "unresolved")
            self.assertEqual(coverage["unresolved"], 1)
            self.assertEqual(coverage["comparable"], 0)

    def test_difference_and_whole_second_tolerance(self):
        for date, expected in (("2020-01-01T01:00:01+01:00", "original"),
                               ("2020-01-01T00:00:02Z", "difference")):
            manifest, matches, assets = self.fixture()
            assets["asset"]["fileCreatedAt"] = date
            rows, _, coverage = date_findings(manifest, matches, assets, "original")
            self.assertEqual(rows[0]["status"], expected)
            self.assertEqual(coverage["comparable"], 1)

    def test_unmatched_container_source_stays_in_denominator(self):
        manifest, matches, assets = self.fixture()
        missing = copy.deepcopy(manifest["items"][0])
        missing["path"] = "unmatched.mp4"
        manifest["items"].append(missing)
        rows, capture, container = date_findings(manifest, matches, assets, "original")
        self.assertEqual(len(rows), 1)
        self.assertEqual(container["total"], 2)
        self.assertEqual(container["comparable"], 1)
        self.assertEqual(container["unmatched"], 1)
        self.assertEqual(capture["container_only"], 2)

    def test_nonfinite_or_boolean_instants_are_never_asserted(self):
        for value in (float("nan"), float("inf"), float("-inf"), True, 10 ** 1000):
            manifest, matches, assets = self.fixture()
            manifest["items"][0]["capture"] = {"timestamp": value}
            rows, capture, _ = date_findings(manifest, matches, assets, "original")
            self.assertEqual(capture["asserted"], 0)
            self.assertEqual(rows[0]["status"], "unresolved")
            self.assertNotIn("source_date_provenance", rows[0])

    def test_capture_positive_and_unmatched_scope(self):
        manifest, matches, assets = self.fixture()
        item = manifest["items"][0]
        item["capture"] = {"timestamp": 1577836800, "datetime_utc": "2020-01-01T00:00:00Z"}
        item["sidecars"] = ["clip.jpg.json"]
        before = copy.deepcopy((manifest, matches, assets))
        rows, capture, container = date_findings(manifest, matches, assets, "original")
        self.assertEqual(rows[0]["evidence"], "Capture date agrees")
        self.assertEqual(capture["agreements"], 1)
        self.assertEqual(container["total"], 0)
        self.assertEqual(before, (manifest, matches, assets))
        rows, capture, container = date_findings(manifest, {}, assets, "original")
        self.assertFalse(rows)
        self.assertEqual(capture["asserted"], 1)
        self.assertEqual(capture["comparable"], 0)


if __name__ == "__main__":
    unittest.main()
