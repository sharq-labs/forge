"""Seal the candidate outputs before the evaluator may read any historical record.

    python -m benchmarks.battery_rediscovery_v0.seal --outputs <dir> --access-log <file>

Refuses if any frozen file changed since PLAN.json.  Runs the pre-seal leakage audit (static, pack schema, runtime
access log); on a finding it writes the seal with status LEAKAGE_INVALIDATED and exits 2.  Otherwise SEAL.json binds
the plan, the pack manifest, the access log, the audit and every output by sha256.  The seal is then committed; the
evaluator refuses to run unless that commit is in HEAD's history and every bound file still matches.
"""

from __future__ import annotations

import argparse
import hashlib
import pathlib
import subprocess
import sys

from . import freeze, leakage
from .candidate.common import write_json

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def _sha(p: pathlib.Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _rel(p: pathlib.Path) -> str:
    return str(p.resolve().relative_to(ROOT)).replace("\\", "/")


def seal(outputs: pathlib.Path, access_log: pathlib.Path) -> int:
    if freeze.main(["--check"]) != 0:
        print("REFUSED: frozen files changed since PLAN.json", file=sys.stderr)
        return 3
    report = leakage.audit(access_log, outputs, post_seal=False)
    audit_path = outputs.parent / "LEAKAGE_PRE_SEAL.json"
    write_json(audit_path, report)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    files = {_rel(p): _sha(p) for p in sorted(outputs.glob("*.json")) if p.name != "TIMINGS.json"}
    payload = {"schema": "forge.battery_rediscovery.seal/1", "status": report["status"], "code_commit": head,
               "plan_sha256": _sha(HERE / "PLAN.json"), "pack_manifest_sha256": _sha(HERE / "candidate" / "pack" / "MANIFEST.json"),
               "access_log": {_rel(access_log): _sha(access_log)}, "leakage_pre_seal": {_rel(audit_path): _sha(audit_path)},
               "outputs": files,
               "note": "TIMINGS.json is excluded: wall-clock values are not scientific content"}
    sha = write_json(outputs.parent / "SEAL.json", payload)
    print(report["status"], sha)
    return 0 if report["status"] == "PASS" else 2


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--outputs", required=True, type=pathlib.Path)
    ap.add_argument("--access-log", required=True, type=pathlib.Path)
    a = ap.parse_args(argv)
    return seal(a.outputs, a.access_log)


if __name__ == "__main__":
    raise SystemExit(main())
