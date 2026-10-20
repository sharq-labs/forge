"""Domain real-data round: classify every data-bearing file in the repository.

    python -X utf8 benchmarks/domain_real_data/audit/inventory_scan.py          # print live inventory
    python -X utf8 benchmarks/domain_real_data/audit/inventory_scan.py --check  # historical replay AND live coverage
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

Historical classifications are inherited only for unchanged historical blobs.
New/changed paths require explicit artifact/source declarations matching both
raw working bytes and the Git index; directory prefixes grant no new coverage.
The preserved report describes its pinned historical tree, not today's checkout.
Classification never says a file is useful; claim mapping lives in DATASETS.json.
"""

from __future__ import annotations

import argparse
import collections
import functools
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys
import types

ROOT = pathlib.Path(__file__).resolve().parents[3]
OUT = ROOT / "benchmarks" / "domain_real_data" / "REPOSITORY_SCAN.json"
HISTORICAL_COMMIT = "a80b4df5e4cb6e0cdfc4e4e87f9f09d13a7823db"
HISTORICAL_TREE = "45ba44977eb7a4f06dc1f8fe5a17776e5bff05aa"
HISTORICAL_SCANNER_SHA256 = "ce5abd8860d923b79f621e60feaf16b7775ff497ec8e099a2752b71d4ccbc3b9"
HISTORICAL_REPORT_SHA256 = "a26fe3c3b9fd7bc5b0cb6f3d158dcd4997f27ec977ab8275e1a7db2e027768c5"
REVIEW_PATH = "benchmarks/domain_real_data/CURRENT_PROVENANCE.json"

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


def _git_bytes(*args: str) -> bytes:
    env = {key: value for key, value in os.environ.items() if not key.upper().startswith("GIT_")}
    return subprocess.run(["git", *args], cwd=ROOT, env=env, capture_output=True, check=True).stdout


def _git(*args: str) -> list[str]:
    out = _git_bytes(*args)
    return [line for line in out.decode("utf-8").splitlines() if line]


def _git_z(*args: str) -> list[str]:
    return [part.decode("utf-8") for part in _git_bytes(*args).split(b"\0") if part]


def _historical_entries() -> dict[str, str]:
    try:
        if _git("rev-parse", HISTORICAL_COMMIT + "^{tree}") != [HISTORICAL_TREE]:
            raise RuntimeError("historical tree identity mismatch")
        entries = {}
        for line in _git_z("ls-tree", "-rz", HISTORICAL_TREE):
            metadata, path = line.split("\t", 1)
            mode, kind, blob = metadata.split()
            if kind == "blob" and mode in ("100644", "100755"):
                entries[path] = blob
        return entries
    except subprocess.CalledProcessError as exc:
        raise RuntimeError("historical Git objects unavailable; fetch full history") from exc


@functools.lru_cache(maxsize=1)
def _historical_program():
    source = _git_bytes("show", HISTORICAL_COMMIT + ":benchmarks/domain_real_data/audit/inventory_scan.py")
    if hashlib.sha256(source).hexdigest() != HISTORICAL_SCANNER_SHA256:
        raise RuntimeError("historical scanner identity mismatch")
    module = types.ModuleType("_pinned_historical_inventory")
    module.__file__ = str(ROOT / "benchmarks/domain_real_data/audit/inventory_scan.py")
    exec(compile(source, module.__file__, "exec"), module.__dict__)
    return module


def historical_scan() -> dict:
    """Reconstruct only the archived claim, using its pinned original program."""
    _historical_entries()
    if hashlib.sha256(OUT.read_bytes()).hexdigest() != HISTORICAL_REPORT_SHA256:
        raise RuntimeError("historical report identity mismatch")
    module = _historical_program()
    # Preserve historical quoting behavior only for exact archival replay.
    paths = _git("ls-tree", "-r", "--name-only", HISTORICAL_TREE)
    module._git = lambda *args: paths
    return module.scan()


