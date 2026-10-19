"""Compare byte-derived media families with Immich's reported classification."""
from __future__ import annotations


def _family(media):
    return media.get("family") if media.get("valid") is True and media.get("complete") is True else None


def type_findings(manifest, matches, assetmap, verified, mode):
    """Classify only content-matched occurrences; filenames never prove a type.

    In checksum mode the match contract belongs to the caller. Destination
    classification is compared to the source container, without asserting that
    current destination bytes have been inspected.
    """
    findings = []
    supported = [item for item in manifest["items"] if item.get("supported", True)]
    coverage = {"total": len(supported), "matched": 0, "checked": 0,
                "agreements": 0, "differences": 0, "unresolved": 0, "unmatched": 0}
    for item in supported:
        ids = matches.get(item["path"], [])
        if not ids:
            coverage["unmatched"] += 1
            continue
        coverage["matched"] += 1
        media = item.get("media") or {}
        family = _family(media)
        expected = {"image": "IMAGE", "video": "VIDEO"}.get(family)
        types = {ident: assetmap.get(ident, {}).get("type") for ident in ids}
        actual = {ident: verified.get(ident, {}).get("media", {}) for ident in ids} if mode == "original" else {}
        unknown = [ident for ident in ids if types[ident] not in {"IMAGE", "VIDEO"} or
                   (mode == "original" and (_family(actual[ident]) != family or verified.get(ident, {}).get("error")))]
        wrong = [ident for ident in ids if expected and types[ident] in {"IMAGE", "VIDEO"} and types[ident] != expected]
        if expected is None or unknown:
            status, evidence = "unresolved", "Media type unresolved"
            message = "Media family could not be established from supported complete container structure, or destination classification/original evidence is unavailable. The filename was not used as proof."
            coverage["unresolved"] += 1
        elif wrong:
            status, evidence = "difference", "Media type difference"
            message = f"Source container is {family} media, but Immich reports a different media type for {len(wrong)} matched asset(s)."
            coverage["differences"] += 1
            coverage["checked"] += 1
        else:
            status, evidence = mode, "Media type agrees"
            message = f"The {family} family established by source container structure agrees with Immich's media type."
            coverage["agreements"] += 1
            coverage["checked"] += 1
        if mode == "original":
            message += " Current downloaded original containers were inspected alongside their content hashes; this does not verify decoding or playback."
        else:
            message += " The content association uses the server's stored upload checksum; current destination containers were not downloaded or independently verified."
        findings.append({"kind": "media_type", "status": status, "evidence": evidence, "path": item["path"],
                         "asset_ids": ids, "message": message, "expected_type": expected,
                         "source_media": media, "source_filename_mime": item.get("extension_media_type"),
                         "destination_types": types, "destination_media": actual,
                         "mismatched_asset_ids": wrong, "unknown_asset_ids": unknown,
                         "proof_level": "current_original_container" if mode == "original" else "source_container_stored_association"})
    return findings, coverage
