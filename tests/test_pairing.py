"""Byte-backed paired-media rules independent of transport and source readers."""
from __future__ import annotations

import base64
import copy
import unittest

from pmc.pairing import pair_findings


IMAGE, VIDEO, OTHER = "a" * 64, "b" * 64, "c" * 64
IMAGE_SHA1, VIDEO_SHA1 = "d" * 40, "e" * 40


def stored(digest):
    return base64.b64encode(bytes.fromhex(digest)).decode()


def fixture(companion=False):
    image = {"path": "album/photo.jpg", "sha256": IMAGE, "sha1": IMAGE_SHA1, "size": 100,
             "media": {"family": "image", "container": "jpeg", "valid": True, "complete": True,
                       "embedded_video": {"validated": True, "sha256": VIDEO, "sha1": VIDEO_SHA1,
                                          "offset": 60, "size": 40}}}
    manifest = {"items": [image]}
    matches = {image["path"]: ["image"]}
    assets = {"image": {"id": "image", "type": "IMAGE", "livePhotoVideoId": "video",
                        "libraryId": None, "checksum": stored(IMAGE_SHA1), "exifInfo": {"fileSizeInByte": 100}},
              "video": {"id": "video", "type": "VIDEO", "livePhotoVideoId": None,
                        "libraryId": None, "checksum": stored(VIDEO_SHA1), "exifInfo": {"fileSizeInByte": 40}}}
    verified = {"image": {"sha256": IMAGE, "size": 100, "media": {"family": "image", "valid": True, "complete": True}},
                "video": {"sha256": VIDEO, "size": 40, "media": {"family": "video", "valid": True, "complete": True}}}
    if companion:
        manifest["items"].append({"path": "unrelated-name.jpg", "sha256": VIDEO, "sha1": VIDEO_SHA1,
                                  "size": 40, "media": {"family": "video", "container": "mp4",
                                                        "valid": True, "complete": True}})
        matches["unrelated-name.jpg"] = ["video"]
    return manifest, matches, assets, verified