def _unchanged_historical_paths() -> set[str]:
    historical = _historical_entries()
    unchanged = set()
    for line in _git_z("ls-files", "--stage", "-z"):
        metadata, path = line.split("\t", 1)
        mode, blob, stage = metadata.split()
        if path in NOT_DATA or (path not in EXTRA_DATA_FILES and not path.lower().endswith(DATA_SUFFIXES)):
            continue
        if stage == "0" and mode in ("100644", "100755") and historical.get(path) == blob:
            candidate = ROOT / path
            if (not candidate.is_file() or candidate.is_symlink()
                    or not candidate.resolve().is_relative_to(ROOT.resolve())):
                continue
            # Hash raw bytes even when Git's assume-unchanged/skip-worktree flags
            # hide a modification. Checkout normalization is conservatively unknown.
            body = candidate.read_bytes()
            actual = hashlib.sha1(b"blob " + str(len(body)).encode() + b"\0" + body).hexdigest()
            if actual == blob:
                unchanged.add(path)
    return unchanged


def data_files(include_untracked: bool = False) -> list[str]:
    # Tracked (including staged) files by default, so the committed scan is a fact about
    # a commit. --include-untracked widens it to a working tree before `git add`.
    files = set(_git_z("ls-files", "-z"))
    if include_untracked:
        files |= set(_git_z("ls-files", "--others", "--exclude-standard", "-z"))
    keep = []
    for path in files:
        if path in NOT_DATA:
            continue
        if path in EXTRA_DATA_FILES or path.lower().endswith(DATA_SUFFIXES):
            keep.append(path)
    return sorted(keep)


def _classify_reviewed(path: str) -> tuple[str, str, str, str]:
    return _historical_program().classify(path)


def reviewed_declarations(root=None, manifest=None) -> dict:
    """Read explicit reviewed inventory metadata; never scientific evidence admission."""
    root = ROOT if root is None else pathlib.Path(root)
    manifest = root / REVIEW_PATH if manifest is None else pathlib.Path(manifest)
    if not manifest.exists():
        return {}
    if manifest.is_symlink() or not manifest.resolve().is_relative_to(root.resolve()):
        raise ValueError("provenance review must be a local regular file")
    manifest_body = manifest.read_bytes()
    doc = json.loads(manifest_body)
    if (set(doc) != {"schema", "review_base", "records"}
            or doc["schema"] != "domain_real_data_provenance_review/1"
            or not re.fullmatch(r"[0-9a-f]{40}", doc["review_base"])
            or not isinstance(doc["records"], list)):
        raise ValueError("invalid provenance review schema")
    seen, accepted = set(), {}
    env = {key: value for key, value in os.environ.items() if not key.upper().startswith("GIT_")}
    indexed = {}
    for row in subprocess.run(
            ["git", "ls-files", "--stage", "-z"], cwd=root, env=env,
            check=True, capture_output=True).stdout.split(b"\0"):
        if not row:
            continue
        metadata, name = row.decode("utf-8").split("\t", 1)
        mode, blob, stage = metadata.split()
        if stage == "0" and mode in ("100644", "100755"):
            indexed[name] = blob

    def index_matches(name, body):
        blob = hashlib.sha1(b"blob " + str(len(body)).encode() + b"\0" + body).hexdigest()
        return indexed.get(name) == blob

    def bound_file(entry):
        name, digest = entry["path"], entry["sha256"]
        if (not isinstance(name, str) or "\\" in name or ":" in name
                or name.startswith("/") or any(p in ("", ".", "..") for p in name.split("/"))
                or not re.fullmatch(r"[0-9a-f]{64}", digest)):
            raise ValueError("invalid provenance path or digest")
        if "commit" in entry:
            if not re.fullmatch(r"[0-9a-f]{40}", entry["commit"]):
                raise ValueError("provenance source commit must be immutable")
            env = {key: value for key, value in os.environ.items() if not key.upper().startswith("GIT_")}
            body = subprocess.run(
                ["git", "show", entry["commit"] + ":" + name],
                cwd=root, env=env, check=True, capture_output=True,
            ).stdout
            return hashlib.sha256(body).hexdigest() == digest
        file = root / name
        if (not file.is_file() or file.is_symlink()
                or not file.resolve().is_relative_to(root.resolve())):
            return False
        body = file.read_bytes()
        return hashlib.sha256(body).hexdigest() == digest and index_matches(name, body)

    for entry in doc["records"]:
        required = {"path", "sha256", "class", "role", "rationale", "evidence"}
        if not required <= set(entry) or set(entry) - required - {"dataset_record"}:
            raise ValueError("invalid provenance record fields")
        path = entry["path"]
        if path in seen:
            raise ValueError("duplicate provenance declaration")
        seen.add(path)
        if entry["class"] not in {"DERIVED", "SYNTHETIC", "REAL_MEASURED", "REFERENCE_ONLY"}:
            raise ValueError("invalid provenance class")
        if not all(isinstance(entry[k], str) and entry[k].strip() for k in ("role", "rationale")):
            raise ValueError("missing provenance rationale")
        evidence = entry["evidence"]
        if (not isinstance(evidence, list) or not evidence
                or any(set(e) not in ({"path", "sha256"}, {"path", "sha256", "commit"})
                       or e["path"] == path for e in evidence)):
            raise ValueError("provenance requires independently identified source records")
        if entry["class"] in {"REAL_MEASURED", "REFERENCE_ONLY"}:
            if entry.get("dataset_record") not in {e["path"] for e in evidence}:
                raise ValueError("physical/reference declaration requires dataset_record evidence")
        if bound_file(entry) and all(bound_file(e) for e in evidence):
            accepted[path] = entry
    # Preserve record-field errors before refusing an unstaged manifest.
    manifest_name = manifest.resolve().relative_to(root.resolve()).as_posix()
    return accepted if index_matches(manifest_name, manifest_body) else {}


