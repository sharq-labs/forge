"""Part 18: the Core V2 mutation matrix, HD-1..HD-10 -- each applied, tested and reverted.

    python -X utf8 benchmarks/core_v2_hybrid_uq/audit/hd_mutations.py --tree <scratch checkout> [HD-n ...]

Separate from tests/mutation_guards.py (certification-pinned, the certified 79): V2 mutations never join it.
Run against a scratch checkout (a git worktree) with PYTHONPATH set to that checkout's src. A control run with
no mutation must be green. Each mutation must match its target text exactly once. KILLED means pytest ran and
failed (exit 1). Every file is restored byte-for-byte and re-hashed.

Writes benchmarks/core_v2_hybrid_uq/HD_MUTATIONS.json in THIS checkout.
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
PKG = "src/engcore/hybrid_uq/"
TARGETS = ["tests/hybrid_uq", "tests/test_core_v2_compatibility.py"]

MUTATIONS = {
    "HD-1": ("bypass the local-route validity check", PKG + "local_gaussian.py",
             "    claim = claim_for(refusals + downgrades)\n",
             "    refusals, downgrades = [], []\n    claim = claim_for(refusals + downgrades)\n"),
    "HD-2": ("ignore the bound-active refusal", PKG + "local_gaussian.py",
             "    if at_bound:\n        refusals.append(RouteReason.PARAMETER_AT_BOUND)\n",
             "    if False:\n        refusals.append(RouteReason.PARAMETER_AT_BOUND)\n"),
    "HD-3": ("ignore a singular Jacobian", PKG + "local_gaussian.py",
             "    elif condition > NUMERICAL_CONDITION_LIMIT:\n        structural = RouteReason.NUMERICALLY_SINGULAR_JACOBIAN\n",
             "    elif False:\n        structural = RouteReason.NUMERICALLY_SINGULAR_JACOBIAN\n"),
    "HD-4": ("remove the multistart", PKG + "local_gaussian.py",
             "    if multistart is None:\n        uniqueness = \"NOT_ASSESSED\"\n",
             "    if True:\n        uniqueness = \"NOT_ASSESSED\"\n"),
    "HD-5": ("mislabel an approximation as exact", PKG + "vocabulary.py",
             "Neither is the continuous posterior, and no member may say so.\n        return False\n",
             "Neither is the continuous posterior, and no member may say so.\n        return True\n"),
    "HD-6": ("drop parameter uncertainty from the prediction", PKG + "predictive.py",
             "    parameter_var = np.einsum(\"ij,jk,ik->i\", G, cov, G)\n",
             "    parameter_var = np.zeros(G.shape[0])\n"),
    "HD-7": ("merge measurement and parameter uncertainty incorrectly (linear sum)", PKG + "predictive.py",
             "    total_sd = np.asarray([math.sqrt(parameter_var[i] + (m ** 2 if m is not None else 0.0)) for i, m in enumerate(measurement)])\n",
             "    total_sd = np.asarray([parameter_sd[i] + (m if m is not None else 0.0) for i, m in enumerate(measurement)])\n"),
    "HD-8": ("route an unresolved grid as trusted", PKG + "router.py",
             "        try:\n            identifiability = assess_routed_identifiability(grid)\n",
             "        try:\n            identifiability = None\n"),
    "HD-9": ("ignore parameterization identity", PKG + "local_gaussian.py",
             "        identity = digest_of({\"parent\": self.parameterization_digest,",
             "        identity = self.parameterization_digest or digest_of({\"parent\": self.parameterization_digest,"),
    "HD-10": ("predictive UQ accepts a refused local route", PKG + "predictive.py",
              "    cov = posterior._require_numbers()\n    if posterior.parameterization != \"declared\":",
              "    cov = posterior._require_numbers() if posterior.covariance is not None else posterior._design_covariance\n"
              "    if posterior.parameterization != \"declared\":"),
}


def sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pytest(tree: pathlib.Path, basetemp: str):
    env = dict(os.environ, PYTHONPATH=str(tree / "src"), PYTHONDONTWRITEBYTECODE="1")
    started = time.monotonic()
    proc = subprocess.run([sys.executable, "-X", "utf8", "-m", "pytest", *TARGETS, "-q", "-n", "4", "-p", "no:cacheprovider",
                           f"--basetemp={basetemp}"], cwd=tree, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
    tail = [line for line in proc.stdout.splitlines() if line.startswith(("FAILED", "ERROR")) or " passed" in line or " failed" in line]
    return proc.returncode, "\n".join(tail[-8:]), round(time.monotonic() - started, 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tree", required=True)
    ap.add_argument("--basetemp", default="D:/v2_hd_bt")
    ap.add_argument("ids", nargs="*")
    args = ap.parse_args()
    tree = pathlib.Path(args.tree).resolve()
    probe = subprocess.run([sys.executable, "-c", "import engcore, sys; sys.stdout.write(engcore.__file__)"], cwd=tree,
                           env=dict(os.environ, PYTHONPATH=str(tree / "src")), capture_output=True, text=True)
    if not pathlib.Path(probe.stdout).resolve().is_relative_to(tree / "src"):
        raise SystemExit(f"tests would import {probe.stdout}, not the checkout under test")
    stamp = int(time.time())
    record = {"schema": "core_v2_hd_mutations/1", "tree_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=tree, text=True).strip(),
              "targets": TARGETS, "results": {}}
    code, tail, secs = pytest(tree, f"{args.basetemp}_{stamp}_control")
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
            code, tail, secs = pytest(tree, f"{args.basetemp}_{stamp}_{ident}")
        finally:
            path.write_bytes(original)
        if sha(path) != digest:
            raise SystemExit(f"{ident}: {rel} was not restored")
        verdict = "KILLED" if code == 1 else "SURVIVED" if code == 0 else f"ERROR(exit {code})"
        record["results"][ident] = {"mutation": what, "file": rel, "verdict": verdict, "exit_code": code, "summary": tail, "seconds": secs}
        print(ident, verdict, secs, "|", tail.splitlines()[0] if tail else "", flush=True)
    out = HERE / "benchmarks" / "core_v2_hybrid_uq" / "HD_MUTATIONS.json"
    out.write_bytes((json.dumps(record, indent=1) + "\n").encode("utf-8"))
    print(f"{sum(r['verdict'] == 'KILLED' for r in record['results'].values())}/{len(record['results'])} killed")


if __name__ == "__main__":
    main()
