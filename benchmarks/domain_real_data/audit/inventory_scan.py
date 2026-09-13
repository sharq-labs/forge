"""Domain real-data round: classify every data-bearing file in the repository.

    python -X utf8 benchmarks/domain_real_data/audit/inventory_scan.py          # write REPOSITORY_SCAN.json
    python -X utf8 benchmarks/domain_real_data/audit/inventory_scan.py --check  # exit 1 if the file is stale
    python -X utf8 benchmarks/domain_real_data/audit/inventory_scan.py --include-untracked --check

The scan walks ``git ls-files`` (tracked and staged files) rather than
searching by domain name, so a measured file sitting under an unexpected path
cannot be missed. Every data-bearing file must match exactly one rule below. A
file that matches none is reported as UNKNOWN_PROVENANCE and the scan exits
non-zero: an inventory that silently skips a file is not an inventory.

The classes are the round's five:

    REAL_MEASURED       bytes recorded by an instrument in a documented experiment
    SYNTHETIC           generated: analytic truth, simulator output, injected noise, hand-built cases
    DERIVED             computed by this repository from other data (results, reports, manifests, reductions)
    REFERENCE_ONLY      published reference relations or constants, not a specimen measurement
    UNKNOWN_PROVENANCE  nothing establishes where it came from

A rule's class is a statement about the file's ORIGIN. It never says the file is
useful; claim mapping lives in DATASETS.json.
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
OUT = ROOT / "benchmarks" / "domain_real_data" / "REPOSITORY_SCAN.json"

DATA_SUFFIXES = (
    ".csv", ".tsv", ".xlsx", ".xls", ".xlsm", ".json", ".jsonl", ".parquet", ".feather",
    ".h5", ".hdf5", ".mat", ".npz", ".npy", ".dat", ".txt", ".log", ".h",
)

# Files that are data in all but extension: vendored third-party copies.
EXTRA_DATA_FILES = ("benchmarks/empirical_validation/evidence/scipy_codata.py",)

# Not data: packaging and dependency manifests.
NOT_DATA = ("requirements.txt",)

# (prefix, class, role, rationale). First match wins, so specific prefixes come first.
RULES = (
    ("benchmarks/domain_real_data/battery/lg_hg2_mcmaster/raw/Readme file", "REAL_MEASURED", "DATASET_DOCUMENTATION",
     "The published record's own readme, vendored beside its raw files: documentation of the measured dataset, not a measurement channel"),
    ("benchmarks/domain_real_data/battery/lg_hg2_mcmaster/raw/", "REAL_MEASURED", "DATASET",
     "Vendored bytes of Mendeley Data 10.17632/cp3473x7xv.3 (McMaster, Digatron cycler), SHA-256 equal to the repository's published hash; see battery/lg_hg2_mcmaster/PROVENANCE.json"),
    ("benchmarks/domain_real_data/", "DERIVED", "INVENTORY_ARTIFACT",
     "Written by this round: registry, manifests, provenance records, screens and reports"),
    ("benchmarks/battery_flagship_b3/evidence/raw/", "REAL_MEASURED", "DATASET",
     "Vendored bytes of Zenodo 10.5281/zenodo.10852930 (Univ. Bayreuth, BaSyTec CTS), MD5 equal to Zenodo's; see battery_flagship_b3/evidence/PROVENANCE.json"),
    ("benchmarks/battery_flagship_b3/evidence/PROVENANCE.json", "DERIVED", "PROVENANCE_RECORD",
     "Provenance metadata for the B3 raw files"),
    ("benchmarks/model_measurement_validation/evidence/ocv_relaxation_24h.xlsx", "REAL_MEASURED", "DATASET",
     "IEEE DataPort 10.21227/651q-8v82 via a CC BY 4.0 mirror; 24 h OCV relaxation at 1 min, NI USB-6251; see model_measurement_validation/EVIDENCE_PROVENANCE.json S-OCV"),
    ("benchmarks/model_measurement_validation/evidence/discharge_curves_1min.json", "DERIVED", "REDUCTION_OF_MEASURED",
     "Every 60th sample of the measured IEEE DataPort 10.21227/cm0f-jg66 workbook; the upstream file is REAL_MEASURED, this reduction is not the raw bytes (S-DCHG)"),
    ("benchmarks/model_measurement_validation/evidence/pt100rtd_table.h", "REFERENCE_ONLY", "REFERENCE_TABLE",
     "Third-party transcription of the DIN 43760 / IEC 60751 Pt100 table: a standardised relation, not a specimen (S-PT100)"),
    ("benchmarks/empirical_validation/evidence/scipy_codata.py", "REFERENCE_ONLY", "REFERENCE_CONSTANTS",
     "scipy 1.17.1 CODATA 2022 table copy (CODATA-2022-R)"),
    ("benchmarks/empirical_validation/fixtures/platinum_iec60751.json", "REFERENCE_ONLY", "REFERENCE_COEFFICIENTS",
     "IEC 60751 Callendar-Van Dusen coefficients recited, not retrieved; its own evidence_level field says not a measurement"),
    ("benchmarks/empirical_validation/fixtures/", "SYNTHETIC", "CONSTRUCTED_PROBLEM",
     "Hand-constructed operating points labelled LEVEL 5 independent analytical; battery_cell.json says nothing here is called a measurement"),
    ("benchmarks/ai_designs/components.json", "REFERENCE_ONLY", "DATASHEET_VALUES",
     "Manufacturer datasheet ratings transcribed from PDFs (ai_designs/components.md); ratings, not specimen measurements"),
    ("benchmarks/ai_designs/designs/", "SYNTHETIC", "BENCHMARK_CASE",
     "Hand-written designs; ai_designs/README.md: no laboratory measurement"),
    ("benchmarks/ai_designs/", "DERIVED", "ROUND_ARTIFACT", "Schema, prompts and scored results of the AI-designs round"),
    ("benchmarks/hard/cases_hard/", "SYNTHETIC", "BENCHMARK_CASE",
     "Generated by generate_hard.py; truth computed from first principles (hard/README.md)"),
    ("benchmarks/hard/cases_battery/", "SYNTHETIC", "BENCHMARK_CASE",
     "Generated by generate_battery.py; truth computed from first principles"),
    ("benchmarks/hard/", "DERIVED", "ROUND_ARTIFACT", "Indices, splits, adjudications and scored results of the synthetic hard benchmark"),
    ("benchmarks/blind/v1/cases/", "SYNTHETIC", "BENCHMARK_CASE",
     "Generated payloads with oracle truth; blind/README.md: nothing checked against a measurement"),
    ("benchmarks/blind/v1/TRUTH.json", "SYNTHETIC", "ORACLE_TRUTH", "Oracle-decided truth for generated cases"),
    ("benchmarks/blind/", "DERIVED", "ROUND_ARTIFACT", "Spec, freeze, comparisons and triage of the blind v1 challenge"),
    ("benchmarks/blind_v2/cases/", "SYNTHETIC", "BENCHMARK_CASE", "Generated cases; the generator states an intent, oracles decide"),
    ("benchmarks/blind_v2/truth/", "SYNTHETIC", "ORACLE_TRUTH", "Dual-oracle truth (closed form + numerical solver / ngspice)"),
    ("benchmarks/blind_v2/runner/", "SYNTHETIC", "BENCHMARK_CASE", "Smoke subsets of the generated cases"),
    ("benchmarks/blind_v2/", "DERIVED", "ROUND_ARTIFACT", "Runs, comparisons, freezes and audits of the blind v2 challenge"),
    ("benchmarks/oracles/results/", "SYNTHETIC", "ORACLE_TRUTH", "Independent oracle outputs over generated development cases"),
    ("benchmarks/scientific_truth/REFERENCE_CASES.json", "SYNTHETIC", "ORACLE_TRUTH", "Reference cases solved by code oracles (scientific_truth/oracles)"),
    ("benchmarks/performance/", "DERIVED", "COMPUTE_MEASUREMENT", "Wall-clock timings of this software; not a physical dataset"),
    ("benchmarks/performance_campaign/", "DERIVED", "COMPUTE_MEASUREMENT", "Wall-clock timings of this software"),
    ("benchmarks/perf_runtime_audit/", "DERIVED", "COMPUTE_MEASUREMENT", "Profiles and call counts of this software"),
    ("benchmarks/core_runtime_finalization/", "DERIVED", "COMPUTE_MEASUREMENT", "Profiles, scaling and mutation results of this software"),
    ("benchmarks/", "DERIVED", "ROUND_ARTIFACT", "Preregistrations, results, audits, mutation logs and reports written by a repository round"),
    ("experiments/falsification/", "SYNTHETIC", "SYNTHETIC_OBSERVATIONS",
     "Hidden truth g(x) with injected noise (falsification/truth.py, benchmark.py)"),
    ("experiments/thermal_t", "SYNTHETIC", "SYNTHETIC_OBSERVATIONS", "Synthetic alpha truth plus Gaussian noise (thermal_t1/t1_truth.py)"),
    ("experiments/electrical_e", "SYNTHETIC", "SYNTHETIC_OBSERVATIONS", "Hidden misspecification law with injected noise (electrical_e2/e2_truth.py)"),
    ("experiments/electrical_v01_demo/", "SYNTHETIC", "SYNTHETIC_OBSERVATIONS", "Demo configuration and results over analytic references"),
    ("experiments/kinetics_k1/", "SYNTHETIC", "SOLVER_ADMISSION", "Numerical regimes R1-R8, no data"),
    ("experiments/design_d3/", "DERIVED", "ROUND_ARTIFACT", "Design-loop results over synthetic reference models"),
    ("certification/", "DERIVED", "CERTIFICATION_MANIFEST", "Core certificate and freeze manifests"),
    ("docs/", "DERIVED", "ROUND_ARTIFACT", "Milestone freeze records"),
    ("tests/api/", "DERIVED", "API_SNAPSHOT", "Frozen API snapshots"),
    ("tests/inference/fixtures/", "DERIVED", "TEST_FIXTURE", "Posterior-grid fixtures computed from repository runs"),
)

BULK_LIST_LIMIT = 40


def _git(*args: str) -> list[str]:
    out = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, check=True).stdout
    return [line for line in out.decode("utf-8").splitlines() if line]


def data_files(include_untracked: bool = False) -> list[str]:
    # Tracked (including staged) files by default, so the committed scan is a fact about
    # a commit. --include-untracked widens it to a working tree before `git add`.
    files = set(_git("ls-files"))
    if include_untracked:
        files |= set(_git("ls-files", "--others", "--exclude-standard"))
    keep = []
    for path in files:
        if path in NOT_DATA:
            continue
        if path in EXTRA_DATA_FILES or path.lower().endswith(DATA_SUFFIXES):
            keep.append(path)
    return sorted(keep)


def classify(path: str) -> tuple[str, str, str, str]:
    for prefix, cls, role, rationale in RULES:
        if path.startswith(prefix):
            return prefix, cls, role, rationale
    return "", "UNKNOWN_PROVENANCE", "UNCLASSIFIED", "no rule matches; provenance not established"


def scan(include_untracked: bool = False) -> dict:
    groups: dict[tuple[str, str, str, str], list[str]] = collections.defaultdict(list)
    for path in data_files(include_untracked):
        groups[classify(path)].append(path)
    rows = []
    totals = collections.Counter()
    for (prefix, cls, role, rationale), paths in sorted(groups.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        totals[cls] += len(paths)
        row = {"rule_prefix": prefix, "class": cls, "role": role, "rationale": rationale, "file_count": len(paths)}
        if len(paths) <= BULK_LIST_LIMIT or cls in ("REAL_MEASURED", "REFERENCE_ONLY", "UNKNOWN_PROVENANCE"):
            row["files"] = paths
        else:
            row["files_sample"] = paths[:3]
        rows.append(row)
    return {
        "schema": "domain_real_data_repository_scan/1",
        "method": "git ls-files (tracked and staged), filtered to data-bearing suffixes, each matched against an ordered prefix rule table (audit/inventory_scan.py)",
        "data_suffixes": list(DATA_SUFFIXES),
        "extra_data_files": list(EXTRA_DATA_FILES),
        "excluded_as_not_data": list(NOT_DATA),
        "totals_by_class": dict(sorted(totals.items())),
        "total_files": sum(totals.values()),
        "unknown_provenance_files": totals.get("UNKNOWN_PROVENANCE", 0),
        "groups": rows,
    }


def render(doc: dict) -> bytes:
    return (json.dumps(doc, indent=1, ensure_ascii=False) + "\n").encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--include-untracked", action="store_true")
    args = parser.parse_args()
    doc = scan(args.include_untracked)
    data = render(doc)
    if args.include_untracked:
        print(json.dumps(doc["totals_by_class"]), "unknown", doc["unknown_provenance_files"])
        return 1 if doc["unknown_provenance_files"] else 0
    if args.check:
        stale = not OUT.exists() or OUT.read_bytes() != data
        print("REPOSITORY_SCAN.json", "STALE" if stale else "current")
        return 1 if stale or doc["unknown_provenance_files"] else 0
    OUT.write_bytes(data)
    print(json.dumps(doc["totals_by_class"]), "total", doc["total_files"])
    return 1 if doc["unknown_provenance_files"] else 0


if __name__ == "__main__":
    sys.exit(main())
