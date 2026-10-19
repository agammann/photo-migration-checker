"""Deterministic source-manifest checks; no Immich service is required here."""
from __future__ import annotations

import hashlib
import json
import os
import struct
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from pmc.sample import create_sample
from pmc.source import CHUNK_SIZE, MAX_JSON_BYTES, SourceCancelled, scan_source
import pmc.source as source_module

EXPECTED = json.loads((Path(__file__).parent / "fixtures" / "expected.json").read_text(encoding="utf-8"))


def _snapshot(root: Path) -> dict:
    return {path.relative_to(root).as_posix(): (path.stat().st_size, path.stat().st_mtime_ns, hashlib.sha256(path.read_bytes()).hexdigest()) for path in root.rglob("*") if path.is_file()}


class SourceTests(unittest.TestCase):
    def test_byte_container_classification_survives_wrong_or_unknown_extension(self):
        from pmc.sample import _avi, _png
        with tempfile.TemporaryDirectory(prefix="pmc-media-extension-") as directory:
            root = Path(directory)
            (root / "video.jpg").write_bytes(_avi())
            (root / "image.bin").write_bytes(_png(1, 2, 3))
            items = {item["path"]: item for item in scan_source(root)["items"]}
            self.assertEqual(items["video.jpg"]["media_type"], "video/x-msvideo")
            self.assertEqual(items["video.jpg"]["extension_media_type"], "image/jpeg")
            self.assertEqual(items["video.jpg"]["media"]["family"], "video")
            self.assertTrue(items["image.bin"]["supported"])
            self.assertEqual(items["image.bin"]["media_type"], "image/png")

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="pmc-source-test-")
        self.base = Path(self.temporary.name)
        self.addCleanup(self.temporary.cleanup)

    def sample(self, scenario="problems"):
        return create_sample(self.base / scenario, scenario)

    def write(self, name: str, content: bytes) -> Path:
        target = self.base / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return target

    def test_correct_fixture_matches_static_expected_without_false_alarms(self):
        sample = self.sample("correct")
        manifest = scan_source(sample["source"])
        expected = EXPECTED["correct"]
        self.assertEqual(sample["expected"], expected)
        self.assertEqual(manifest["issues"], [])
        self.assertEqual(len(manifest["items"]), expected["source_media_occurrences"])
        for item in manifest["items"]:
            digest = expected["hashes"][item["path"]]
            self.assertEqual((item["sha256"], item["sha1"], item["size"]), (digest["sha256"], digest["sha1"], digest["size"]))
            self.assertEqual(len(item["sidecars"]), 1)
            self.assertEqual(item["capture"]["timestamp"], 1700000000)
            self.assertTrue(item["supported"])

    def test_seeded_source_problems_match_expected(self):
        sample = self.sample()
        manifest = scan_source(sample["source"])
        expected = EXPECTED["problems"]
        self.assertEqual(sample["expected"], expected)
        self.assertEqual(len(manifest["items"]), expected["source_media_occurrences"] + len(expected["unsupported_paths"]))
        by_code = {}
        for issue in manifest["issues"]:
            by_code.setdefault(issue["code"], []).append(issue["path"])
        self.assertEqual(sorted(by_code["unsupported_format"]), expected["unsupported_paths"])
        self.assertEqual(by_code["sidecar_malformed"], expected["malformed_sidecars"])
        self.assertEqual(by_code["sidecar_ambiguous"], expected["ambiguous_sidecars"])
        self.assertEqual(by_code["capture_time_unresolved"], expected["uncertain_capture_paths"])
        self.assertEqual(sorted(by_code["paired_media_uncertain"]), expected["paired_paths"])

    def test_source_tree_is_unchanged_including_sidecars(self):
        sample = self.sample()
        before = _snapshot(sample["source"])
        manifest = scan_source(sample["source"])
        self.assertEqual(_snapshot(sample["source"]), before)
        self.assertEqual(len(manifest["inventory"]), len(before))
        self.assertEqual(sum(entry["size"] for entry in manifest["inventory"]), manifest["inventory_bytes"])

    def test_duplicates_and_edited_versions_remain_distinct_occurrences(self):
        manifest = scan_source(self.sample("correct")["source"])
        items = {item["path"]: item for item in manifest["items"]}
        self.assertEqual(len(manifest["duplicate_groups"]), 1)
        self.assertEqual(manifest["duplicate_groups"][0]["paths"], EXPECTED["correct"]["duplicate_occurrences"][0])
        self.assertNotEqual(items["Family/portrait.png"]["sha256"], items["Family/portrait-edited.png"]["sha256"])
        self.assertNotEqual(items["Family/collision.png"]["sha256"], items["Weekend/collision.png"]["sha256"])

    def test_duplicate_album_titles_use_stable_directory_keys(self):
        manifest = scan_source(self.sample("correct")["source"])
        self.assertEqual(manifest["album_titles"], {"Family": "Trips", "Weekend": "Trips", "Videos": "Videos"})
        items = {item["path"]: item for item in manifest["items"]}
        self.assertEqual(items["Family/sunrise.png"]["albums"], ["Family"])
        self.assertEqual(items["Weekend/sunrise.png"]["albums"], ["Weekend"])

    def test_directory_alone_does_not_assert_album(self):
        self.write("Pictures from 2023/photo.png", b"not decoded by byte checker")
        manifest = scan_source(self.base)
        self.assertEqual(manifest["album_titles"], {})
        self.assertEqual(manifest["items"][0]["albums"], [])
        self.assertEqual(manifest["items"][0]["directory_hint"], "Pictures from 2023")

    def test_conflicting_album_metadata_does_not_assert_identity_or_membership(self):
        self.write("Album/photo.png", b"photo")
        self.write("Album/metadata.json", b'{"title":"Album A","description":""}')
        self.write("Album/other.json", b'{"albumData":{"title":"Album B"}}')
        manifest = scan_source(self.base)
        self.assertEqual(manifest["album_titles"], {})
        self.assertEqual(manifest["items"][0]["albums"], [])
        self.assertEqual(len(manifest["items"]), 1)
        conflict = next(issue for issue in manifest["issues"] if issue["code"] == "album_metadata_conflict")
        self.assertEqual(conflict["path"], "Album")
        self.assertEqual(conflict["metadata_paths"], ["Album/metadata.json", "Album/other.json"])
        self.assertEqual(conflict["titles"], ["Album A", "Album B"])

    def test_corroborating_album_metadata_keeps_membership(self):
        self.write("Album/photo.png", b"photo")
        self.write("Album/metadata.json", b'{"title":"Same album","description":""}')
        self.write("Album/other.json", b'{"albumData":{"title":"Same album"}}')
        manifest = scan_source(self.base)
        self.assertEqual(manifest["album_titles"], {"Album": "Same album"})
        self.assertEqual(manifest["items"][0]["albums"], ["Album"])
        self.assertEqual(manifest["issues"], [])

    def test_supplemental_metadata_and_unique_title_associations(self):
        self.write("photo.png", b"a")
        self.write("photo.png.supplemental-metadata.json", b'{"photoTakenTime":{"timestamp":"10"}}')
        self.write("other.png", b"b")
        self.write("renamed-sidecar.json", b'{"title":"other.png","photoTakenTime":{"timestamp":"20"}}')
        manifest = scan_source(self.base)
        items = {item["path"]: item for item in manifest["items"]}
        self.assertEqual(items["photo.png"]["capture"]["timestamp"], 10)
        self.assertEqual(items["other.png"]["capture"]["timestamp"], 20)
        self.assertEqual(items["photo.png"]["sidecar_evidence"][0]["method"], "exact_filename")
        self.assertEqual(items["other.png"]["sidecar_evidence"][0]["method"], "sidecar_title")

    def test_ambiguous_truncation_is_never_selected(self):
        manifest = scan_source(self.sample()["source"])
        candidates = [item for item in manifest["items"] if "this-is-a-very-long-" in item["path"]]
        self.assertEqual(len(candidates), 2)
        self.assertTrue(all(item["sidecars"] == [] and item["capture"] is None for item in candidates))
        self.assertTrue(all(any(issue["code"] == "sidecar_ambiguous" for issue in item["issues"]) for item in candidates))

    def test_conflicting_sidecar_capture_times_remain_unresolved(self):
        self.write("photo.png", b"a")
        self.write("photo.png.json", b'{"photoTakenTime":{"timestamp":"10"}}')
        self.write("photo.png.supplemental-metadata.json", b'{"photoTakenTime":{"timestamp":"20"}}')
        manifest = scan_source(self.base)
        self.assertIsNone(manifest["items"][0]["capture"])
        self.assertIn("capture_time_conflict", [issue["code"] for issue in manifest["issues"]])

    def test_conflicting_filename_and_title_evidence_remains_ambiguous(self):
        self.write("first.png", b"a")
        self.write("second.png", b"b")
        self.write("first.png.json", b'{"title":"second.png","photoTakenTime":{"timestamp":"10"}}')
        manifest = scan_source(self.base)
        self.assertTrue(all(item["capture"] is None and not item["sidecars"] for item in manifest["items"]))
        self.assertIn("sidecar_ambiguous", [issue["code"] for issue in manifest["issues"]])

    def test_conflicting_truncated_filename_and_title_remains_ambiguous(self):
        self.write("photo.png", b"original")
        self.write("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-edited.png", b"edited")
        self.write("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-.json", b'{"title":"photo.png","photoTakenTime":{"timestamp":"20"}}')
        manifest = scan_source(self.base)
        self.assertTrue(all(item["capture"] is None and not item["sidecars"] for item in manifest["items"]))
        self.assertIn("sidecar_ambiguous", [issue["code"] for issue in manifest["issues"]])

    def test_renamed_duplicate_exact_filename_and_original_title_stays_ambiguous(self):
        self.write("photo.png", b"original")
        self.write("photo(1).png", b"different content")
        self.write("photo(1).png.json", b'{"title":"photo.png","photoTakenTime":{"timestamp":"20"}}')
        manifest = scan_source(self.base)
        self.assertTrue(all(item["capture"] is None and not item["sidecars"] for item in manifest["items"]))
        self.assertIn("sidecar_ambiguous", [issue["code"] for issue in manifest["issues"]])

    def test_unique_title_can_disambiguate_compatible_truncated_prefix(self):
        self.write("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-first.png", b"a")
        self.write("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-second.png", b"b")
        self.write("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-.json", b'{"title":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-second.png","photoTakenTime":{"timestamp":"20"}}')
        manifest = scan_source(self.base)
        items = {item["path"]: item for item in manifest["items"]}
        self.assertIsNone(items["aaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-first.png"]["capture"])
        self.assertEqual(items["aaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-second.png"]["capture"]["timestamp"], 20)
        self.assertEqual(manifest["issues"], [])

    def test_capture_timezone_and_filesystem_time_are_distinct(self):
        manifest = scan_source(self.sample()["source"])
        items = {item["path"]: item for item in manifest["items"]}
        known = items["Weekend/dated.png"]
        self.assertEqual(known["capture"]["datetime_utc"], "2023-11-14T22:13:20Z")
        self.assertEqual(known["capture"]["timezone"], "utc")
        self.assertTrue(known["capture"]["timezone_uncertain"])
        self.assertIn("mtime_ns", known["stat"])
        unknown = items["Weekend/clock.png"]
        self.assertIsNone(unknown["capture"]["timestamp"])
        self.assertEqual(unknown["capture"]["timezone"], "unknown")

    def test_oversized_json_is_not_parsed_but_is_inventoried(self):
        self.write("photo.png", b"a")
        oversized = self.write("photo.png.json", b" " * (MAX_JSON_BYTES + 1))
        manifest = scan_source(self.base)
        self.assertIn("sidecar_too_large", [issue["code"] for issue in manifest["issues"]])
        entry = next(entry for entry in manifest["inventory"] if entry["path"] == oversized.name)
        self.assertEqual(entry["size"], MAX_JSON_BYTES + 1)
        self.assertIsNotNone(entry["sha256"])
        self.assertIsNone(manifest["items"][0]["capture"])

    def test_unrecognized_json_and_extensions_are_not_lost(self):
        self.write("settings.json", b'{"custom":"value"}')
        self.write("edit.aae", b"anything")
        manifest = scan_source(self.base)
        self.assertEqual([item["path"] for item in manifest["items"]], ["edit.aae", "settings.json"])
        self.assertTrue(all(not item["supported"] for item in manifest["items"]))
        self.assertEqual(len(manifest["inventory"]), 2)

    def test_hashes_stream_more_than_one_chunk(self):
        content = (b"abc0123456789" * ((CHUNK_SIZE * 2) // 13 + 1)) + b"tail"
        self.write("large.mp4", content)
        manifest = scan_source(self.base)
        self.assertEqual(manifest["items"][0]["sha256"], hashlib.sha256(content).hexdigest())
        self.assertEqual(manifest["items"][0]["sha1"], hashlib.sha1(content).hexdigest())

    def test_cancel_before_and_during_scan(self):
        source = self.sample("correct")["source"]
        event = threading.Event()
        event.set()
        with self.assertRaises(SourceCancelled):
            scan_source(source, cancel=event)
        event.clear()
        with self.assertRaises(SourceCancelled):
            scan_source(source, cancel=event, progress=lambda _: event.set())
        self.assertEqual(scan_source(source)["issues"], [])

    def test_progress_reports_complete_inventory_counts(self):
        source = self.sample("correct")["source"]
        events = []
        manifest = scan_source(source, progress=events.append)
        self.assertEqual(events[-1]["files_scanned"], len(manifest["inventory"]))
        self.assertEqual(events[-1]["bytes_scanned"], manifest["inventory_bytes"])
        self.assertEqual(events[-1]["files_scanned"], events[-1]["files_total"])

    def test_unreadable_file_is_visible_without_leaking_absolute_path(self):
        self.write("photo.png", b"a")
        with patch.object(source_module, "_safe_open", side_effect=PermissionError("private full path intentionally omitted")):
            manifest = scan_source(self.base)
        item = manifest["items"][0]
        self.assertIsNone(item["sha256"])
        self.assertEqual(item["issues"][0]["code"], "file_unreadable")
        self.assertNotIn(str(self.base), json.dumps(manifest))

    def test_mutation_during_stream_invalidates_hashes(self):
        target = self.write("photo.png", b"a" * (CHUNK_SIZE + 1))
        safe_open = source_module._safe_open
        class MutatingReader:
            def __init__(self, handle):
                self.handle = handle
                self.changed = False
            def __enter__(self):
                return self
            def __exit__(self, *_):
                self.handle.close()
            def fileno(self):
                return self.handle.fileno()
            def read(self, size):
                content = self.handle.read(size)
                if not self.changed:
                    with target.open("ab") as writer:
                        writer.write(b"changed")
                    self.changed = True
                return content
        with patch.object(source_module, "_safe_open", side_effect=lambda path, root: MutatingReader(safe_open(path, root))):
            manifest = scan_source(self.base)
        self.assertIsNone(manifest["items"][0]["sha256"])
        self.assertIsNone(manifest["items"][0]["sha1"])
        self.assertIn("source_changed", [issue["code"] for issue in manifest["issues"]])

    def test_symbolic_links_are_never_followed(self):
        outside = self.base / "outside"
        outside.mkdir()
        (outside / "secret.png").write_bytes(b"secret")
        source = self.base / "source"
        source.mkdir()
        try:
            os.symlink(outside, source / "linked", target_is_directory=True)
            os.symlink(outside / "secret.png", source / "secret.png")
        except OSError as exc:
            self.skipTest(f"Creating symbolic links is unavailable: {type(exc).__name__}")
        manifest = scan_source(source)
        self.assertEqual(manifest["items"], [])
        self.assertEqual(manifest["inventory"], [])
        self.assertEqual(len([issue for issue in manifest["issues"] if issue["code"] == "symlink_skipped"]), 2)

    @unittest.skipUnless(os.name == "nt", "Windows junction test")
    def test_windows_junction_is_never_followed(self):
        outside = self.base / "outside"
        outside.mkdir()
        (outside / "secret.png").write_bytes(b"secret")
        source = self.base / "source"
        source.mkdir()
        result = subprocess.run(["cmd", "/c", "mklink", "/J", str(source / "linked"), str(outside)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = scan_source(source)
        self.assertEqual(manifest["items"], [])
        self.assertEqual(manifest["inventory"], [])
        self.assertEqual(manifest["issues"][0]["code"], "symlink_skipped")
        self.assertTrue((outside / "secret.png").exists())

    def test_fixture_images_and_video_have_real_container_headers(self):
        sample = self.sample("correct")
        from PIL import Image
        with Image.open(sample["source"] / "Family/sunrise.png") as image:
            image.load()
            self.assertEqual(image.size, (2, 2))
        video = (sample["source"] / "Videos/clip.avi").read_bytes()
        self.assertEqual(video[:4], b"RIFF")
        self.assertEqual(video[8:12], b"AVI ")
        self.assertEqual(struct.unpack("<I", video[4:8])[0], len(video) - 8)
        self.assertIn(b"movi", video)
        self.assertIn(b"idx1", video)

    def test_sample_generator_refuses_overwrite(self):
        sample = self.sample("correct")
        before = _snapshot(sample["source"])
        with self.assertRaises(ValueError):
            create_sample(self.base / "correct", "correct")
        self.assertEqual(before, _snapshot(sample["source"]))


if __name__ == "__main__":
    unittest.main()
