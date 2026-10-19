"""Evidence rules independent of HTTP, storage and user interface."""
from __future__ import annotations

from collections import Counter, defaultdict

from .dates_compare import date_findings
from .immich import decode_checksum
from .media_compare import type_findings
from .pairing import pair_findings

LABELS = {"original": "Verified original bytes", "checksum": "Server-reported checksum match",
          "possible": "Possible match", "missing": "Missing", "mismatched": "Mismatched",
          "ambiguous": "Ambiguous", "inaccessible": "Inaccessible", "unsupported": "Unsupported"}


def compare(manifest: dict, destination: dict, mode: str, verified: dict | None = None) -> dict:
    verified = verified or {}
    by_hash, by_name = defaultdict(list), defaultdict(list)
    assets = destination.get("assets", [])
    issues = list(manifest.get("issues", [])) + list(destination.get("issues", []))
    checksum_compatible = destination.get("version") == "3.3.3"
    untrusted = []
    for asset in assets:
        ident = asset["id"]
        by_name[asset.get("originalFileName", "")].append(ident)
        if mode == "original":
            proof = verified.get(ident, {})
            if proof.get("sha256") and not proof.get("error"):
                by_hash[proof["sha256"]].append(ident)
            else:
                untrusted.append(ident)
        else:
            digest = decode_checksum(asset.get("checksum"))
            # Missing libraryId means unknown provenance, not an uploaded original.
            if checksum_compatible and "libraryId" in asset and asset["libraryId"] is None and digest:
                by_hash[digest].append(ident)
            else:
                untrusted.append(ident)
    asset_map = {a["id"]: a for a in assets}
    findings, matches = [], {}
    for asset in assets:
        if asset.get("isOffline"):
            findings.append({"kind": "destination", "status": "inaccessible", "evidence": "Inaccessible",
                             "path": "Destination asset", "asset_ids": [asset["id"]],
                             "message": "Immich reports this original as offline. A stored checksum cannot establish availability."})
    inaccessible = bool(destination.get("issues")) or bool(untrusted)
    occurrences = Counter(i.get("sha256") for i in manifest["items"])
    for item in manifest["items"]:
        path = item["path"]
        digest = item.get("sha256" if mode == "original" else "sha1")
        ids = sorted(by_hash.get(digest, [])) if digest else []
        status = mode if ids else "missing"
        explanation = ("SHA-256 of streamed destination original matches the source bytes." if mode == "original"
                       else "Source SHA-1 matches the server's stored upload checksum; current original bytes were not downloaded.")
        if not item.get("sha256"):
            status, explanation = "inaccessible", "Source bytes could not be read reliably."
        elif not item.get("supported", True):
            status, explanation = "unsupported", "This file format is outside the supported media list; it remains in the manifest."
        elif not ids:
            candidate_ids = by_name.get(path.rsplit("/", 1)[-1], [])
            if inaccessible:
                status, explanation = "inaccessible", "No verified content match; destination coverage or checksum provenance is incomplete."
            elif candidate_ids:
                status = "mismatched" if mode == "original" else "possible"
                explanation = ("A destination filename matches, but the downloaded original bytes differ." if mode == "original"
                               else "A filename matches, but its stored checksum differs. Filename equality is not content proof.")
            else:
                explanation = ("No destination original has matching SHA-256 bytes in the accessible inventory." if mode == "original"
                               else "No matching stored upload checksum in the accessible inventory; original bytes were not downloaded.")
            ids = sorted(candidate_ids)
        else:
            matches[path] = ids
        findings.append({"kind": "content", "status": status, "evidence": LABELS[status], "path": path,
                         "asset_ids": ids, "message": explanation, "source_sha256": item.get("sha256"),
                         "source_sha1": item.get("sha1"), "size": item.get("size"),
                         "destination_sha256": {i: verified[i]["sha256"] for i in ids if verified.get(i, {}).get("sha256")},
                         "sidecars": item.get("sidecars", []), "source_occurrences": occurrences[item.get("sha256")]})
        for issue in item.get("issues", []):
            findings.append({"kind": "source_metadata", "status": "unresolved", "evidence": "Unresolved",
                             "path": path, "asset_ids": matches.get(path, []),
                             "message": issue.get("message", str(issue))})
    date_results, capture_coverage, container_coverage = date_findings(manifest, matches, asset_map, mode)
    findings.extend(date_results)
    for auxiliary in manifest.get("auxiliary_files", []):
        findings.append({"kind": "auxiliary", "status": "not_applicable", "evidence": "Empty auxiliary metadata",
                         "path": auxiliary["path"], "asset_ids": [], "message": auxiliary["message"],
                         "classification": auxiliary["classification"], "content_state": auxiliary["content_state"],
                         "size": auxiliary["size"], "source_sha256": auxiliary["sha256"], "source_sha1": auxiliary["sha1"]})
    pair_results, pair_coverage = pair_findings(manifest, matches, asset_map, verified, mode)
    type_results, type_coverage = type_findings(manifest, matches, asset_map, verified, mode)
    findings.extend(pair_results)
    findings.extend(type_results)
    # Album identity is determined by asset membership. Titles only break ties / explain differences.
    source_albums = defaultdict(list, {key: [] for key in manifest.get("album_titles", {})})
    for item in manifest["items"]:
        for album in item.get("albums", []):
            source_albums[album].append(item["path"])
    album_evidence = {}
    for album, paths in source_albums.items():
        title = manifest.get("album_titles", {}).get(album, album)
        known = [set(matches[p]) for p in paths if p in matches]
        complete = len(known) == len(paths)
        expected_ids = set().union(*known) if known else set()
        exact = [a for a in destination.get("albums", []) if complete and
                 all(set(a["asset_ids"]) & group for group in known) and
                 set(a["asset_ids"]).issubset(expected_ids)]
        album_evidence[album] = {"title": title, "known": known, "complete": complete,
                                 "expected_ids": expected_ids, "exact": exact}
    # Album identities are one-to-one even when they contain identical bytes.
    # Membership establishes candidates; a unique equal title can break a tie.
    # Resolve forced choices first, keeping competing identities explicit.
    assigned, consumed = {}, set()
    while True:
        choices = {}
        for album, proof in album_evidence.items():
            if album in assigned:
                continue
            available = [a for a in proof["exact"] if a["id"] not in consumed]
            named = [a for a in available if a["albumName"] == proof["title"]]
            choices[album] = named or available
        single_claims = Counter(candidates[0]["id"] for candidates in choices.values() if len(candidates) == 1)
        resolved = [(album, candidates[0]) for album, candidates in choices.items()
                    if len(candidates) == 1 and single_claims[candidates[0]["id"]] == 1]
        if not resolved:
            break
        for album, target in resolved:
            assigned[album] = target
            consumed.add(target["id"])
    for album, proof in album_evidence.items():
        title, known, complete = proof["title"], proof["known"], proof["complete"]
        expected_ids, exact = proof["expected_ids"], proof["exact"]
        if album in assigned:
            target = assigned[album]
            if target["albumName"] != title:
                findings.append({"kind": "album", "status": "difference", "evidence": "Album name difference", "path": album,
                                 "asset_ids": sorted(expected_ids), "album_ids": [target["id"]],
                                 "message": f"Asset membership matches an album named {target['albumName']!r}; source title is {title!r}."})
            continue
        if exact:
            message = "Matched album membership has no unique one-to-one destination identity. Several source albums may be competing for the same destination album, or several destination albums remain indistinguishable."
            status = "unresolved"
            candidates = exact
        else:
            candidates = [a for a in destination.get("albums", []) if a["albumName"] == title]
            status = "difference" if complete and not destination.get("issues") else "unresolved"
            if len(candidates) > 1:
                status = "unresolved"
                message = "Duplicate destination album names have no unique exact membership match."
            elif candidates:
                member_ids = set(candidates[0]["asset_ids"])
                absent = sum(not (member_ids & group) for group in known)
                extra = len(member_ids - expected_ids)
                message = f"Album membership differs: {absent} matched source content group(s) absent, {extra} additional destination asset(s)."
            else:
                message = "No destination album has the matched source membership or source title."
            if not complete:
                message += " Some source content is unresolved, so album coverage is incomplete."
        findings.append({"kind": "album", "status": status, "evidence": "Album difference" if status == "difference" else "Unresolved",
                         "path": album, "asset_ids": sorted(expected_ids), "album_ids": [a["id"] for a in candidates], "message": message})
    for issue in issues:
        findings.append({"kind": issue.get("kind", "coverage"), "status": "unresolved", "evidence": "Unresolved",
                         "path": issue.get("path", "Scan coverage"), "asset_ids": [], "message": issue.get("message", "Coverage issue")})
    for ident in untrusted:
        findings.append({"kind": "destination", "status": "unresolved", "evidence": "Unresolved", "path": "Destination asset",
                         "asset_ids": [ident], "message": verified.get(ident, {}).get("error") or
                         "Original not independently verified; checksum algorithm/provenance is unknown or unsupported."})
    counts = Counter(f["status"] for f in findings if f["kind"] == "content")
    matched = counts["original"] + counts["checksum"]
    attention = sum(f["status"] not in {"original", "checksum", "not_applicable"} for f in findings)
    inventory = manifest.get("inventory_summary", {})
    return {"schema_version": 3, "mode": mode, "immich_version": destination.get("version"),
            "coverage": {"capture_dates": capture_coverage, "container_dates": container_coverage,
                         "album_membership": {"asserted_occurrences": sum(bool(i.get("albums")) for i in manifest["items"]),
                                              "total": len(manifest["items"]),
                                              "policy": manifest.get("album_policy", "Only recognizable source album metadata asserts membership.")},
                         "paired_media": pair_coverage, "media_types": type_coverage},
            "scope": "Supplied extracted folder against API-key-readable active, non-locked assets, including readable shared albums. No server-wide completeness claim.",
            "summary": {"source_files": len(manifest["items"]), "source_bytes": manifest["total_bytes"],
                        **({"inventory_files": inventory["files"], "inventory_bytes": inventory["bytes"],
                            "media_files": inventory["media_files"], "auxiliary_files": inventory["auxiliary_files"],
                            "auxiliary_bytes": inventory["auxiliary_bytes"], "sidecar_files": inventory["sidecar_files"],
                            "album_metadata_files": inventory["album_metadata_files"]} if inventory else {}),
                        "unique_source_content": len({i["sha256"] for i in manifest["items"] if i.get("sha256")}),
                        "destination_assets": len(assets), "matched": matched, "attention": attention,
                        "content_counts": dict(counts), "coverage_complete": not issues and not untrusted and not any(
                            f["status"] in {"unresolved", "inaccessible", "unsupported", "ambiguous", "possible"} for f in findings),
                        "verification": LABELS[mode], "source_albums": len(source_albums),
                        "destination_albums": len(destination.get("albums", []))},
            "limitations": ["This verifies only the supplied export; it cannot prove Google exported everything.",
                             "Never use this report as permission to delete originals.",
                             "API visibility excludes locked media and items this key cannot access.",
                             "Re-enumeration detects observable changes, but Immich does not provide an atomic library snapshot.",
                             "Google Motion Photo pairing requires validated XMP layout, an embedded MP4 video track and matching component bytes. Other pairing formats and original camera timezone may remain unresolved.",
                             "Media types use supported container structure, not filename extensions. Container validation does not prove codec decoding or playback.",
                             "ISO BMFF creation fields are nominal container timestamps, not independently established shutter instants or original camera timezones.",
                             "An empty recognized shared-album comments JSON remains inventoried as auxiliary metadata; it does not require a destination media asset.",
                             "Server checksum matches are stored historical SHA-1 evidence, not current-byte verification."],
            "findings": findings}
