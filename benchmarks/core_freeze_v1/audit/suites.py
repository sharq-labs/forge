"""Core Freeze V1 -- Part 14: every required suite, on the frozen candidate.

    python -X utf8 benchmarks/core_freeze_v1/audit/suites.py <evidence-dir>

Writes ``<evidence-dir>/SUITES.json``. The file is written OUTSIDE the
repository on purpose: several of these suites -- the certificate suite and the
freeze-manifest suite -- refuse a dirty working tree, correctly, so evidence
cannot be dropped into the checkout while the evidence is still being gathered.
It is copied in afterwards, together with everything else, and committed.

Refuses to start on a dirty tree for the same reason: a suite result about
uncommitted bytes is not a result about the candidate.

Domain regression is not repeated here. ``domain_boundary.py`` runs those
eleven suites itself as the third leg of its proof and records them in
DOMAIN_BOUNDARY.json; running them twice would be two records of one fact.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[3]
PY = str(ROOT / ".venv" / "Scripts" / "python.exe")

SUITES = {
    "FAST": ["tests", "-n", "4", "-m", "not expensive and not campaign"],
    "FULL": ["tests", "-n", "4"],
    "contract_guard": [
        "tests/test_core_guards.py", "tests/test_design_d0_contracts.py",
        "tests/test_data_boundary0.py",
    ],
    "capability_boundary": [
        "tests/domains", "-k", "applicab or boundary",
        "tests/mcp/test_battery_boundary.py",
    ],
    "scientific_truth": [
        "tests/domains/test_evidentiary_level_audit.py",
        "tests/oracles/test_independent_case_truth.py",
        "tests/oracles/test_independent_reason_truth.py",
        "tests/test_result_validity.py", "tests/test_blind_challenge_guards.py",
    ],
    "field_suites": [
        "tests/test_field_records.py", "tests/test_field_values.py",
        "tests/test_field_composition.py", "tests/test_field_ir_ceiling.py",
        "tests/test_conduction2d.py", "tests/test_conduction2d_convergence.py",
    ],
    "field_profile_suites": [
        "tests/test_field_profiles.py", "tests/test_field_profiled_conditions.py",
        "tests/test_field_profile_limit.py", "tests/test_field_coefficient_spike.py",
        "tests/test_conduction2d_profiled.py",
    ],
    "api_snapshot": [
        "tests/test_core_api_snapshot.py", "tests/test_core_api_deprecation.py",
        "tests/test_core_freeze_policy.py",
    ],
    # The Sprint 10 serialization policy suite AND the suites that load real
    # legacy payloads for the eight readers that accept older versions.
    "serialization": [
        "tests/test_core_api_serialization.py", "tests/test_result_validity.py",
        "tests/test_provenance_integrity.py", "tests/test_consensus_integrity.py",
        "tests/test_model0r_realization_foundation.py",
    ],
    "dependency_layering": [
        "tests/test_core_api_contracts.py", "tests/test_core_api_layering.py",
        "tests/test_trust_boundary_package_identity.py",
    ],
    "freeze_manifest": ["tests/test_core_freeze_manifest.py"],
    "certificate": ["tests/test_core_certificate.py"],
}

COUNT = re.compile(r"(\d+) (passed|failed|skipped|deselected|errors?)\b")


def main() -> int:
    out_dir = pathlib.Path(sys.argv[1])
    out_dir.mkdir(parents=True, exist_ok=True)
    porcelain = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT,
                               capture_output=True, text=True, check=True).stdout
    if porcelain.strip():
        raise SystemExit(f"refusing: the tree is dirty\n{porcelain}")
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                            capture_output=True, text=True, check=True).stdout.strip()
    env = dict(os.environ, TMPDIR=os.environ.get("TMPDIR", "D:/ftmp"))

    results = {}
    for index, (name, selection) in enumerate(SUITES.items()):
        argv = [PY, "-X", "utf8", "-m", "pytest", *selection, "-q",
                "-p", "no:cacheprovider", "--basetemp", f"D:/fz{index}"]
        started = time.monotonic()
        proc = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", env=env)
        lines = (proc.stdout + proc.stderr).strip().splitlines()
        summary = next((l for l in reversed(lines) if COUNT.search(l)), "")
        counts = {"passed": 0, "failed": 0, "skipped": 0, "deselected": 0, "error": 0}
        for number, kind in COUNT.findall(summary):
            counts["error" if kind.startswith("error") else kind] += int(number)
        failures = [l for l in lines if l.startswith(("FAILED ", "ERROR "))]
        results[name] = {
            "selection": " ".join(selection),
            "exit": proc.returncode,
            "passed": counts["passed"],
            "failed": counts["failed"] + counts["error"],
            "skipped": counts["skipped"],
            "deselected": counts["deselected"],
            # Wall clock stripped: it is not a fact about the candidate.
            "summary": re.sub(r" in [0-9.]+s( \([0-9:]+\))?$", "", summary.strip()),
            "failures": failures[:20],
        }
        print(f"{name:22} exit={proc.returncode}  {results[name]['summary']}"
              f"  ({time.monotonic() - started:.0f}s)", flush=True)

    after = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT,
                           capture_output=True, text=True, check=True).stdout
    document = {
        "commit": commit,
        "tree_clean_before": True,
        "tree_clean_after": not after.strip(),
        "suites": results,
        "all_green": all(r["exit"] == 0 and r["failed"] == 0 for r in results.values()),
    }
    (out_dir / "SUITES.json").write_bytes(
        json.dumps(document, indent=2, sort_keys=True).encode("utf-8") + b"\n")
    print(f"\nall green: {document['all_green']}  -> {out_dir / 'SUITES.json'}")
    return 0 if document["all_green"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
