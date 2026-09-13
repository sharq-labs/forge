"""Domain real-data round: readiness screen of the measured files this round maps to claims.

    python -X utf8 benchmarks/domain_real_data/audit/quality_screen.py          # write DATA_QUALITY.json
    python -X utf8 benchmarks/domain_real_data/audit/quality_screen.py --check  # exit 1 if stale or a hash moved

This is a READINESS screen, not cleaning and not analysis. It opens each raw
file read-only, verifies its SHA-256 against DATASETS.json, and reports only:
rows, columns, units present, finite and missing values, exact duplicate rows,
duplicate or non-increasing time stamps, sampling intervals, value ranges, and
byte-level facts (CRLF, NUL bytes). It fits nothing, derives no resistance, no
capacity and no temperature coefficient, and it does not open any benchmark case.

Files screened:
  * the vendored LG HG2 25 degC cycler exports (this round), and
  * the B3 HysPowerTest files already in the repository, because this round maps
    them to loaded-voltage claims that B3 never used them for.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import math
import pathlib
import statistics
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
ROUND = ROOT / "benchmarks" / "domain_real_data"
OUT = ROUND / "DATA_QUALITY.json"


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _float(text: str) -> float | None:
    text = text.strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _hms_seconds(text: str) -> float | None:
    parts = text.strip().split(":")
    if len(parts) != 3:
        return None
    try:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    except ValueError:
        return None


def _range(values: list[float]) -> list[float] | None:
    return [min(values), max(values)] if values else None


def _intervals(times: list[float]) -> dict:
    steps = [b - a for a, b in zip(times, times[1:])]
    positive = [s for s in steps if s > 0]
    return {
        "non_increasing_steps": sum(1 for s in steps if s <= 0),
        "duplicate_time_stamps": sum(1 for s in steps if s == 0),
        "interval_s_min_median_max": (
            [round(min(positive), 6), round(statistics.median(positive), 6), round(max(positive), 6)] if positive else None
        ),
        "span_s": round(times[-1] - times[0], 6) if times else None,
    }


def screen_digatron_csv(path: pathlib.Path) -> dict:
    """Digatron Firing Circuits cycler export: key,value header block, a column row, a unit row, data rows."""
    raw = path.read_bytes()
    lines = raw.decode("latin-1").split("\r\n")
    header_idx = next(i for i, line in enumerate(lines) if line.startswith("Time Stamp,"))
    metadata = {}
    for line in lines[:header_idx]:
        if "," in line:
            key, _, value = line.partition(",")
            if key.strip():
                metadata[key.strip()] = value.strip()
    columns = [c for c in lines[header_idx].split(",") if c != ""]
    units = lines[header_idx + 1].split(",")[: len(columns)]
    numeric = {"Voltage", "Current", "Temperature", "Capacity", "WhAccu", "Cnt"}
    values: dict[str, list[float]] = {c: [] for c in columns if c in numeric}
    missing = collections.Counter()
    malformed = 0
    rows = []
    prog_times: list[float] = []
    status = collections.Counter()
    for line in lines[header_idx + 2:]:
        if not line.strip():
            continue
        cells = line.split(",")
        if len(cells) < len(columns):
            malformed += 1
            continue
        rows.append(tuple(cells[: len(columns)]))
        record = dict(zip(columns, cells))
        status[f'{record["Step"]}:{record["Status"]}:{record["Procedure"]}'] += 1
        seconds = _hms_seconds(record["Prog Time"])
        if seconds is None:
            missing["Prog Time"] += 1
        else:
            prog_times.append(seconds)
        for name in values:
            number = _float(record[name])
            if number is None:
                missing[name] += 1
            elif not math.isfinite(number):
                missing[name] += 1
            else:
                values[name].append(number)
    return {
        "format": "Digatron cycler CSV export",
        "bytes": len(raw),
        "crlf_line_endings": b"\r\n" in raw,
        "nul_bytes": raw.count(b"\x00"),
        "header_metadata": {k: metadata[k] for k in (
            "Measurement ID", "Battery Name", "Program", "Test section", "Start Time", "End Time",
            "Nominal Voltage", "Nominal Capacity", "Maximum Voltage", "Impedance", "Comment") if k in metadata},
        "columns": columns,
        "units_row": dict(zip(columns, units)),
        "units_present_for": sorted(c for c, u in zip(columns, units) if u.strip()),
        "rows": len(rows),
        "malformed_rows": malformed,
        "exact_duplicate_rows": len(rows) - len(set(rows)),
        "missing_or_non_finite": dict(sorted(missing.items())),
        "time_axis": {"column": "Prog Time", **_intervals(prog_times)},
        "ranges": {name: _range(v) for name, v in values.items()},
        "step_status_procedure_row_counts": dict(sorted(status.items(), key=lambda kv: (int(kv[0].split(":")[0]), kv[0]))),
    }


def screen_numeric_csv(path: pathlib.Path) -> dict:
    """Plain numeric CSV with one header row (the B3 HysPowerTest files: t, Q, I, U)."""
    raw = path.read_bytes()
    lines = [line for line in raw.decode("utf-8").splitlines() if line.strip()]
    columns = lines[0].split(",")
    values: dict[str, list[float]] = {c: [] for c in columns}
    missing = collections.Counter()
    rows = []
    for line in lines[1:]:
        cells = line.split(",")
        rows.append(tuple(cells))
        for name, cell in zip(columns, cells):
            number = _float(cell)
            if number is None or not math.isfinite(number):
                missing[name] += 1
            else:
                values[name].append(number)
    return {
        "format": "numeric CSV, one header row, no unit row",
        "bytes": len(raw),
        "crlf_line_endings": b"\r\n" in raw,
        "nul_bytes": raw.count(b"\x00"),
        "columns": columns,
        "units_present_for": [],
        "units_source": "not in the file; the Zenodo record description names [t Q I U] without units",
        "rows": len(rows),
        "exact_duplicate_rows": len(rows) - len(set(rows)),
        "missing_or_non_finite": dict(sorted(missing.items())),
        "time_axis": {"column": columns[0], **_intervals(values[columns[0]])},
        "ranges": {name: _range(v) for name, v in values.items()},
    }


SCREENS = (
    ("DS-BAT-LGHG2-25C", "benchmarks/domain_real_data/battery/lg_hg2_mcmaster/raw/549_HPPC.csv", screen_digatron_csv),
    ("DS-BAT-LGHG2-25C", "benchmarks/domain_real_data/battery/lg_hg2_mcmaster/raw/549_C20DisCh.csv", screen_digatron_csv),
    ("DS-BAT-LGHG2-25C", "benchmarks/domain_real_data/battery/lg_hg2_mcmaster/raw/549_Dis_0p5C.csv", screen_digatron_csv),
    ("DS-BAT-LGHG2-25C", "benchmarks/domain_real_data/battery/lg_hg2_mcmaster/raw/549_Dis_2C.csv", screen_digatron_csv),
    ("DS-BAT-LGHG2-25C", "benchmarks/domain_real_data/battery/lg_hg2_mcmaster/raw/551_Cap_1C.csv", screen_digatron_csv),
    ("DS-BAT-JAHN-A123", "benchmarks/battery_flagship_b3/evidence/raw/20230125_HysPowerTest_A123_01_25deg_SOC50.csv", screen_numeric_csv),
    ("DS-BAT-JAHN-A123", "benchmarks/battery_flagship_b3/evidence/raw/20230125_HysPowerTest_A123_01_25deg_SOC100.csv", screen_numeric_csv),
)


def pinned_hashes() -> dict[str, str]:
    registry = json.loads((ROUND / "DATASETS.json").read_text(encoding="utf-8"))
    pins = {}
    for dataset in registry["datasets"]:
        for entry in dataset.get("files_in_repository", []):
            pins[entry["path"]] = entry["sha256"]
    return pins


def screen() -> dict:
    pins = pinned_hashes()
    results = []
    for dataset_id, rel, function in SCREENS:
        path = ROOT / rel
        digest = sha256(path)
        results.append({
            "dataset_id": dataset_id,
            "path": rel,
            "sha256": digest,
            "sha256_matches_registry": pins.get(rel) == digest,
            "screen": function(path),
        })
    return {
        "schema": "domain_real_data_quality_screen/1",
        "scope": "readiness only: counts, ranges, finiteness, duplicates, time-axis monotonicity, byte facts; no fitting, no derived physical quantity",
        "all_hashes_match_registry": all(r["sha256_matches_registry"] for r in results),
        "files": results,
    }


def render(doc: dict) -> bytes:
    return (json.dumps(doc, indent=1, ensure_ascii=False) + "\n").encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    doc = screen()
    data = render(doc)
    if args.check:
        stale = not OUT.exists() or OUT.read_bytes() != data
        print("DATA_QUALITY.json", "STALE" if stale else "current", "hashes", "OK" if doc["all_hashes_match_registry"] else "MISMATCH")
        return 1 if stale or not doc["all_hashes_match_registry"] else 0
    OUT.write_bytes(data)
    print("hashes", "OK" if doc["all_hashes_match_registry"] else "MISMATCH")
    return 0 if doc["all_hashes_match_registry"] else 1


if __name__ == "__main__":
    sys.exit(main())
