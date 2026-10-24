"""Seal the v1 candidate outputs before the evaluator reads any historical record or any v1 truth.

    python -m benchmarks.battery_rediscovery_v1.seal

Refuses if a frozen file changed.  Runs the pre-seal audit with scanner v1 (numeric with the pre-run protected values,
text, pack schema, measurement provenance, runtime path/module audit of the run's access log) and checks that every
expected candidate output exists.  Writes results/SEAL.json (status PASS or LEAKAGE_INVALIDATED), to be committed
before evaluation.
"""

from __future__ import annotations

import hashlib
import pathlib
import subprocess
import sys

from . import freeze, leakage, mutation
from .candidate.common import write_json

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
    cand = RESULTS / "candidate"
    expected = [ROOT / "benchmarks" / "battery_rediscovery_v1" / e for e in freeze.EXPECTED_OUTPUTS
                if e.startswith("results/candidate/") or e == "results/ACCESS_LOG.json"]
    missing = [_rel(p) for p in expected if not p.exists()]
    values = list(mutation.SYNTHETIC) + mutation.historical_values()
    report = leakage.audit(values, access_logs=[RESULTS / "ACCESS_LOG.json"], out_dirs=[cand], phase="pre_seal")
    if missing:
        report["status"] = "LEAKAGE_INVALIDATED"
        report["missing_outputs"] = missing
    audit_path = RESULTS / "LEAKAGE_PRE_SEAL.json"
    write_json(audit_path, report)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    payload = {"schema": "forge.battery_rediscovery.seal/2", "experiment": "battery_rediscovery_v1",
               "status": report["status"], "code_commit": head, "plan_sha256": _sha(HERE / "PLAN.json"),
               "scanner_sha256": _sha(HERE / "leakage.py"),
               "mutation_report_pre_run_sha256": _sha(HERE / "MUTATION_REPORT_pre_run.json"),
               "pack_manifest_sha256": _sha(HERE / "candidate" / "pack" / "MANIFEST.json"),
               "access_log": {_rel(RESULTS / "ACCESS_LOG.json"): _sha(RESULTS / "ACCESS_LOG.json")},
               "leakage_pre_seal": {_rel(audit_path): _sha(audit_path)},
               "outputs": {_rel(p): _sha(p) for p in sorted(cand.glob("*.json")) if p.name != "TIMINGS.json"},
               "note": "TIMINGS.json is excluded: wall-clock values are not scientific content"}
    sha = write_json(RESULTS / "SEAL.json", payload)
    print(report["status"], sha)
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
