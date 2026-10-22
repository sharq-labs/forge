"""Seal the v3 candidate outputs before any truth is computed.

    python -m benchmarks.battery_rediscovery_v3.seal

Refuses if a frozen file changed or a TruthBundle file exists.  Runs the pre-seal audit with firewall v3 (numeric and
text scan of the candidate material, bundle schema, measurement provenance, runtime path/module audit of the run's access
log with outputs write-only) and checks that every expected candidate output exists.  Writes results/SEAL.json (status
PASS or LEAKAGE_INVALIDATED), to be committed before the replay and the evaluation.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess
import sys

from benchmarks.battery_rediscovery_v2.candidate.common import write_json

from . import freeze, leakage, mutation

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RESULTS = HERE / "results"


def _sha(p: pathlib.Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _rel(p: pathlib.Path) -> str:
    return str(p.resolve().relative_to(ROOT)).replace("\\", "/")


def main() -> int:
    if freeze.main(["--check"]) != 0:
        print("REFUSED: frozen files changed since PLAN.json", file=sys.stderr)
        return 3
    if (HERE / "TruthBundle").exists() and any(p.is_file() for p in (HERE / "TruthBundle").rglob("*")):
        print("REFUSED: a TruthBundle exists before the seal", file=sys.stderr)
        return 3
    cand = RESULTS / "candidate"
    plan = json.loads((HERE / "PLAN.json").read_bytes())
    expected = [HERE / e for e in plan["expected_outputs"]
                if e.startswith("results/candidate/") or e == "results/ACCESS_LOG.json"]
    missing = [_rel(p) for p in expected if not p.exists()]
    report = leakage.audit(mutation.protected_values(), access_logs=[(RESULTS / "ACCESS_LOG.json", [cand], [])],
                           phase="pre_seal")
    if missing:
        report["status"] = "LEAKAGE_INVALIDATED"
        report["missing_outputs"] = missing
    audit_path = RESULTS / "LEAKAGE_PRE_SEAL.json"
    write_json(audit_path, report)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    payload = {"schema": "forge.battery_rediscovery_v3.seal/1", "experiment": "battery_rediscovery_v3",
               "status": report["status"], "code_commit": head, "plan_sha256": _sha(HERE / "PLAN.json"),
               "gen1_reference_sha256": _sha(ROOT / "docs" / "discovery" / "mind_gen1_reference.json"),
               "scanner_sha256": _sha(HERE / "leakage.py"),
               "mutation_report_pre_run_sha256": _sha(HERE / "MUTATION_REPORT_pre_run.json"),
               "pack_manifest_sha256": _sha(HERE / "CandidateBundle" / "MANIFEST.json"),
               "access_log": {_rel(RESULTS / "ACCESS_LOG.json"): _sha(RESULTS / "ACCESS_LOG.json")},
               "leakage_pre_seal": {_rel(audit_path): _sha(audit_path)},
               "outputs": {_rel(p): _sha(p) for p in sorted(cand.glob("*.json")) if p.name != "TIMINGS.json"},
               "note": "TIMINGS.json is excluded: wall-clock values are not scientific content"}
    sha = write_json(RESULTS / "SEAL.json", payload)
    print(report["status"], sha)
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
