"""Domain real-data round: readiness screen of EXTERNAL_FETCH_REQUIRED evidence that is not vendored.

    python -X utf8 benchmarks/domain_real_data/audit/acquire.py fetch --dest DIR
    python -X utf8 benchmarks/domain_real_data/audit/external_screen.py --dir DIR   # writes EXTERNAL_SCREEN.json

These files are not in the repository -- their licences do not clearly permit
redistribution (see DATASETS.json) -- so their screen is recorded as a result
over a copy identified by its checksum, and is reproducible only by fetching.
The same readiness rules as quality_screen.py apply: counts, finiteness,
duplicates, ranges. Nothing is fitted and no physical quantity is derived.

The NASA report is a PDF. Its Appendix C tables are read through ``pdftotext
-layout`` (poppler); the screen counts table rows that parse as numbers. It
does not transcribe the tables into the repository.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
ROUND = ROOT / "benchmarks" / "domain_real_data"
OUT = ROUND / "EXTERNAL_SCREEN.json"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def screen_shunt(path: pathlib.Path) -> dict:
    import numpy as np
    import scipy.io as sio

    data = path.read_bytes()
    mat = sio.loadmat(path, squeeze_me=True, struct_as_record=False)
    tcr = mat["TemperatureCoefficientResistor"]
    static = mat["StaticCalibrationMeasurement"]
    temps = np.atleast_1d(tcr.ambientTemperature).astype(float)
    res = np.atleast_1d(tcr.resistance).astype(float)
    structs = sorted(k for k in mat if not k.startswith("__"))
    return {
        "md5": hashlib.md5(data).hexdigest(),
        "sha256": sha256(data),
        "structs": structs,
        "TemperatureCoefficientResistor": {
            "description_in_file": str(tcr.description),
            "points": int(temps.size),
            "all_finite": bool(np.isfinite(temps).all() and np.isfinite(res).all()),
            "ambient_temperature_range": [float(temps.min()), float(temps.max())],
            "ambient_temperature_unit": "UNKNOWN in the file; values span 20-89 and the static struct names 20 degC / 30 degC",
            "resistance_range": [float(res.min()), float(res.max())],
            "resistance_unit": "UNKNOWN in the file; the description says a 10 mOhm shunt",
            "closest_temperature_pair_gap": float(np.min(np.diff(np.sort(temps)))),
            "uncertainty_in_file": "none",
        },
        "StaticCalibrationMeasurement": {
            "fields": list(static._fieldnames),
            "points_20C": int(np.atleast_1d(static.referenceCurrent_T20C).size),
            "points_30C": int(np.atleast_1d(static.referenceCurrent_T30C).size),
            "heatsink_temperature_points_20C": int(np.atleast_1d(static.steadyStateHeatsinkTemperature_T20C).size),
            "reference_current_range_A_20C": [float(np.min(static.referenceCurrent_T20C)), float(np.max(static.referenceCurrent_T20C))],
            "note": "20 degC current points (21) outnumber heat-sink temperature points (6); the pairing is not stated in the file",
        },
        "time_series": {
            name: {
                "samples": int(np.atleast_1d(getattr(mat[name], "time")).size),
                "dt_first_s": float(np.diff(np.atleast_1d(mat[name].time)[:2])[0]),
                "all_finite": bool(np.isfinite(mat[name].referenceCurrent).all()),
            }
            for name in ("ProfileMeasurement", "PulseMeasurement")
        },
    }


TABLE = re.compile(r"Table (C\d+[a-c])\. (Full Vehicle|Isolated Rotor): ([^,]+), hover, (.*)$")
ROW = re.compile(r"^\s*(\d+)\s+(\d+)\s+((?:-?\d+\.\d+|\d+)(?:\s+(?:-?\d+\.\d+|\d+))+)\s*$")


def screen_nasa(path: pathlib.Path) -> dict:
    data = path.read_bytes()
    text = subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True, check=True).stdout.decode("utf-8", "replace")
    tables: dict[str, dict] = {}
    current = None
    for line in text.splitlines():
        match = TABLE.search(line)
        if match:
            key = match.group(1)
            current = key
            tables[key] = {"configuration": match.group(2), "vehicle": match.group(3).strip(), "title_tail": match.group(4).strip(), "rows": 0, "widths": set(), "non_finite": 0}
            continue
        if line.lstrip().startswith("Table "):
            current = None
            continue
        if current and (row := ROW.match(line)):
            values = row.group(3).split()
            tables[current]["rows"] += 1
            tables[current]["widths"].add(len(values) + 2)
            tables[current]["non_finite"] += sum(1 for v in values if not math.isfinite(float(v)))
    hover = {}
    for key, t in sorted(tables.items(), key=lambda kv: (int(re.sub(r"\D", "", kv[0])), kv[0])):
        hover[key] = {**{k: v for k, v in t.items() if k != "widths"}, "column_counts_seen": sorted(t["widths"])}
    return {
        "sha256": sha256(data),
        "extraction": "pdftotext -layout; rows = lines of '<run> <point> <numbers...>' inside an Appendix C hover table",
        "hover_tables": hover,
        "hover_tables_with_rows": sum(1 for t in hover.values() if t["rows"]),
        "hover_rows_total": sum(t["rows"] for t in hover.values()),
        "note": "column_counts_seen > 1 value means pdftotext split or merged a column on some line; a transcription must be checked against the PDF page, not trusted from text extraction",
    }


def screen_uiuc(root: pathlib.Path) -> dict:
    manifest = json.loads((ROUND / "aerospace" / "uiuc_propeller_database" / "STATIC_MANIFEST.json").read_text(encoding="utf-8"))
    files = rows = non_finite = headers_repeated = changed = 0
    rpm = []
    for entry in manifest["files"]:
        path = root / entry["path"]
        if not path.exists():
            continue
        body = path.read_bytes()
        files += 1
        changed += sha256(body) != entry["sha256_of_copy_retrieved"]
        lines = [line.split() for line in body.decode("latin-1").splitlines() if line.strip()]
        headers_repeated += sum(1 for line in lines[1:] if line and line[0] == "RPM")
        for line in lines:
            if line[0] == "RPM":
                continue
            rows += 1
            numbers = [float(v) for v in line]
            non_finite += sum(1 for v in numbers if not math.isfinite(v))
            rpm.append(numbers[0])
    return {
        "files_present": files,
        "files_in_manifest": manifest["file_count"],
        "files_changed_upstream": changed,
        "data_rows": rows,
        "non_finite_values": non_finite,
        "files_with_a_repeated_header_line": headers_repeated,
        "rpm_range": [min(rpm), max(rpm)] if rpm else None,
        "columns": "RPM CT CP (dimensionless coefficients); no uncertainty, no air density, no motor electrical data in the files",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", type=pathlib.Path, required=True)
    args = parser.parse_args()
    doc = {
        "schema": "domain_real_data_external_screen/1",
        "scope": "readiness only, over copies fetched by acquire.py fetch; not vendored",
        "wesskamp_melbert_shunt": screen_shunt(args.dir / "JSSS-2016-48-DataSet.mat"),
        "nasa_tm_2018_219758": screen_nasa(args.dir / "Russell_1180_Final_TM_022218.pdf"),
        "uiuc_propeller_database_static": screen_uiuc(args.dir / "uiuc"),
    }
    OUT.write_bytes((json.dumps(doc, indent=1, ensure_ascii=False) + "\n").encode("utf-8"))
    print("wrote", OUT.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
