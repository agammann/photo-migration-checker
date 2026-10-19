"""Byte-derived types remain separate from matching bytes and pair links."""
import copy
import unittest

from pmc.media_compare import type_findings


class MediaTypeTests(unittest.TestCase):
    def setUp(self):
        self.media = {"family": "video", "mime": "video/mp4", "container": "mp4",
                      "complete": True, "valid": True, "evidence": ["MP4 video track"], "issues": []}
        self.manifest = {"items": [{"path": "component.jpg", "supported": True, "media": self.media,
                                    "extension_media_type": "image/jpeg"}]}
        self.matches = {"component.jpg": ["video-id"]}
        self.assets = {"video-id": {"type": "IMAGE"}}
        self.verified = {"video-id": {"media": self.media}}

    def check(self, mode="original"):
        return type_findings(self.manifest, self.matches, self.assets, self.verified, mode)

    def test_mp4_with_jpeg_name_and_api_image_is_a_type_difference(self):
        for mode in ("original", "checksum"):
            with self.subTest(mode=mode):
                findings, coverage = self.check(mode)
                self.assertEqual(findings[0]["status"], "difference")
                self.assertEqual(findings[0]["expected_type"], "VIDEO")
                self.assertEqual(findings[0]["mismatched_asset_ids"], ["video-id"])
                self.assertEqual(coverage["differences"], 1)

    def test_agreement_uses_container_not_extension(self):
        self.assets["video-id"]["type"] = "VIDEO"
        findings, coverage = self.check()
        self.assertEqual(findings[0]["status"], "original")
        self.assertEqual(coverage["agreements"], 1)

    def test_unknown_or_partial_container_is_not_filename_proof(self):
        for field, value in (("family", "unknown"), ("valid", False), ("complete", False)):
            with self.subTest(field=field):
                self.manifest["items"][0]["media"] = {**self.media, field: value}
                findings, coverage = self.check()
                self.assertEqual(findings[0]["status"], "unresolved")
                self.assertEqual(coverage["checked"], 0)

    def test_current_destination_container_evidence_required_in_original_mode(self):
        self.verified = {}
        self.assertEqual(self.check()[0][0]["status"], "unresolved")
        self.assertEqual(self.check("checksum")[0][0]["status"], "difference")

    def test_checksum_never_claims_destination_container_was_inspected(self):
        finding = self.check("checksum")[0][0]
        self.assertEqual(finding["destination_media"], {})
        self.assertIn("were not downloaded", finding["message"])
        self.assertEqual(finding["proof_level"], "source_container_stored_association")

    def test_missing_api_type_is_unresolved(self):
        self.assets["video-id"] = {}
        findings, coverage = self.check()
        self.assertEqual(findings[0]["status"], "unresolved")
        self.assertEqual(coverage["unresolved"], 1)

    def test_all_matching_destination_classifications_are_checked(self):
        self.matches["component.jpg"].append("other")
        self.assets["other"] = {"type": "VIDEO"}
        self.verified["other"] = {"media": self.media}
        self.assertEqual(self.check()[0][0]["status"], "difference")
        self.assets["other"] = {}
        self.assertEqual(self.check()[0][0]["status"], "unresolved")

    def test_unmatched_and_unsupported_have_no_duplicate_type_finding(self):
        self.matches = {}
        self.manifest["items"].append({"path": "unknown.bin", "supported": False})
        findings, coverage = self.check()
        self.assertEqual(findings, [])
        self.assertEqual(coverage["total"], 1)
        self.assertEqual(coverage["unmatched"], 1)

    def test_does_not_modify_inputs(self):
        before = copy.deepcopy((self.manifest, self.matches, self.assets, self.verified))
        self.check()
        self.assertEqual(before, (self.manifest, self.matches, self.assets, self.verified))
