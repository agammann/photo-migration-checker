"""Offline reports containing only explicit, escaped evidence fields."""
import html
import json


def export_json(report: dict) -> bytes:
    return json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8")


def export_html(report: dict) -> bytes:
    e = lambda x: html.escape(str(x), quote=True)
    summary = report["summary"]
    coverage = report.get("coverage", {})
    dates = coverage.get("capture_dates", {})
    container_dates = coverage.get("container_dates", {})
    albums = coverage.get("album_membership", {})
    pairs = coverage.get("paired_media", {})
    media = coverage.get("media_types", {})
    rows = []
    for f in report["findings"]:
        details = {k: v for k, v in f.items() if k not in {"path", "evidence", "message", "status", "kind", "asset_ids"}}
        rows.append(f'<tr><td>{e(f["path"])}</td><td>{e(f["evidence"])}</td><td>{e(", ".join(f.get("asset_ids", [])))}</td>'
                    f'<td>{e(f["message"])}<details><summary>Evidence</summary><pre>{e(json.dumps(details, ensure_ascii=False, indent=2))}</pre></details></td></tr>')
    document = f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src 'none'; base-uri 'none'; form-action 'none'">
<title>Photo Migration Checker — local report</title><style>
body{{font:16px/1.5 system-ui,sans-serif;color:#182620;background:#fff;max-width:1300px;margin:48px auto;padding:0 24px}}
h1{{font-size:32px}} .notice{{padding:18px;background:#fff3d9;border:1px solid #e8c788}} table{{border-collapse:collapse;width:100%;font-size:14px}}
td,th{{text-align:left;vertical-align:top;border-bottom:1px solid #dce2df;padding:12px;overflow-wrap:anywhere}}th{{background:#f5f7f6}}
pre{{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}} .stats{{display:flex;gap:40px;flex-wrap:wrap;margin:24px 0}} footer{{margin:32px 0;color:#52645a}}
</style><h1>Photo Migration Checker</h1>
<p>Independent read-only verification report. {e(report.get("created_at", ""))}</p>
<p class="notice">{"Deterministic sample fixture. This is not a real Immich validation. " if report.get("demo") else ""}
Coverage: {"inventory completed within the stated scope" if summary["coverage_complete"] else "incomplete — unresolved evidence remains"}. This verifies only the supplied export. Keep your originals.</p>
<div class="stats"><span>Source files: <strong>{summary["source_files"]}</strong></span><span>Content matched: <strong>{summary["matched"]}</strong></span>
<span>Attention findings: <strong>{summary["attention"]}</strong></span><span>Level: <strong>{e(summary["verification"])}</strong></span></div>
<p>{e(report["scope"])}</p><p>Immich version: {e(report.get("immich_version"))}. Source timezone conversion is never guessed.</p>
<p>Comparable capture dates: {e(dates.get("comparable", "unknown"))} / {e(dates.get("total", "unknown"))}.
Capture agreements: {e(dates.get("agreements", "unknown"))}; capture differences: {e(dates.get("differences", "unknown"))}.
Comparable nominal container creation dates: {e(container_dates.get("comparable", 0))} / {e(container_dates.get("total", 0))};
container agreements: {e(container_dates.get("agreements", 0))}.
Container creation dates do not establish shutter instants or original camera timezones.
Source occurrences with asserted album membership: {e(albums.get("asserted_occurrences", "unknown"))} / {e(albums.get("total", "unknown"))}.
{e(albums.get("policy", ""))}</p>
<p>Source inventory: {e(summary.get("inventory_files", "unknown"))} files, {e(summary.get("inventory_bytes", "unknown"))} bytes;
{e(summary.get("media_files", "unknown"))} media files, {e(summary.get("sidecar_files", "unknown"))} sidecars,
{e(summary.get("album_metadata_files", "unknown"))} album metadata files and {e(summary.get("auxiliary_files", 0))} auxiliary files.
Recognized empty auxiliary metadata is retained with its hashes and a neutral status; no destination media asset is expected.</p>
<p>Paired media: {e(pairs.get("original_verified", 0))} verified original relationships,
{e(pairs.get("checksum_supported", 0))} stored checksum relationships,
{e(pairs.get("differences", 0))} differences, {e(pairs.get("unresolved", 0))} unresolved.
Media types: {e(media.get("agreements", 0))} agree, {e(media.get("differences", 0))} differ,
{e(media.get("unresolved", 0))} unresolved, {e(media.get("unmatched", 0))} unmatched source occurrences.</p>
<table><thead><tr><th>Source file / scope</th><th>Evidence</th><th>Destination asset IDs</th><th>Explanation</th></tr></thead><tbody>{"".join(rows)}</tbody></table>
<footer><ul>{"".join(f"<li>{e(x)}</li>" for x in report["limitations"])}</ul>
Report contains relative file paths, album names, asset IDs, dates and content hashes. Treat it as sensitive.</footer></html>'''
    return document.encode("utf-8")
