"""Extract the v3 raw members from the local Kirkaldy 2024 archives (evaluator side; no fit, no model comparison).

    python -m benchmarks.battery_rediscovery_v3.extract [--verify-archives]

Writes the selected 25-pulse GITT members into ``D:/forge-data/kirkaldy2024/v3_rpt/`` (outside the repository) and
``EvaluatorVault/EXTRACT_MANIFEST.json`` with, per member, the archive, the member path, the zip CRC-32 and the sha256 of
the extracted bytes.  ``--verify-archives`` also recomputes each archive's md5 and compares it with the md5 Zenodo
publishes for record 10637534 (``record.json``), which takes a few minutes for ~22 GB.

The selection is structural and was fixed before any member was read: the experiments whose cells no FORGE 1RC study has
used (Expt 4 and Expt 5, cells A, B, C, F, G, H; cells D and E were used by the cross-cell 1RC study), the beginning-of-life
RPT (RPT0) and the latest RPT at which every one of those cells has a 25-pulse GITT file (Expt 4: RPT8, Expt 5: RPT14).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import zipfile

from benchmarks.battery_rediscovery_v2.candidate.common import write_json

from .data_root import FORGE_DATA_ROOT

HERE = pathlib.Path(__file__).resolve().parent
VAULT = HERE / "EvaluatorVault"
KIRKALDY = FORGE_DATA_ROOT / "kirkaldy2024"
OUT = KIRKALDY / "v3_rpt"
ARCHIVES = {4: "Expt 4 - Drive Cycle Aging (Control).zip", 5: "Expt 5 - Standard Cycle Aging (Control).zip"}
CELLS = ("A", "B", "C", "F", "G", "H")
RPTS = {4: (0, 8), 5: (0, 14)}
ZENODO_RECORD = "10637534"


def member_name(expt: int, cell: str, rpt: int) -> str:
    return f"Expt {expt} - cell {cell} - RPT{rpt} - 25-pulse GITT 0.5C discharge data.csv"


def selection() -> list[tuple[int, str, int]]:
    return [(e, c, r) for e in sorted(ARCHIVES) for c in CELLS for r in RPTS[e]]


def _md5(path: pathlib.Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 24), b""):
            h.update(chunk)
    return h.hexdigest()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify-archives", action="store_true")
    a = ap.parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)
    record = json.loads((KIRKALDY / "record.json").read_bytes())
    published = {f["key"]: f["checksum"].split(":", 1)[1] for f in record["files"]}
    manifest: dict = {"schema": "forge.battery_rediscovery_v3.extract_manifest/1", "zenodo_record": ZENODO_RECORD,
                      "archives": {}, "members": {}}
    for expt, name in sorted(ARCHIVES.items()):
        path = KIRKALDY / "raw" / name
        entry = {"file": name, "bytes": path.stat().st_size, "zenodo_md5": published[name]}
        if a.verify_archives:
            entry["md5"] = _md5(path)
            entry["md5_matches_zenodo"] = entry["md5"] == published[name]
            if not entry["md5_matches_zenodo"]:
                raise SystemExit(f"{name}: md5 does not match the Zenodo record")
        manifest["archives"][str(expt)] = entry
    for expt, cell, rpt in selection():
        target = member_name(expt, cell, rpt)
        with zipfile.ZipFile(KIRKALDY / "raw" / ARCHIVES[expt]) as z:
            hits = [n for n in z.namelist() if n.rsplit("/", 1)[-1] == target]
            if len(hits) != 1:
                raise SystemExit(f"{target}: {len(hits)} members match (refused)")
            raw = z.read(hits[0])  # zipfile checks the CRC-32 on read
            crc = z.getinfo(hits[0]).CRC
        dest = OUT / target
        if not dest.exists() or dest.read_bytes() != raw:
            dest.write_bytes(raw)
        manifest["members"][target] = {"archive": ARCHIVES[expt], "member": hits[0], "crc32": f"{crc:08x}",
                                       "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw),
                                       "expt": expt, "cell": cell, "rpt": rpt}
        print(target, len(raw))
    write_json(VAULT / "EXTRACT_MANIFEST.json", manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
