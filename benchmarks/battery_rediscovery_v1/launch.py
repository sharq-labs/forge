"""Launch the v1 candidate run (or its replay) only from a committed, unchanged freeze with a passing mutation report.

    python -m benchmarks.battery_rediscovery_v1.launch run
    python -m benchmarks.battery_rediscovery_v1.launch replay

Refuses unless: every frozen file matches PLAN.json; PLAN.json, its digest and every frozen file are committed (no
uncommitted change under the v1 directory except results/); the pre-run mutation report is PASS, is the one PLAN.json
binds, and was produced by the scanner bytes PLAN.json binds.  The arms then run under ``sandbox_run``'s audit hook.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess
import sys

from . import freeze

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RESULTS = HERE / "results"
REL = "benchmarks/battery_rediscovery_v1"


def _sha(p: pathlib.Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def preconditions() -> list[str]:
    problems = []
    if freeze.main(["--check"]) != 0:
        problems.append("frozen files changed since PLAN.json")
    plan = json.loads((HERE / "PLAN.json").read_bytes())
    if (HERE / "PLAN.sha256").read_bytes().split()[0].decode() != _sha(HERE / "PLAN.json"):
        problems.append("PLAN.sha256 does not match PLAN.json")
    dirty = subprocess.run(["git", "status", "--porcelain", "--", REL], cwd=ROOT, capture_output=True, text=True,
                           check=True).stdout.splitlines()
    dirty = [d for d in dirty if f"{REL}/results/" not in d and "__pycache__" not in d]
    if dirty:
        problems.append(f"uncommitted changes under {REL}: {dirty[:5]}")
    mut = HERE / "MUTATION_REPORT_pre_run.json"
    rep = json.loads(mut.read_bytes())
    if rep["status"] != "PASS":
        problems.append("the pre-run mutation report is not PASS")
    if _sha(mut) != plan["leakage"]["mutation_report_pre_run_sha256"]:
        problems.append("the pre-run mutation report is not the one PLAN.json binds")
    if rep["scanner_sha256"] != plan["leakage"]["scanner_sha256"] or _sha(HERE / "leakage.py") != plan["leakage"]["scanner_sha256"]:
        problems.append("the scanner differs from the one the mutation report and PLAN.json bind")
    return problems


def main(argv: list[str]) -> int:
    mode = argv[0] if argv else ""
    if mode not in ("run", "replay"):
        print("usage: launch run|replay", file=sys.stderr)
        return 2
    problems = preconditions()
    if problems:
        for p in problems:
            print("REFUSED:", p, file=sys.stderr)
        return 3
    py = sys.executable
    if mode == "run":
        if (RESULTS / "candidate").exists():
            print("REFUSED: results/candidate exists; a v1 run happens once", file=sys.stderr)
            return 3
        args = [str(RESULTS / "ACCESS_LOG.json"), "--", "--out", str(RESULTS / "candidate")]
    else:
        args = [str(RESULTS / "ACCESS_LOG_REPLAY.json"), "--", "--replay", str(RESULTS / "candidate"),
                "--out", str(RESULTS / "replay")]
    RESULTS.mkdir(exist_ok=True)
    return subprocess.run([py, "-m", "benchmarks.battery_rediscovery_v1.sandbox_run", *args], cwd=ROOT).returncode


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
