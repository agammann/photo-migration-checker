"""Compare paired-media evidence without filesystem or network access.

``matches`` must contain only source-to-asset content matches established by the
caller. In checksum mode this includes the caller's Immich-version compatibility
gate. Names, suffixes and the API's IMAGE/VIDEO classification never pair bytes.
"""
from __future__ import annotations

import base64
import binascii
import re
from collections import Counter, defaultdict


def _hex(value, length):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-fA-F]{%d}" % length, value) is not None


def _sha256(value):
    return value.lower() if _hex(value, 64) else None


def _stored_sha1(asset):
    if "libraryId" not in asset or asset["libraryId"] is not None:
        return None
    value = asset.get("checksum")
    if not isinstance(value, str):
        return None
    try:
        decoded = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error):
        return None
    return decoded.hex() if len(decoded) == 20 else None


def _embedded(item):
    media = item.get("media") or {}
    embedded = media.get("embedded_video") or {}
    declaration = media.get("motion_photo") or {}
    size, offset = embedded.get("size"), embedded.get("offset")
    if not (media.get("complete") is True and media.get("valid") is True
            and media.get("family") == "image" and media.get("container") in {"jpeg", "jpg"}
            and embedded.get("validated") is True and _hex(embedded.get("sha256"), 64)
            and not (declaration.get("declared") is True and declaration.get("validated") is not True)
            and isinstance(size, int) and not isinstance(size, bool) and size > 0
            and isinstance(offset, int) and not isinstance(offset, bool) and offset >= 0
            and isinstance(item.get("size"), int) and offset + size == item["size"]):
        return None
    return embedded


def _link(asset):
    value = asset.get("livePhotoVideoId")
    return value if isinstance(value, str) and value else None


def _cycle(start, assets):
    seen, current = set(), start
    while current in assets:
        if current in seen:
            return True
        seen.add(current)
        current = _link(assets[current])
    return False


