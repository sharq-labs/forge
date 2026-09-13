"""Phase 10 repair mutation matrix: RIDGE-1..8, each applied, tested and reverted.

    python -X utf8 benchmarks/core_v1_thin_ridge_repair/audit/ridge_mutations.py --tree <checkout> [RIDGE-n ...]

Separate from tests/mutation_guards.py, which is certification-pinned. Run it against a scratch checkout
(a git worktree) so a crash cannot leave a mutant in the working tree; PYTHONPATH is set to that
checkout's src so the mutant, not the editable install, is what the tests import. Each mutation must
match its target text exactly once. A control run with no mutation must pass first. A mutation counts
as KILLED only when pytest exits 1 (tests ran and failed); collection or usage errors count as ERROR.
Every file is restored byte-for-byte and its SHA-256 re-checked after each run.

Writes benchmarks/core_v1_thin_ridge_repair/RIDGE_MUTATIONS.json in THIS checkout (not --tree).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).resolve().parents[3]
CAL = "src/engcore/inference/calibration.py"
PRED = "src/engcore/uq/predictive.py"
TARGETS = [
    "tests/inference/test_grid_resolution_repair.py",
    "tests/inference/test_tcr_calibration.py",
    "tests/inference/test_tcr_heldout_uq.py",
    "tests/inference/test_reproducibility_and_evidence.py",
    "tests/test_k3_predictive_uq.py",
    "tests/test_k31_predictive_admission.py",
    "tests/test_k4_model_adequacy.py",
    "tests/test_evidence_pairing_integrity.py",
]

MUTATIONS = {
    "RIDGE-1": ("remove the aliasing check", CAL,
                "    aliasing = _minimum_aliasing_number(lattice_covariance, _ALIASING_NUMBER_MINIMUM)\n    if aliasing is not None:\n",
                "    aliasing = _minimum_aliasing_number(lattice_covariance, _ALIASING_NUMBER_MINIMUM)\n    if False:\n"),
    "RIDGE-2": ("use the diagonal of the fitted covariance only", CAL,
                "    aliasing = _minimum_aliasing_number(lattice_covariance, _ALIASING_NUMBER_MINIMUM)\n",
                "    aliasing = _minimum_aliasing_number(np.diag(np.diag(lattice_covariance)), _ALIASING_NUMBER_MINIMUM)\n"),
    "RIDGE-3": ("enumerate axis lattice vectors only (drop off-axis n)", CAL,
                "                if np.any(n != 0):\n",
                "                if np.count_nonzero(n) == 1:\n"),
    "RIDGE-4": ("disable scale normalization (fit in parameter units)", CAL,
                "        x = (points[index] - points[top]) / steps\n",
                "        x = points[index] - points[top]\n"),
    "RIDGE-5": ("let ESS ~ 1 pass", CAL,
                "    if ess < p + 1:\n",
                "    if ess < 1.0:\n"),
    "RIDGE-6": ("predictive UQ ignores the refusal", PRED,
                "    refusal = _grid_resolution_refusal(posterior, discrete_posterior_passes=True)\n    if refusal is not None:\n",
                "    refusal = _grid_resolution_refusal(posterior, discrete_posterior_passes=True)\n    if False:\n"),
    "RIDGE-7": ("threshold comparison reversed", CAL,
                "    aliasing = _minimum_aliasing_number(lattice_covariance, _ALIASING_NUMBER_MINIMUM)\n    if aliasing is not None:\n",
                "    aliasing = _minimum_aliasing_number(lattice_covariance, _ALIASING_NUMBER_MINIMUM)\n    if aliasing is None:\n"),
    "RIDGE-8": ("covariance fit failure treated as PASS", CAL,
                "    if lattice_covariance is None:\n        return (\n",
                "    if lattice_covariance is None:\n        return None\n        return (\n"),
}


def sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pytest(tree: pathlib.Path, basetemp: str) -> tuple[int, str, float]:
    env = dict(os.environ, PYTHONPATH=str(tree / "src"), PYTHONDONTWRITEBYTECODE="1")
    started = time.monotonic()
    proc = subprocess.run([sys.executable, "-X", "utf8", "-m", "pytest", *TARGETS, "-q", "-x", "-n", "4", "-p", "no:cacheprovider",
                           f"--basetemp={basetemp}"], cwd=tree, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
    tail = [line for line in proc.stdout.splitlines() if line.startswith(("FAILED", "ERROR")) or " passed" in line or " failed" in line]
    return proc.returncode, "\n".join(tail[-6:]), round(time.monotonic() - started, 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tree", required=True)
    ap.add_argument("--basetemp", default="D:/rp_ridge_bt")
    ap.add_argument("ids", nargs="*")
    args = ap.parse_args()
    tree = pathlib.Path(args.tree).resolve()
    probe = subprocess.run([sys.executable, "-c", "import engcore, sys; sys.stdout.write(engcore.__file__)"], cwd=tree,
                           env=dict(os.environ, PYTHONPATH=str(tree / "src")), capture_output=True, text=True)
    if not pathlib.Path(probe.stdout).resolve().is_relative_to(tree / "src"):
        raise SystemExit(f"tests would import {probe.stdout}, not the checkout under test")
    record = {"schema": "thin_ridge_repair_mutations/1", "tree_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=tree, text=True).strip(),
              "targets": TARGETS, "results": {}}
    code, tail, secs = pytest(tree, args.basetemp + "_control")
    record["control"] = {"exit_code": code, "summary": tail, "seconds": secs}
    print("control", code, tail.splitlines()[-1] if tail else "", secs, flush=True)
    if code != 0:
        raise SystemExit("control run is not green; mutations would prove nothing")
    for ident in args.ids or list(MUTATIONS):
        what, rel, old, new = MUTATIONS[ident]
        path = tree / rel
        original = path.read_bytes()
        digest = sha(path)
        text = original.decode("utf-8")
        if text.count(old) != 1:
            raise SystemExit(f"{ident}: target text occurs {text.count(old)} times in {rel}")
        try:
            path.write_bytes(text.replace(old, new).encode("utf-8"))
            code, tail, secs = pytest(tree, f"{args.basetemp}_{ident}")
        finally:
            path.write_bytes(original)
        if sha(path) != digest:
            raise SystemExit(f"{ident}: {rel} was not restored")
        verdict = "KILLED" if code == 1 else "SURVIVED" if code == 0 else f"ERROR(exit {code})"
        record["results"][ident] = {"mutation": what, "file": rel, "verdict": verdict, "exit_code": code, "summary": tail, "seconds": secs}
        print(ident, verdict, secs, "|", tail.splitlines()[0] if tail else "", flush=True)
    out = HERE / "benchmarks" / "core_v1_thin_ridge_repair" / "RIDGE_MUTATIONS.json"
    out.write_bytes((json.dumps(record, indent=1) + "\n").encode("utf-8"))
    killed = sum(r["verdict"] == "KILLED" for r in record["results"].values())
    print(f"{killed}/{len(record['results'])} killed")


if __name__ == "__main__":
    main()
