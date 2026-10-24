"""The v3 truth table: computed only after the seal is verified, from two references that must agree.

    reference A  benchmarks.battery_rediscovery_v2.evaluator.reference (GEN1-era protocol, imported unchanged; shares
                 scipy least_squares "trf" and the canonical identifiability classifier with the candidate)
    reference B  evaluator/reference_b.py (variable projection + BVLS + its own recursion and Jacobian; shares only the
                 canonical classifier, and only when a noise is declared)

Per (problem, axis): if A and B give the same truth, that is the truth; otherwise the instance is UNSCORED with basis
``REFERENCE_DISAGREEMENT``.  ``basis_kind`` records how a truth was reached: ``INDEPENDENT_AGREEMENT`` (decided, B
independent of the candidate's numerics), ``CLASSIFIER_SHARED_AGREEMENT`` (an identifiability decision that went through
the canonical classifier, which the candidate also calls: ``implementation_correlated = True``),
``STRUCTURAL_DECLARATION`` (NOT_ASSESSABLE because the pack declares no noise or supplies no set), ``DOMAIN_RULE``
(NOT_ASSESSABLE because a held-out subset passes outside the calibration domain), ``UNSCORED_BY_RULE`` (both references
say marginal).  A process that has computed this table never executes the candidate afterwards: ``extract`` refuses
unless the seal and the sandboxed replay are committed, so the candidate side is closed before truth exists.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess
from typing import Any, Mapping

from benchmarks.battery_rediscovery_v2.candidate.common import load_pack
from benchmarks.battery_rediscovery_v2.evaluator import reference as ref_a

from . import diagnostics, reference_b

ROOT = pathlib.Path(__file__).resolve().parents[3]
HERE = pathlib.Path(__file__).resolve().parents[1]
PACK = HERE / "CandidateBundle"
S, NS, NA = "SUPPORTED", "NOT_SUPPORTED", "NOT_ASSESSABLE"
AXES = reference_b.AXES


class SealNotVerified(RuntimeError):
    pass


def combine_axis(axis: str, a: Mapping[str, Any], b: Mapping[str, Any]) -> dict[str, Any]:
    ta, tb = a.get("truth"), b.get("truth")
    out: dict[str, Any] = {"truth_a": ta, "truth_b": tb, "basis_a": a.get("basis"), "basis_b": b.get("basis")}
    if ta != tb:
        out.update(truth=None, agreement=False, basis_kind="REFERENCE_DISAGREEMENT", implementation_correlated=False)
        return out
    correlated = (ta in (S, NS) and axis == "IDENTIFIABILITY" and bool(b.get("classifier_shared"))
                  and not (b.get("near_structural") or b.get("ambiguous")))
    if ta in (S, NS):
        kind = "CLASSIFIER_SHARED_AGREEMENT" if correlated else "INDEPENDENT_AGREEMENT"
    elif ta == NA:
        kind = "DOMAIN_RULE" if axis in ("WITHIN_CELL_GENERALIZATION", "CROSS_CELL_TRANSFER") and \
            a.get("basis") != "no set supplied" else "STRUCTURAL_DECLARATION"
    else:
        kind = "UNSCORED_BY_RULE"
    out.update(truth=ta, agreement=True, basis_kind=kind, implementation_correlated=correlated)
    return out


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout


def _committed(path: pathlib.Path) -> str:
    rel = str(path.resolve().relative_to(ROOT)).replace("\\", "/")
    commits = _git("log", "--format=%H", "--", rel).split()
    if not commits:
        raise SealNotVerified(f"{rel} is not committed")
    first = subprocess.run(["git", "show", f"{commits[-1]}:{rel}"], cwd=ROOT, capture_output=True, check=True).stdout
    if first != path.read_bytes():
        raise SealNotVerified(f"{rel} differs from the bytes first committed")
    return commits[-1]


def verify_seal(results: pathlib.Path) -> dict[str, Any]:
    seal_path = results / "SEAL.json"
    if not seal_path.exists():
        raise SealNotVerified("no SEAL.json: the candidate outputs are not sealed")
    seal_commit = _committed(seal_path)
    seal = json.loads(seal_path.read_bytes())
    if seal["status"] != "PASS":
        raise SealNotVerified(f"the seal status is {seal['status']}")
    bound = dict(seal["outputs"]); bound.update(seal["access_log"]); bound.update(seal["leakage_pre_seal"])
    for path, sha in bound.items():
        if hashlib.sha256((ROOT / path).read_bytes()).hexdigest() != sha:
            raise SealNotVerified(f"{path} changed after the seal")
    replay = results / "replay" / "REPLAY.json"
    if not replay.exists():
        raise SealNotVerified("the sandboxed replay has not run: the candidate side is not closed")
    replay_commit = _committed(replay)
    return {"seal_sha256": hashlib.sha256(seal_path.read_bytes()).hexdigest(), "seal_commit": seal_commit,
            "replay_commit": replay_commit, "files_bound": len(bound)}


def _a_summary(spec: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Reference A's truth table and fit record from ONE analysis (A's ``_analyse`` is memoised in this process only;
    A's code is not modified)."""
    original = ref_a._analyse
    cache: dict[int, Any] = {}

    def once(s):
        if id(s) not in cache:
            cache[id(s)] = original(s)
        return cache[id(s)]

    ref_a._analyse = once
    try:
        table = ref_a.truth_table(spec)
        fit = ref_a.reference_fit(spec)
    finally:
        ref_a._analyse = original
    best = fit["starts"][fit["best_start"]]
    return table, {"cost": fit["cost"], "parameters": fit["optimum"], "best_status": best["status"],
                   "starts_detail": [{"cost": s["cost"], "final": s["final"], "status": s["status"]} for s in fit["starts"]]}


def problem_truth(spec: Mapping[str, Any]) -> dict[str, Any]:
    a_table, a_fit = _a_summary(spec)
    b_table = reference_b.truth_table(spec)
    combined = {axis: combine_axis(axis, a_table[axis], b_table[axis]) for axis in AXES}
    dims = diagnostics.evidence_dimensions(a_fit, b_table["diagnostics"], b_table,
                                           requested=tuple(spec.get("requested_parameters", ("R0", "R1", "C1"))))
    return {"truth": {axis: combined[axis]["truth"] for axis in AXES}, "combined": combined, "dimensions": dims,
            "reference_a": a_table, "reference_a_fit": a_fit, "reference_b": b_table}


def extract(results: pathlib.Path, pack: pathlib.Path = PACK, problems: list[str] | None = None) -> dict[str, Any]:
    seal = verify_seal(results)
    specs = load_pack(pack)
    out = {}
    for pid in sorted(specs) if problems is None else problems:
        out[pid] = problem_truth(specs[pid])
        print("truth", pid, out[pid]["truth"], flush=True)
    return {"schema": "forge.battery_rediscovery_v3.truth/1", "seal": seal,
            "reference_a_sha256": hashlib.sha256(pathlib.Path(ref_a.__file__).read_bytes()).hexdigest(),
            "reference_b_sha256": hashlib.sha256((HERE / "evaluator" / "reference_b.py").read_bytes()).hexdigest(),
            "table": out}


__all__ = ["SealNotVerified", "combine_axis", "extract", "problem_truth", "verify_seal"]