def _declared_classification(path, declarations):
    if path == REVIEW_PATH and (ROOT / REVIEW_PATH).is_file():
        # Exact schema-checked inventory bookkeeping, not a source of measurements.
        return path, "DERIVED", "PROVENANCE_REVIEW_DOCUMENT", "explicit reviewed inventory declarations; not validation"
    if path in declarations:
        record = declarations[path]
        return path, record["class"], record["role"], record["rationale"]
    return "", "UNKNOWN_PROVENANCE", "UNREVIEWED_CHANGE", "new or changed bytes need explicit provenance review"


def classify(path: str) -> tuple[str, str, str, str]:
    if path not in _unchanged_historical_paths():
        return _declared_classification(path, reviewed_declarations())
    return _classify_reviewed(path)


def scan(include_untracked: bool = False) -> dict:
    groups: dict[tuple[str, str, str, str], list[str]] = collections.defaultdict(list)
    reviewed = _unchanged_historical_paths()
    declarations = reviewed_declarations()
    for path in data_files(include_untracked):
        classification = (_classify_reviewed(path) if path in reviewed
                          else _declared_classification(path, declarations))
        groups[classification].append(path)
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
        "schema": "domain_real_data_repository_scan/2",
        "method": "NUL-delimited live tracked/staged paths; pinned historical classes inherited only when index and raw working bytes match historical blobs; new or changed bytes require explicit reviewed artifact/source bindings matching the index; otherwise UNKNOWN_PROVENANCE",
        "historical_commit": HISTORICAL_COMMIT,
        "classification_limit": "inherited historical classification is not independently validated provenance",
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
        reproduced = render(historical_scan()) == OUT.read_bytes()
        print("historical REPOSITORY_SCAN.json", "reproduced" if reproduced else "MISMATCH")
        print("live UNKNOWN_PROVENANCE", doc["unknown_provenance_files"])
        return 1 if not reproduced or doc["unknown_provenance_files"] else 0
    # The historical report is immutable. Live output is explicit and never overwrites it.
    sys.stdout.buffer.write(data)
    print(json.dumps(doc["totals_by_class"]), "total", doc["total_files"])
    return 1 if doc["unknown_provenance_files"] else 0


if __name__ == "__main__":
    sys.exit(main())
