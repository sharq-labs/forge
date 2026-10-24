"""Launch the v2 candidate run (once) or its replay (after the seal), only from a committed, unchanged freeze.

    python -m benchmarks.battery_rediscovery_v2.launch run
    python -m benchmarks.battery_rediscovery_v2.launch replay

Refuses unless: every frozen file matches PLAN.json; PLAN.json, its digest and every frozen file are committed (no
uncommitted change under the v2 directory except results/); the pre-run mutation report is PASS, is the one PLAN.json
binds, and was produced by the scanner bytes PLAN.json binds.  ``run`` refuses if results/candidate exists (a v2 run
happens once).  ``replay`` refuses unless results/SEAL.json is PASS and committed.  Both run under ``sandbox_run``.
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
REL = freeze.REL


def _sha(p: pathlib.Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout


def preconditions() -> list[str]:
    problems = []
    if freeze.main(["--check"]) != 0:
        problems.append("frozen files changed since PLAN.json")
    plan = json.loads((HERE / "PLAN.json").read_bytes())
    if (HERE / "PLAN.sha256").read_bytes().split()[0].decode() != _sha(HERE / "PLAN.json"):
        problems.append("PLAN.sha256 does not match PLAN.json")
    dirty = [d for d in _git("status", "--porcelain", "--untracked-files=all", "--", REL).splitlines()
             if f"{REL}/results/" not in d and "__pycache__" not in d]
    if dirty:
        problems.append(f"uncommitted changes under {REL}: {dirty[:5]}")
    imported = [p for p in plan["sources"]["imported_frozen_files"]]
    dirty_imp = [d for d in _git("status", "--porcelain", "--", *imported).splitlines()]
    if dirty_imp:
        problems.append(f"uncommitted changes in imported frozen files: {dirty_imp[:5]}")
    mut = HERE / "MUTATION_REPORT_pre_run.json"
    rep = json.loads(mut.read_bytes())
    if rep["status"] != "PASS":
        problems.append("the pre-run mutation report is not PASS")
    if _sha(mut) != plan["leakage"]["mutation_report_pre_run_sha256"]:
        problems.append("the pre-run mutation report is not the one PLAN.json binds")
    if rep["scanner_sha256"] != plan["leakage"]["scanner_sha256"] or _sha(HERE / "leakage.py") != plan["leakage"]["scanner_sha256"]:
        problems.append("the scanner differs from the one the mutation report and PLAN.json bind")
    return problems


def _seal_committed() -> str | None:
    seal = RESULTS / "SEAL.json"
    if not seal.exists():
        return "no SEAL.json"
    rel = f"{REL}/results/SEAL.json"
    commits = _git("log", "--format=%H", "--", rel).split()
    if not commits:
        return "SEAL.json is not committed"
    if subprocess.run(["git", "show", f"{commits[-1]}:{rel}"], cwd=ROOT, capture_output=True, check=True).stdout != seal.read_bytes():
        return "SEAL.json differs from the bytes first committed"
    if json.loads(seal.read_bytes())["status"] != "PASS":
        return "the seal is not PASS"
    return None


def main(argv: list[str]) -> int:
    mode = argv[0] if argv else ""
    if mode not in ("run", "replay"):
        print("usage: launch run|replay", file=sys.stderr)
        return 2
    problems = preconditions()
    if mode == "replay":
        why = _seal_committed()
        if why:
            problems.append(why)
    if problems:
        for p in problems:
            print("REFUSED:", p, file=sys.stderr)
        return 3
    if mode == "run":
        if (RESULTS / "candidate").exists():
            print("REFUSED: results/candidate exists; a v2 run happens once", file=sys.stderr)
            return 3
        args = [str(RESULTS / "ACCESS_LOG.json"), "--", "--out", str(RESULTS / "candidate")]
    else:
        args = [str(RESULTS / "ACCESS_LOG_REPLAY.json"), "--", "--replay", str(RESULTS / "candidate"),
                "--out", str(RESULTS / "replay")]
    RESULTS.mkdir(exist_ok=True)
    return subprocess.run([sys.executable, "-m", f"{REL.replace('/', '.')}.sandbox_run", *args], cwd=ROOT).returncode


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
