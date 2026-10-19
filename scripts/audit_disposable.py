"""Read-only independent storage/database snapshot of this test harness's stack."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    owner = json.loads((args.owner_dir / "owner.json").read_text(encoding="utf-8"))
    project = owner["project"]
    if not re.fullmatch(r"pmc-test-[a-f0-9]{12}", project) or owner["port"] != 22839:
        raise SystemExit("Only a harness-owned disposable stack is accepted.")
    server, database = project + "-server-1", project + "-database-1"

    def command(argv, input=None):
        result = subprocess.run(argv, input=input, capture_output=True, check=True, timeout=120)
        return result.stdout

    for container in (server, database):
        label = command(["docker", "inspect", "--format", '{{index .Config.Labels "com.docker.compose.project"}}', container]).decode().strip()
        if label != project:
            raise SystemExit("Container ownership mismatch.")

    def sql(query):
        return command(["docker", "exec", database, "psql", "-U", "postgres", "-d", "immich", "-At", "-c", query])

    tables = {}
    # Media/album records, not auth usage or job-queue bookkeeping. Values are
    # hashed inside this process and never exported as raw server/GPS metadata.
    names = ["asset", "asset_exif", "asset_metadata", "asset_edit", "asset_file", "asset_video", "asset_audio",
             "album", "album_asset", "album_user", "asset_audit", "album_audit", "album_asset_audit"]
    for table in names:
        raw = sql(f'SELECT COALESCE(jsonb_agg(row_data ORDER BY row_data::text), \'[]\'::jsonb)::text FROM (SELECT to_jsonb(t) AS row_data FROM "{table}" t) rows')
        rows = json.loads(raw)
        canonical = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
        tables[table] = {"rows": len(rows), "sha256": hashlib.sha256(canonical).hexdigest()}
    paths = json.loads(sql('SELECT COALESCE(json_agg(json_build_object(\'id\',id,\'path\',"originalPath") ORDER BY id),\'[]\'::json) FROM asset'))
    node = '''const fs=require('node:fs'),crypto=require('node:crypto');let input='';
process.stdin.on('data',c=>input+=c);process.stdin.on('end',async()=>{try{let output=[];
for(const item of JSON.parse(input)){const hash=crypto.createHash('sha256');let size=0;
for await(const chunk of fs.createReadStream(item.path)){hash.update(chunk);size+=chunk.length;}
output.push({id:item.id,size,sha256:hash.digest('hex')});}
console.log(JSON.stringify(output));}catch(e){console.error('Original storage audit failed');process.exitCode=1;}});'''
    originals = json.loads(command(["docker", "exec", "-i", server, "node", "-e", node], json.dumps(paths).encode()))
    image = command(["docker", "inspect", "--format", '{{.Config.Image}}', server]).decode().strip()
    snapshot = {"test_kind": "Independent read-only container storage and database audit", "immich_image": image,
                "tables": tables, "originals": originals, "original_bytes": sum(x["size"] for x in originals)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"originals": len(originals), "original_bytes": snapshot["original_bytes"], "media_album_tables": len(tables)}))


if __name__ == "__main__":
    main()
