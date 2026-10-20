"""Domain real-data round: acquisition manifests and re-fetch instructions for external evidence.

    python -X utf8 benchmarks/domain_real_data/audit/acquire.py manifests        # (network) rebuild the *_MANIFEST.json files
    python -X utf8 benchmarks/domain_real_data/audit/acquire.py fetch --dest DIR # (network) fetch EXTERNAL_FETCH_REQUIRED files into DIR and verify

Nothing here runs in the test suite: it needs the network, and the tests must
not. The manifests it writes are METADATA ONLY -- filenames, sizes, checksums,
persistent identifiers, download endpoints -- never dataset content. That is
what lets a dataset whose licence does not clearly permit redistribution be
recorded here without being vendored.

Checksums:
  * Mendeley Data publishes SHA-256 per file in its public API; recorded as published.
  * Zenodo publishes MD5 per file; recorded as published, and the SHA-256 of the copy
    this round retrieved is recorded beside it where a copy was retrieved.
  * The UIUC propeller site and the NASA report publish no checksum; the SHA-256 of
    the copy retrieved on RETRIEVED_ON is recorded and labelled as such. A later
    mismatch means the upstream bytes changed, not that this record is wrong.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[3]
ROUND = ROOT / "benchmarks" / "domain_real_data"
RETRIEVED_ON = "2026-09-13"

MENDELEY = {
    "cp3473x7xv": ROUND / "battery" / "lg_hg2_mcmaster" / "MENDELEY_MANIFEST.json",
    "wykht8y7tg": ROUND / "battery" / "panasonic_18650pf_wisconsin" / "MENDELEY_MANIFEST.json",
}
ZENODO = {
    "11958572": ROUND / "battery" / "jahn_a123_bayreuth" / "ZENODO_MANIFEST.json",
    "164820": ROUND / "electrical" / "wesskamp_melbert_shunt" / "ZENODO_MANIFEST.json",
    "4881855": ROUND / "kinetics" / "sciexpem_jsr_dagaut_2010" / "ZENODO_MANIFEST.json",
}
UIUC_BASE = "https://m-selig.ae.illinois.edu/props/"
UIUC_MANIFEST = ROUND / "aerospace" / "uiuc_propeller_database" / "STATIC_MANIFEST.json"
NASA_URL = "https://rotorcraft.arc.nasa.gov/Publications/files/Russell_1180_Final_TM_022218.pdf"
NASA_MANIFEST = ROUND / "aerospace" / "nasa_tm_2018_219758" / "RETRIEVAL_MANIFEST.json"

TEMPERATURE_TOKEN = re.compile(r"(?:^|[ _])(n?\d+degC)(?:_|$)")


def curl(url: str) -> bytes:
    return subprocess.run(["curl", "-s", "-L", "-m", "300", url], capture_output=True, check=True).stdout


def write_json(path: pathlib.Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(doc, indent=1, ensure_ascii=False) + "\n").encode("utf-8"))


def mendeley_manifest(dataset_id: str) -> dict:
    record = json.loads(curl(f"https://data.mendeley.com/public-api/datasets/{dataset_id}"))
    files = record["files"]
    # A folder's ambient temperature is read from the temperature token in the names of
    # the .mat files that share its folder id ("..._25degC_LGHG2.mat"). The API returns
    # folder ids without names. A folder whose .mat names carry no single token is UNKNOWN.
    tokens: dict[str, set[str]] = {}
    for f in files:
        if f["filename"].endswith(".mat") and f.get("folder_id"):
            match = TEMPERATURE_TOKEN.search(f["filename"].rsplit(".", 1)[0])
            if match:
                tokens.setdefault(f["folder_id"], set()).add(match.group(1))
    rows = []
    for f in files:
        folder = f.get("folder_id")
        token = tokens.get(folder, set())
        rows.append({
            "filename": f["filename"],
            "folder_id": folder,
            "folder_ambient_temperature_label": next(iter(token)) if len(token) == 1 else "UNKNOWN",
            "bytes": f["content_details"]["size"],
            "sha256_published_by_mendeley": f["content_details"]["sha256_hash"],
            "file_id": f["id"],
        })
    rows.sort(key=lambda r: (r["folder_ambient_temperature_label"], r["filename"]))
    return {
        "schema": "domain_real_data_mendeley_manifest/1",
        "dataset_id": dataset_id,
        "doi": record["doi"]["id"],
        "title": record["name"],
        "licence": record["data_licence"]["short_name"],
        "licence_url": record["data_licence"]["url"],
        "institutions": [i["name"] for i in record.get("institutions", [])],
        "contributors": [f'{c.get("first_name", "").strip()} {c.get("last_name", "").strip()}'.strip() for c in record.get("contributors", [])],
        "publish_date": record.get("publish_date"),
        "retrieved_on": RETRIEVED_ON,
        "download_endpoint": "https://data.mendeley.com/public-files/datasets/{dataset_id}/files/{file_id}/file_downloaded",
        "temperature_label_rule": "token like 25degC / n10degC in the names of .mat files sharing the folder id; UNKNOWN when absent or ambiguous",
        "file_count": len(rows),
        "total_bytes": sum(r["bytes"] for r in rows),
        "files": rows,
    }


def zenodo_manifest(record_id: str) -> dict:
    record = json.loads(curl(f"https://zenodo.org/api/records/{record_id}"))
    meta = record["metadata"]
    return {
        "schema": "domain_real_data_zenodo_manifest/1",
        "record_id": record_id,
        "doi": meta.get("doi"),
        "title": meta.get("title"),
        "licence": (meta.get("license") or {}).get("id", "UNKNOWN"),
        "creators": [{"name": c.get("name"), "affiliation": c.get("affiliation") or "UNKNOWN"} for c in meta.get("creators", [])],
        "publication_date": meta.get("publication_date"),
        "retrieved_on": RETRIEVED_ON,
        "files": sorted(
            ({"filename": f["key"], "bytes": f["size"], "checksum_published_by_zenodo": f["checksum"],
              "download_url": f"https://zenodo.org/records/{record_id}/files/{f['key']}?download=1"} for f in record["files"]),
            key=lambda r: r["filename"]),
    }


def uiuc_manifest() -> dict:
    rows = []
    for volume in (1, 2, 3, 4):
        page = curl(f"{UIUC_BASE}volume-{volume}/propDB-volume-{volume}.html").decode("latin-1")
        for rel in sorted(set(re.findall(r'data/[^"]*static[^"]*\.txt', page))):
            body = curl(f"{UIUC_BASE}volume-{volume}/{rel}")
            rows.append({
                "path": f"volume-{volume}/{rel}",
                "bytes": len(body),
                "sha256_of_copy_retrieved": hashlib.sha256(body).hexdigest(),
            })
    return {
        "schema": "domain_real_data_uiuc_static_manifest/1",
        "source": "UIUC Propeller Data Site, https://m-selig.ae.illinois.edu/props/propDB.html (Vols 1-4)",
        "retrieved_on": RETRIEVED_ON,
        "checksum_note": "the site publishes no checksums; these are SHA-256 of the copies retrieved on retrieved_on",
        "selection": "every file linked from a volume page whose name contains 'static' (static thrust/power coefficient tests)",
        "file_count": len(rows),
        "files": rows,
    }


def nasa_manifest() -> dict:
    body = curl(NASA_URL)
    return {
        "schema": "domain_real_data_retrieval_manifest/1",
        "url": NASA_URL,
        "retrieved_on": RETRIEVED_ON,
        "bytes": len(body),
        "sha256_of_copy_retrieved": hashlib.sha256(body).hexdigest(),
        "checksum_note": "NASA publishes no checksum for this PDF",
    }


def cmd_manifests() -> int:
    for dataset_id, path in MENDELEY.items():
        write_json(path, mendeley_manifest(dataset_id))
        print("wrote", path.relative_to(ROOT))
    for record_id, path in ZENODO.items():
        write_json(path, zenodo_manifest(record_id))
        print("wrote", path.relative_to(ROOT))
    write_json(UIUC_MANIFEST, uiuc_manifest())
    print("wrote", UIUC_MANIFEST.relative_to(ROOT))
    write_json(NASA_MANIFEST, nasa_manifest())
    print("wrote", NASA_MANIFEST.relative_to(ROOT))
    return 0


def cmd_fetch(dest: pathlib.Path) -> int:
    """Fetch the EXTERNAL_FETCH_REQUIRED evidence and verify it against the committed manifests."""
    failures = 0
    dest.mkdir(parents=True, exist_ok=True)

    shunt = json.loads((ZENODO["164820"]).read_text(encoding="utf-8"))
    for f in shunt["files"]:
        body = curl(f["download_url"])
        ok = "md5:" + hashlib.md5(body).hexdigest() == f["checksum_published_by_zenodo"]
        (dest / f["filename"]).write_bytes(body)
        print(f["filename"], "MD5_OK" if ok else "MD5_MISMATCH")
        failures += not ok

    nasa = json.loads(NASA_MANIFEST.read_text(encoding="utf-8"))
    body = curl(nasa["url"])
    ok = hashlib.sha256(body).hexdigest() == nasa["sha256_of_copy_retrieved"]
    (dest / "Russell_1180_Final_TM_022218.pdf").write_bytes(body)
    print("NASA TM", "SHA256_OK" if ok else "SHA256_CHANGED_UPSTREAM")
    failures += not ok

    uiuc = json.loads(UIUC_MANIFEST.read_text(encoding="utf-8"))
    changed = 0
    for f in uiuc["files"]:
        body = curl(UIUC_BASE + f["path"])
        target = dest / "uiuc" / f["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)
        changed += hashlib.sha256(body).hexdigest() != f["sha256_of_copy_retrieved"]
    print("UIUC static files", len(uiuc["files"]), "changed upstream:", changed)
    failures += changed
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("manifests")
    fetch = sub.add_parser("fetch")
    fetch.add_argument("--dest", type=pathlib.Path, default=pathlib.Path(tempfile.gettempdir()) / "domain_real_data_external")
    args = parser.parse_args()
    if args.command == "manifests":
        return cmd_manifests()
    return cmd_fetch(args.dest)


if __name__ == "__main__":
    sys.exit(main())
