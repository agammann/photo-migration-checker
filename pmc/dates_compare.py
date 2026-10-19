"""Keep asserted Takeout capture instants separate from encoded container dates."""
from __future__ import annotations

from datetime import datetime
from math import isfinite


def _timestamp(value):
    try:
        return isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value)
    except OverflowError:
        return False


def epoch(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.timestamp() if parsed.tzinfo else None
    except (ValueError, TypeError, AttributeError, OverflowError, OSError):
        return None


def date_findings(manifest, matches, asset_map, mode):
    findings = []
    capture_coverage = {"comparable": 0, "total": len(manifest["items"]), "asserted": 0,
                        "agreements": 0, "differences": 0, "unresolved": 0, "container_only": 0}
    container_coverage = {"total": 0, "comparable": 0, "agreements": 0, "differences": 0, "unresolved": 0, "unmatched": 0,
                          "policy": "Literal ISO BMFF creation timestamps are compared as nominal UTC. They do not establish shutter instants or the originating camera timezone."}
    for item in manifest["items"]:
        capture = item.get("capture") or {}
        timestamp = capture.get("timestamp")
        asserted = _timestamp(timestamp)
        capture_coverage["asserted"] += asserted
        path = item["path"]
        media = item.get("media") or {}
        container = media.get("container_creation") or {}
        # A malformed, ambiguous or conflicting sidecar must never be bypassed
        # by a lower-priority timestamp. Only a sidecar-free video can fall back.
        use_container = (not capture and not item.get("sidecars") and not item.get("issues")
                         and media.get("valid") is True and media.get("complete") is True
                         and media.get("family") == "video" and media.get("container") in {"mp4", "quicktime"}
                         and container.get("valid") is True and container.get("complete") is True
                         and container.get("source") == "iso_bmff.creation_time"
                         and _timestamp(container.get("timestamp")))
        if use_container:
            container_coverage["total"] += 1
            capture_coverage["container_only"] += 1
        if path not in matches:
            container_coverage["unmatched"] += bool(use_container)
            continue
        ids = matches[path]
        dates = {ident: asset_map[ident].get("fileCreatedAt") for ident in ids}
        parsed = {ident: epoch(value) for ident, value in dates.items()}
        finding = {"kind": "metadata", "path": path, "asset_ids": ids, "destination_dates": dates}
        if asserted or use_container:
            container_only = not asserted
            evidence = container if container_only else capture
            timestamp = evidence["timestamp"]
            coverage = container_coverage if container_only else capture_coverage
            finding.update(date_kind="container_creation" if container_only else "capture_instant",
                           source_date=evidence.get("datetime_utc"),
                           source_date_provenance={
                               "method": "iso_bmff.creation_time" if container_only else "takeout.photoTakenTime",
                               "semantics": "container_creation" if container_only else "capture_instant",
                               "timezone": "nominal_utc" if container_only else "utc",
                               "capture_instant_verified": not container_only,
                               "source_paths": [path] if container_only else item.get("sidecars", []),
                               **({"fields": container.get("fields", [])} if container_only else {})})
            comparable = any(value is not None for value in parsed.values())
            coverage["comparable"] += comparable
            agreeing = sorted(ident for ident, value in parsed.items() if value is not None and abs(value - timestamp) <= 1)
            finding["agreeing_asset_ids"] = agreeing
            if agreeing:
                coverage["agreements"] += 1
                finding.update(status=mode,
                    evidence="Container creation timestamp agrees" if container_only else "Capture date agrees",
                    message=("The literal encoded container creation timestamp agrees with Immich fileCreatedAt within one second. This does not establish a shutter instant or the originating camera timezone."
                             if container_only else "Immich fileCreatedAt agrees with the asserted Takeout photoTakenTime instant within one second. Filesystem dates were not used."))
            elif comparable:
                coverage["differences"] += 1
                finding.update(status="difference", evidence="Container date difference" if container_only else "Metadata difference",
                    message=("Immich fileCreatedAt differs from the literal encoded container creation timestamp. Container creation does not establish a shutter instant or the originating camera timezone."
                             if container_only else "Capture instant differs from Takeout photoTakenTime. Filesystem dates were not used."))
            else:
                coverage["unresolved"] += 1
                finding.update(status="unresolved", evidence="Date comparison unavailable",
                               message="Destination fileCreatedAt has no comparable timezone-aware instant.")
        else:
            capture_coverage["unresolved"] += 1
            finding.update(status="unresolved", date_kind="unresolved",
                           evidence="Timezone uncertain" if capture else "Date evidence unavailable",
                           message="No trustworthy source capture instant is available, and no eligible independent container date can be compared. Filename dates, filesystem dates, neighbouring photos and uncertain timezone conversions were not used.")
            if container:
                finding["container_date_issues"] = container.get("issues", [])
        findings.append(finding)
    return findings, capture_coverage, container_coverage