def pair_findings(manifest, matches, assetmap, verified, mode):
    """Return ``(findings, coverage)`` for validated source motion-photo pairs.

    A validated embedded MP4 alone asserts an expected pair. Standalone source
    companions are optional; they are associated only by full SHA-256 and size.
    ``original`` attests independently downloaded image and linked-video bytes.
    ``checksum`` describes compatible stored upload checksums and a stored link;
    it deliberately makes no claim about current destination bytes.

    Coverage ``asserted`` counts source image occurrences; ``source_pairs`` counts
    unique image/video hash pairs. ``standalone_companions`` counts assertions
    with at least one full-hash companion. ``total`` also includes destination
    links for which the source cannot assert a pair. Other counters count
    findings at their explicit evidence level. Inputs are never modified.
    """
    if mode not in {"original", "checksum"}:
        raise ValueError("Pair comparison mode must be original or checksum.")
    verified = verified or {}
    items = manifest.get("items", [])
    assertions = [(item, _embedded(item)) for item in items if _embedded(item)]
    expectations = defaultdict(set)
    for item, embedded in assertions:
        expectations[_sha256(item.get("sha256"))].add((embedded["sha256"].lower(), embedded["size"]))
    findings, covered_videos = [], set()

    for item, embedded in assertions:
        expected_sha = embedded["sha256"].lower()
        expected_sha1 = embedded.get("sha1", "").lower() if _hex(embedded.get("sha1"), 40) else None
        image_ids = sorted(set(matches.get(item["path"], [])))
        companions = [other for other in items if other is not item
                      and _sha256(other.get("sha256")) == expected_sha
                      and other.get("size") == embedded["size"]
                      and (other.get("media") or {}).get("family") == "video"
                      and (other.get("media") or {}).get("complete") is True
                      and (other.get("media") or {}).get("valid") is True]
        companion_ids = {ident for other in companions for ident in matches.get(other["path"], [])}
        links = {ident: _link(assetmap.get(ident, {})) for ident in image_ids}
        video_ids = set(companion_ids) | {ident for ident in links.values() if ident}
        finding = {"kind": "paired_media", "path": item["path"], "asset_ids": sorted(set(image_ids) | video_ids),
                   "image_asset_ids": image_ids, "video_asset_ids": sorted(video_ids),
                   "source_video_paths": sorted({other["path"] for other in companions}),
                   "source_sha256": item.get("sha256"), "expected_video_sha256": expected_sha,
                   "expected_video_sha1": expected_sha1, "expected_video_size": embedded["size"],
                   "embedded_video_offset": embedded["offset"],
                   "destination_links": links}

        def finish(status, relation, message):
            finding.update(status=status, relation=relation, message=message,
                           evidence={"original": "Verified paired original bytes",
                                     "checksum": "Stored paired-media relationship",
                                     "difference": "Paired media difference", "unresolved": "Pair evidence unresolved"}[status])
            findings.append(finding)
            covered_videos.update(finding["video_asset_ids"])

        if len(expectations[_sha256(item.get("sha256"))]) != 1:
            finish("unresolved", "conflicting_source", "Identical source image hashes have conflicting embedded-video evidence; no pair was chosen.")
            continue
        if not image_ids or any(ident not in assetmap for ident in image_ids):
            finish("unresolved", "image_unmatched", "The source image has no accessible proved destination content match, so its pair cannot be checked.")
            continue
        if len(image_ids) != 1:
            finish("unresolved", "ambiguous_image_matches", "Multiple matching destination images provide candidate relationships; no image identity was guessed.")
            continue
        image_id = image_ids[0]
        image_proof = verified.get(image_id, {})
        if not _sha256(item.get("sha256")):
            finish("unresolved", "image_unverified", "The source image lacks a complete full-file SHA-256 hash, so its embedded and destination evidence cannot be joined reliably.")
            continue
        if mode == "original":
            if image_proof.get("error") or _sha256(image_proof.get("sha256")) != item["sha256"].lower():
                finish("unresolved", "image_unverified", "Current destination image bytes do not provide the required full source-image SHA-256 proof.")
                continue
        elif not _hex(item.get("sha1"), 40) or _stored_sha1(assetmap[image_id]) != item["sha1"].lower():
            finish("unresolved", "image_checksum_untrusted", "The image's stored upload checksum or provenance does not establish the source match; current bytes were not verified.")
            continue
        if _cycle(image_id, assetmap):
            finish("difference", "cyclic_link", "The destination paired-media links form a cycle instead of an image-to-video relationship.")
            continue
        target = links[image_id]
        if not target:
            reverse = []
            for ident, asset in assetmap.items():
                proof = verified.get(ident, {})
                expected_match = (proof.get("sha256") == expected_sha and not proof.get("error")) if mode == "original" else (expected_sha1 and _stored_sha1(asset) == expected_sha1)
                if _link(asset) == image_id and expected_match:
                    reverse.append(ident)
            if reverse:
                finding["video_asset_ids"] = sorted(set(finding["video_asset_ids"]) | set(reverse))
                finding["asset_ids"] = sorted(set(finding["asset_ids"]) | set(reverse))
                finding["reverse_links"] = {ident: image_id for ident in sorted(reverse)}
                finish("difference", "reversed_link", "The matching destination video points to the image, but the image has no link to its expected video.")
            else:
                finish("difference", "missing_link", "The matched destination image has no livePhotoVideoId link for the source's validated embedded video.")
            continue
        if target not in assetmap:
            finish("unresolved", "target_inaccessible", "The linked video is outside the readable destination inventory; its bytes and relationship cannot be established.")
            continue
        if _link(assetmap[target]):
            finish("difference", "reversed_link", "The linked video itself has an outgoing paired-media link instead of ending the image-to-video relationship.")
            continue
        target_proof = verified.get(target, {})
        target_media = target_proof.get("media") or {}
        if mode == "original" and target_media.get("family") == "image" and target_media.get("valid") is True and target_media.get("complete") is True:
            finish("difference", "non_video_target", "The destination link points to bytes independently identified as an image rather than the expected embedded video.")
            continue
        if mode == "original":
            if target_proof.get("error") or not _hex(target_proof.get("sha256"), 64):
                finish("unresolved", "target_unverified", "The linked destination original could not be independently hashed; the pair remains unresolved.")
            elif target_proof["sha256"].lower() != expected_sha:
                finish("difference", "wrong_link", "The linked destination original's SHA-256 differs from the source's validated embedded MP4.")
            elif target_proof.get("size") != embedded["size"]:
                finish("unresolved", "conflicting_target_size", "The linked original hash matches but its reported streamed size conflicts with the embedded source video; evidence is inconsistent.")
            else:
                finding["destination_video_sha256"] = target_proof["sha256"].lower()
                finish("original", "verified", "The independently downloaded image matches the whole source image, and its livePhotoVideoId target's current SHA-256 and size match the validated embedded MP4. API media-type labels were not used to pair bytes.")
        elif not expected_sha1 or not _stored_sha1(assetmap[target]):
            finish("unresolved", "target_checksum_untrusted", "The linked asset has no compatible uploaded-original SHA-1 evidence or the source embedded SHA-1 is unavailable; current bytes were not verified.")
        elif _stored_sha1(assetmap[target]) != expected_sha1:
            finish("difference", "wrong_stored_link", "The linked asset's stored upload SHA-1 differs from the validated embedded video's SHA-1; current destination bytes were not downloaded.")
        else:
            reported_size = (assetmap[target].get("exifInfo") or {}).get("fileSizeInByte")
            if not isinstance(reported_size, int) or isinstance(reported_size, bool) or reported_size < 0:
                finish("unresolved", "target_size_unavailable", "The stored video checksum matches, but its reported original size is unavailable; current destination bytes were not downloaded.")
            elif reported_size != embedded["size"]:
                finish("unresolved", "conflicting_target_size", "The stored video checksum matches, but its reported original size differs from the embedded source video; current destination bytes were not downloaded.")
            else:
                finish("checksum", "stored_supported", "The matched image's stored link targets a compatible uploaded-original checksum and reported size matching the embedded video. This is stored relationship evidence; current image and video bytes were not independently verified.")

    asserted_paths = {item["path"] for item, _ in assertions}
    for item in items:
        if item["path"] in asserted_paths:
            continue
        image_ids = sorted(ident for ident in set(matches.get(item["path"], []))
                           if ident in assetmap and _link(assetmap[ident]) and ident not in covered_videos)
        media = item.get("media") or {}
        has_unvalidated_embedded = "embedded_video" in media or (media.get("motion_photo") or {}).get("declared") is True
        if not image_ids and not has_unvalidated_embedded:
            continue
        links = {ident: _link(assetmap[ident]) for ident in image_ids}
        findings.append({"kind": "paired_media", "status": "unresolved", "evidence": "Pair evidence unresolved",
                         "relation": "source_pair_unasserted", "path": item["path"], "asset_ids": image_ids,
                         "image_asset_ids": image_ids, "video_asset_ids": sorted({v for v in links.values() if v}),
                         "source_video_paths": [], "destination_links": links,
                         "message": "The source has no complete validated embedded-video assertion for this relationship. Filenames and destination links alone do not establish a source pair."})
    counts = Counter(finding["status"] for finding in findings)
    coverage = {"asserted": len(assertions),
                "source_pairs": len({(item.get("sha256"), embedded["sha256"].lower()) for item, embedded in assertions}),
                "standalone_companions": sum(bool(finding["source_video_paths"]) for finding in findings),
                "original_verified": counts["original"], "checksum_supported": counts["checksum"],
                "differences": counts["difference"], "unresolved": counts["unresolved"], "total": len(findings)}
    return findings, coverage
