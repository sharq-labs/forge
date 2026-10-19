"""Genesis-lite v0.3 freeze-readiness gate (read-only; it never freezes, runs a campaign or edits a file).

    python -m benchmarks.genesis_lite.v0_3.readiness [--approvals PATH]

Statuses, in order of precedence:

* ``BLOCKED_TECHNICAL``: something the code must still fix. Examples: the preregistration does not rebuild, an
  earlier identity moved, the escrow half is missing, evaluator and escrow disagree, a technical blocker is open, or
  the one-attempt registry fails its self-test.
* ``READY_TO_FREEZE_PENDING_OWNER``: every technical condition holds, but owner decisions, an owner-set value
  (w, root commitment, environment manifest) or OD-3 are still missing. Each reason is listed exactly.
* ``PASS``: everything holds, every listed owner decision is APPROVED in the owner's approval record, and OD-3 names
  this HEAD.

PASS is never reported with a pending owner decision. The approval record is the OWNER's file. This module defines its
shape (:data:`REQUIRED_APPROVALS`) and never writes it. An approval is a scoped owner act; the gate only reads one.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile
from typing import Any, Mapping

from .. import preregistration as v02p
from . import evaluator as v03e
from . import preregistration as v03p

PASS, PENDING_OWNER, BLOCKED = "PASS", "READY_TO_FREEZE_PENDING_OWNER", "BLOCKED_TECHNICAL"
FIXED, NOT_A_BLOCKER = "FIXED_AND_TESTED", "NOT_A_REAL_BLOCKER"
BLOCKED_OD3, OWNER = "SPECIFIED_BLOCKED_BY_OD3", "OWNER_DECISION_REQUIRED"
V0_2_SHA256 = "878e6812a825fc85dc1f181b323d9a1c7a630b55e346612ca73d6a5b4e696b64"
APPROVALS_PATH = v03p.PREREG_PATH.with_name("genesis_lite_v0_3.owner_approvals.json")
#: the consolidated owner decision set (decision record §5); an approval names the chosen option
REQUIRED_APPROVALS = ("D1-scoring", "D2-significance", "D3-baselines-and-tells", "D4-identity-freeze", "D5-deployment",
                      "D6-evaluator", "D7-budget-and-machine", "OD-3")

#: the freeze-blocker ledger: (status, evidence). Statuses are FIXED_AND_TESTED, NOT_A_REAL_BLOCKER,
#: SPECIFIED_BLOCKED_BY_OD3 or OWNER_DECISION_REQUIRED; the escrow row is computed (see :func:`blockers`).
LEDGER: dict[str, tuple[str, str]] = {
    "FDA-05 evaluator half": (FIXED, "test_fda05_* (v0.3 amendment tests)"),
    "FDA-06": (FIXED, "test_fda06_*"),
    "O-1": (FIXED, "test_o1_*"),
    "FDA-18": (FIXED, "test_fda18_* (fresh proposer per card); residual: same-account persistent storage -> OD-20"),
    "FDA-21": (FIXED, "test_fda21_* (n - p - 1 residual dof, mean-zero replicate noise)"),
    "FDA-22": (FIXED, "test_fda22_* (tell declared and law_form measured per universe); equalising the generator "
                      "priors is an owner option on certified universe.py"),
    "pilot P-1 (always_law)": (NOT_A_BLOCKER, "test_pilot_p1_*: solved by the v0.1 joint endpoint and comparison set"),
    "pilot P-2 (control cells)": (FIXED, "test_pilot_p2_* (CONTROL_SOLVED cap)"),
    "pilot P-3 (out-of-family share)": (FIXED, "test_pilot_p3_* (FDA-06 cap)"),
    "readiness P-1/P-2 (isolation deployment, escrow out of process)": (OWNER, "OD-20: needs a chosen deployment"),
    "readiness P-3 (attack arms)": (FIXED, "test_readiness_p3_* (deployment_attacks); REFUSED verdicts are measured in "
                                          "the OD-20 deployment"),
    "P-4 formal driver": (FIXED, "test_p4_*"),
    "P-5 environment manifest": (FIXED, "test_p5_*"),
    "one attempt per root": (FIXED, "test_attempt_*"),
    "FDA-19 probe scope": (BLOCKED_OD3, "certified isolation_probe.py; specified in the decision record section 6"),
}


def _escrow_half() -> Any:
    try:
        from engcore.blindfold import pair_bound  # noqa: PLC0415
    except ImportError:
        return None
    return pair_bound


def agreement_cases() -> list[dict[str, Any]]:
    """Evaluator vs escrow on the fixed synthetic R-05 world: the vacuous pair, the honest pair, a narrow bracket and an
    in-box-disagreeing pair, under several bounds. Empty when the escrow half is absent."""
    pair_bound = _escrow_half()
    if pair_bound is None:
        return []
    from . import selfcheck  # noqa: PLC0415

    return selfcheck.compare(pair_bound)


def blockers() -> dict[str, tuple[str, str]]:
    rows = dict(LEDGER)
    escrow = _escrow_half()
    rows["FDA-05 escrow half"] = ((BLOCKED_OD3, "engcore.blindfold.pair_bound is not in this tree (prepared on branch "
                                               "feat/genesis-lite-v03-escrow-fda05; certified, OD-3)")
                                  if escrow is None else (FIXED, "test_escrow_fda05_* and readiness agreement cases; "
                                                                 "UNCERTIFIED until OD-3"))
    rows["v0.3 harness"] = ((BLOCKED_OD3, "binds only with the escrow half (no fallback)") if escrow is None
                            else (FIXED, "test_harness_*"))
    return rows


def _one_attempt_selftest() -> bool:
    from .registry import AttemptRefused, AttemptRegistry  # noqa: PLC0415

    with tempfile.TemporaryDirectory(prefix="gl-registry-selftest-") as d:
        digest = hashlib.sha256(b"selftest").hexdigest()
        kwargs = {"root_commitment_sha256": digest, "prereg_sha256": digest, "campaign_set_sha256": digest}
        AttemptRegistry(pathlib.Path(d)).admit(tier="formal", **kwargs)
        for tier in ("formal", "development"):
            try:
                AttemptRegistry(pathlib.Path(d)).admit(tier=tier, **kwargs)
            except AttemptRefused:
                continue
            return False
        return True


def _head() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=v03p.HERE, capture_output=True, text=True,
                              check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def check(approvals_path: pathlib.Path | None = None) -> dict[str, Any]:
    technical, owner = [], []
    committed = v03p.PREREG_PATH.read_bytes()
    technical += [f"identity: {p}" for p in v03p.committed_doc_problems(committed)]
    for path, sha in ((v02p.V0_PREREG_PATH, v02p.V0_PREREG_SHA256), (v02p.V0_1_PREREG_PATH, v02p.V0_1_PREREG_SHA256),
                      (v02p.PREREG_PATH, V0_2_SHA256)):
        if hashlib.sha256(path.read_bytes()).hexdigest() != sha:
            technical.append(f"historical identity moved: {path.name}")
    rows = blockers()
    for name, (status, evidence) in sorted(rows.items()):
        if status == BLOCKED_OD3:
            (technical if name in ("FDA-05 escrow half", "v0.3 harness") else owner).append(
                f"{name}: {status} ({evidence})")
        elif status == OWNER:
            owner.append(f"{name}: {status} ({evidence})")
        elif status not in (FIXED, NOT_A_BLOCKER):
            technical.append(f"{name}: {status}")
    cases = agreement_cases()
    if cases and not all(c["agree"] for c in cases):
        technical.append(f"evaluator and escrow disagree on {sum(not c['agree'] for c in cases)} synthetic case(s)")
    if not _one_attempt_selftest():
        technical.append("the one-attempt registry admitted a second attempt on one root")
    doc = json.loads(committed)
    if doc["evaluator"]["pair_bound"] == v03p.ODR:
        owner.append("w (pair bound) is OWNER_DECISION_REQUIRED (D1-scoring)")
    if doc["formal"]["root_commitment_sha256"] == v03p.ODR:
        owner.append("the formal root commitment is not set (generated by the operator at freeze, D4)")
    if doc["formal"]["environment_manifest_sha256"] == v03p.ODR:
        owner.append("the environment manifest is not bound (measured on the owner-approved machine, D7)")
    if doc.get("status") != "FROZEN":
        owner.append(f"identity status is {doc.get('status')!r}: freezing is the owner's act (D4, OD-19)")
    path = approvals_path or APPROVALS_PATH
    record = json.loads(path.read_bytes()) if path.is_file() else {}
    for decision in REQUIRED_APPROVALS:
        entry = record.get(decision) if isinstance(record, Mapping) else None
        if not (isinstance(entry, Mapping) and entry.get("status") == "APPROVED" and entry.get("choice")):
            owner.append(f"owner decision {decision} is not APPROVED in {path.name}")
    od3 = record.get("OD-3") if isinstance(record, Mapping) else None
    if isinstance(od3, Mapping) and od3.get("status") == "APPROVED" and od3.get("certified_head") != _head():
        owner.append("OD-3 names another HEAD than this tree's")
    status = BLOCKED if technical else PENDING_OWNER if owner else PASS
    return {"status": status, "technical_blockers": technical, "owner_and_certification": owner,
            "agreement_cases": len(cases), "ledger": {k: list(v) for k, v in sorted(rows.items())},
            "prereg_sha256": hashlib.sha256(committed).hexdigest(), "pair_bound": v03e.PAIR_BOUND
            if not isinstance(v03e.PAIR_BOUND, v03e.PairBound) else v03e.PAIR_BOUND.to_dict()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Genesis-lite v0.3 freeze-readiness gate (read-only)")
    parser.add_argument("--approvals", type=pathlib.Path, default=None, help="the owner's approval record")
    args = parser.parse_args(argv)
    result = check(args.approvals)
    sys.stdout.write(json.dumps(result, indent=1, sort_keys=True) + "\n")
    return 0 if result["status"] == PASS else 1


if __name__ == "__main__":
    raise SystemExit(main())