class PairingTests(unittest.TestCase):
    def result(self, data=None, mode="original"):
        findings, coverage = pair_findings(*(data or fixture()), mode)
        self.assertEqual(len(findings), 1)
        return findings[0], coverage

    def test_embedded_only_export_verifies_current_linked_originals(self):
        finding, coverage = self.result()
        self.assertEqual(finding["status"], "original")
        self.assertEqual(finding["source_video_paths"], [])
        self.assertEqual(finding["destination_video_sha256"], VIDEO)
        self.assertEqual(finding["embedded_video_offset"], 60)
        self.assertEqual(coverage["original_verified"], 1)
        self.assertEqual(coverage["asserted"], 1)

    def test_hash_companion_ignores_filename_extension_and_api_type(self):
        data = fixture(companion=True)
        data[2]["video"]["type"] = "IMAGE"
        finding, coverage = self.result(data)
        self.assertEqual(finding["status"], "original")
        self.assertEqual(finding["source_video_paths"], ["unrelated-name.jpg"])
        self.assertEqual(coverage["standalone_companions"], 1)

    def test_matching_name_without_matching_bytes_does_not_associate_companion(self):
        data = fixture(companion=True)
        data[0]["items"][1].update(path="album/photo.mp4", sha256=OTHER)
        finding, _ = self.result(data)
        self.assertEqual(finding["status"], "original")
        self.assertEqual(finding["source_video_paths"], [])

    def test_checksum_relationship_is_explicitly_weaker_than_current_bytes(self):
        data = fixture()
        data[2]["video"]["checksum"] = base64.b64encode(bytes.fromhex(VIDEO_SHA1)).decode()
        data = (*data[:3], {})
        finding, coverage = self.result(data, "checksum")
        self.assertEqual(finding["status"], "checksum")
        self.assertEqual(finding["evidence"], "Stored paired-media relationship")
        self.assertIn("not independently verified", finding["message"])
        self.assertEqual(coverage["original_verified"], 0)
        self.assertEqual(coverage["checksum_supported"], 1)

    def test_missing_link_is_a_difference(self):
        data = fixture()
        data[2]["image"]["livePhotoVideoId"] = None
        finding, _ = self.result(data)
        self.assertEqual((finding["status"], finding["relation"]), ("difference", "missing_link"))

    def test_wrong_current_video_hash_overrides_matching_stored_checksum(self):
        data = fixture()
        data[3]["video"]["sha256"] = OTHER
        finding, _ = self.result(data)
        self.assertEqual((finding["status"], finding["relation"]), ("difference", "wrong_link"))

    def test_actual_image_target_rejects_pair_even_when_api_calls_it_video(self):
        data = fixture()
        data[3]["video"]["media"]["family"] = "image"
        finding, _ = self.result(data)
        self.assertEqual(finding["relation"], "non_video_target")
        self.assertEqual(finding["status"], "difference")

    def test_incomplete_image_hint_cannot_defeat_exact_video_hash_identity(self):
        data = fixture()
        data[3]["video"]["media"].update(family="image", valid=False, complete=False)
        finding, _ = self.result(data)
        self.assertEqual(finding["status"], "original")

    def test_missing_target_visibility_remains_unresolved(self):
        data = fixture()
        del data[2]["video"]
        finding, _ = self.result(data)
        self.assertEqual((finding["status"], finding["relation"]), ("unresolved", "target_inaccessible"))

    def test_unavailable_original_hash_does_not_verify(self):
        data = fixture()
        data[3]["video"] = {"error": "Original unavailable"}
        finding, _ = self.result(data)
        self.assertEqual(finding["relation"], "target_unverified")
        self.assertEqual(finding["status"], "unresolved")

    def test_full_image_must_also_be_independently_verified(self):
        data = fixture()
        data[3]["image"]["sha256"] = OTHER
        finding, _ = self.result(data)
        self.assertEqual(finding["relation"], "image_unverified")

    def test_reversed_link_is_detected_without_names_or_api_type(self):
        data = fixture(companion=True)
        data[2]["image"]["livePhotoVideoId"] = None
        data[2]["video"].update(livePhotoVideoId="image", type="IMAGE")
        finding, _ = self.result(data)
        self.assertEqual((finding["status"], finding["relation"]), ("difference", "reversed_link"))

    def test_cycles_and_self_links_are_differences(self):
        for target in ("video", "image"):
            with self.subTest(target=target):
                data = fixture()
                data[2][target]["livePhotoVideoId"] = "image"
                finding, _ = self.result(data)
                self.assertEqual(finding["relation"], "cyclic_link")

    def test_video_with_outgoing_link_is_not_verified(self):
        data = fixture()
        data[2]["video"]["livePhotoVideoId"] = "other-image"
        finding, _ = self.result(data)
        self.assertEqual(finding["relation"], "reversed_link")

    def test_multiple_image_candidates_remain_unresolved(self):
        data = fixture()
        data[1]["album/photo.jpg"].append("other-image")
        data[2]["other-image"] = {**data[2]["image"], "id": "other-image"}
        finding, _ = self.result(data)
        self.assertEqual(finding["relation"], "ambiguous_image_matches")
        self.assertEqual(finding["status"], "unresolved")

    def test_conflicting_embedded_evidence_for_identical_image_bytes_is_unresolved(self):
        data = fixture()
        duplicate = copy.deepcopy(data[0]["items"][0])
        duplicate["path"] = "another/photo.jpg"
        duplicate["media"]["embedded_video"]["sha256"] = OTHER
        data[0]["items"].append(duplicate)
        data[1][duplicate["path"]] = ["image"]
        findings, coverage = pair_findings(*data, "original")
        self.assertEqual({f["relation"] for f in findings}, {"conflicting_source"})
        self.assertEqual(coverage["unresolved"], 2)

    def test_unvalidated_or_out_of_bounds_embedded_evidence_never_asserts_pair(self):
        for change in ({"validated": False}, {"size": 41}, {"sha256": "filename-is-not-a-hash"}):
            with self.subTest(change=change):
                data = fixture()
                data[0]["items"][0]["media"]["embedded_video"].update(change)
                finding, coverage = self.result(data)
                self.assertEqual(finding["relation"], "source_pair_unasserted")
                self.assertEqual(coverage["asserted"], 0)

    def test_destination_link_without_source_assertion_stays_unresolved(self):
        data = fixture()
        del data[0]["items"][0]["media"]["embedded_video"]
        finding, _ = self.result(data)
        self.assertEqual(finding["status"], "unresolved")
        self.assertIn("Filenames", finding["message"])

    def test_declared_but_unvalidated_motion_photo_stays_unresolved_without_dest_link(self):
        data = fixture()
        del data[0]["items"][0]["media"]["embedded_video"]
        data[0]["items"][0]["media"]["motion_photo"] = {"declared": True, "validated": False}
        data[2]["image"]["livePhotoVideoId"] = None
        finding, coverage = self.result(data)
        self.assertEqual(finding["relation"], "source_pair_unasserted")
        self.assertEqual(coverage["unresolved"], 1)

    def test_unreadable_unrelated_source_hash_does_not_break_pair_comparison(self):
        data = fixture()
        data[0]["items"].append({"path": "unreadable.mp4", "sha256": None, "size": 40})
        finding, _ = self.result(data)
        self.assertEqual(finding["status"], "original")

    def test_checksum_pair_requires_full_source_image_hash_as_well(self):
        data = fixture()
        data[0]["items"][0]["sha256"] = None
        finding, _ = self.result(data, "checksum")
        self.assertEqual(finding["relation"], "image_unverified")

    def test_conflicting_declared_motion_metadata_does_not_verify(self):
        data = fixture()
        data[0]["items"][0]["media"]["motion_photo"] = {"declared": True, "validated": False}
        finding, _ = self.result(data)
        self.assertEqual(finding["status"], "unresolved")

    def test_ordinary_unpaired_images_do_not_generate_pair_findings(self):
        data = fixture()
        del data[0]["items"][0]["media"]["embedded_video"]
        data[2]["image"]["livePhotoVideoId"] = None
        findings, coverage = pair_findings(*data, "original")
        self.assertEqual(findings, [])
        self.assertEqual(coverage["total"], 0)

    def test_original_pair_can_use_hash_identity_when_target_inspection_is_unknown(self):
        data = fixture()
        data[3]["video"].pop("media")
        finding, _ = self.result(data)
        self.assertEqual(finding["status"], "original")

    def test_target_size_conflict_is_unresolved(self):
        data = fixture()
        data[3]["video"]["size"] = 41
        finding, _ = self.result(data)
        self.assertEqual(finding["relation"], "conflicting_target_size")

    def test_checksum_wrong_link_or_unknown_provenance_never_verifies(self):
        for changes, relation in (({"checksum": stored("f" * 40)}, "wrong_stored_link"),
                                  ({"libraryId": "external"}, "target_checksum_untrusted"),
                                  ({"checksum": VIDEO_SHA1}, "target_checksum_untrusted"),
                                  ({"checksum": "not-a-checksum"}, "target_checksum_untrusted")):
            with self.subTest(changes=changes):
                data = fixture()
                data[2]["video"].update(changes)
                finding, _ = self.result(data, "checksum")
                self.assertEqual(finding["relation"], relation)
                self.assertNotEqual(finding["status"], "checksum")

    def test_checksum_relationship_requires_equal_reported_target_size(self):
        for size, relation in ((None, "target_size_unavailable"), ("40", "target_size_unavailable"),
                               (False, "target_size_unavailable"), (41, "conflicting_target_size")):
            with self.subTest(size=size):
                data = fixture()
                data[2]["video"]["exifInfo"]["fileSizeInByte"] = size
                finding, _ = self.result(data, "checksum")
                self.assertEqual(finding["status"], "unresolved")
                self.assertEqual(finding["relation"], relation)

    def test_unmatched_source_image_stays_unresolved(self):
        data = fixture()
        data[1].clear()
        finding, _ = self.result(data)
        self.assertEqual(finding["relation"], "image_unmatched")

    def test_comparison_does_not_mutate_any_inputs(self):
        data = fixture(companion=True)
        before = copy.deepcopy(data)
        pair_findings(*data, "original")
        self.assertEqual(data, before)

    def test_unknown_mode_is_rejected(self):
        with self.assertRaises(ValueError):
            pair_findings(*fixture(), "filename")


if __name__ == "__main__":
    unittest.main()
