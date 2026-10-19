"""Genesis-lite v0.3 freeze-readiness gate (read-only; it never freezes, runs a campaign or edits a tracked file).

    python -m benchmarks.genesis_lite.v0_3.readiness [--approvals PATH]

It runs the v0.3 test files itself (:func:`collect_evidence`) and binds the result to the committed HEAD. A ledger row
counts as FIXED only when every test prefix it names matched at least one PASSING test, and none FAILED, in that run,
on a clean tree at that HEAD. A row's label alone is never evidence.

Statuses, in order of precedence:

* ``BLOCKED_TECHNICAL``: something the code must still fix or prove. Examples: the preregistration does not rebuild;
  an earlier identity moved; the escrow half is missing; evaluator and escrow disagree; a technical row has no passing
  evidence; the one-attempt registry fails its self-test; the evidence is not from a clean committed HEAD.
* ``READY_TO_FREEZE_PENDING_OWNER``: every technical condition holds, but owner decisions, an owner-set value (w, root
  commitment, environment manifest, candidate) or OD-3 are missing. Each reason is listed exactly.
* ``PASS``: everything holds, every decision in :data:`REQUIRED_APPROVALS` is APPROVED for THIS preregistration digest
  (the scoring decision also names the bound w), and OD-3 names this HEAD.

PASS is never reported with a pending owner decision. The approval record is the OWNER's file. This module defines its
shape and never writes it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from typing import Any, Mapping

from .. import preregistration as v02p
from . import evaluator as v03e
from . import preregistration as v03p

PASS, PENDING_OWNER, BLOCKED = "PASS", "READY_TO_FREEZE_PENDING_OWNER", "BLOCKED_TECHNICAL"
FIXED, NOT_A_BLOCKER = "FIXED_AND_TESTED", "NOT_A_REAL_BLOCKER"
BLOCKED_OD3, OWNER = "SPECIFIED_BLOCKED_BY_OD3", "OWNER_DECISION_REQUIRED"
V0_2_SHA256 = "878e6812a825fc85dc1f181b323d9a1c7a630b55e346612ca73d6a5b4e696b64"
APPROVALS_PATH = v03p.PREREG_PATH.with_name("genesis_lite_v0_3.owner_approvals.json")
TEST_FILES = ("tests/genesis_lite/test_genesis_lite_v0_3_amendment.py",
              "tests/genesis_lite/test_genesis_lite_v0_3_blockers.py",
              "tests/genesis_lite/test_genesis_lite_v0_3_escrow_fda05.py")
#: the consolidated owner decision set (decision record section 5)
REQUIRED_APPROVALS = ("D1-scoring", "D2-significance", "D3-baselines-and-tells", "D4-identity-freeze", "D5-deployment",
                      "D6-evaluator", "D7-budget-and-machine", "OD-3")

#: name -> (status, test prefixes that must pass, note). FIXED / NOT_A_BLOCKER rows are verified against evidence.
LEDGER: dict[str, tuple[str, tuple[str, ...], str]] = {
    "FDA-05 evaluator half": (FIXED, ("test_fda05_",), "bracket route bounded; w bound to the preregistration"),
    "FDA-06": (FIXED, ("test_fda06_",), "cap over every law-credit kind incl. indistinguishable"),
    "O-1": (FIXED, ("test_o1_",), "sign-flip p; bootstrap for the bound only; Holm unchanged"),
    "FDA-18 (process memory and temp files)": (FIXED, ("test_fda18_",), "one process and temp dir per card"),
    "FDA-18 residual (same-account files, helper processes)": (
        OWNER, (), "D5 / OD-20: the cross_card_state and persistence attacks must be REFUSED in the deployment"),
    "FDA-19 (Genesis-lite secret inventory)": (FIXED, ("test_fda19_",), "proposer-side secret_scan; the certified "
                                                                        "isolation_probe is not extended"),
    "FDA-21": (FIXED, ("test_fda21_",), "corrected-dof arms ADDED beside the v0.2 arms"),
    "FDA-22": (FIXED, ("test_fda22_",), "tell declared, law_form measured; equalising the priors is a D3 option"),
    "pilot P-1 (always_law)": (NOT_A_BLOCKER, ("test_pilot_p1_",), "solved by the v0.1 joint endpoint"),
    "pilot P-2 (control cells)": (FIXED, ("test_pilot_p2_",), "CONTROL_SOLVED cap"),
    "pilot P-3 (out-of-family share)": (FIXED, ("test_pilot_p3_",), "FDA-06 cap"),
    "readiness P-1/P-2 (isolation deployment, escrow out of process)": (OWNER, (), "D5 / OD-20"),
    "readiness P-3 (attack arms)": (FIXED, ("test_readiness_p3_",), "suite exists; verdicts come from the deployment"),
    "P-4 formal driver, candidate in the attempt": (FIXED, ("test_p4_",), "review 2026-10-20 finding 1"),
    "P-5 environment manifest": (FIXED, ("test_p5_",), "measured inside bind for the formal tier"),
    "one attempt per root": (FIXED, ("test_attempt_",), "registry + publication + post-reveal verify_attempt"),
    "pass route with an arbitrary partner (ODC-05d)": (OWNER, (), "D1"),
    "no preregistered power analysis (review note 13)": (OWNER, (), "D2: the claimable region may be small"),
}


def _escrow_half() -> Any:
    try:
        from engcore.blindfold import pair_bound  # noqa: PLC0415
    except ImportError:
        return None
    return pair_bound


def agreement_cases() -> list[dict[str, Any]]:
    """Evaluator vs escrow on the fixed synthetic R-05 world (:mod:`.selfcheck`); empty without the escrow half."""
    pair_bound = _escrow_half()
    if pair_bound is None:
        return []
    from . import selfcheck  # noqa: PLC0415

    return selfcheck.compare(pair_bound)


def blockers() -> dict[str, tuple[str, tuple[str, ...], str]]:
    rows = dict(LEDGER)
    present = _escrow_half() is not None
    rows["FDA-05 escrow half"] = ((FIXED, ("test_escrow_fda05_",), "engcore.blindfold.pair_bound; UNCERTIFIED (OD-3)")
                                  if present else (BLOCKED_OD3, (), "engcore.blindfold.pair_bound is not in this tree "
                                                   "(branch feat/genesis-lite-v03-escrow-fda05)"))
    rows["v0.3 harness end to end"] = ((FIXED, ("test_harness_",), "binds only with the escrow half") if present
                                       else (BLOCKED_OD3, (), "binds only with the escrow half (no fallback)"))
    return rows


def _git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], cwd=v03p.HERE, capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return ""


def _head() -> str:
    return _git("rev-parse", "HEAD").strip()


def collect_evidence(python: str | None = None) -> dict[str, Any]:
    """Run the v0.3 test files that exist in this tree; return {head, clean, tests: {name: outcome}}."""
    root = v02p.ROOT
    files = [f for f in TEST_FILES if (root / f).is_file()]
    with tempfile.TemporaryDirectory(prefix="gl-readiness-") as d:
        junit = pathlib.Path(d) / "junit.xml"
        subprocess.run([python or sys.executable, "-m", "pytest", *files, "-q", "-p", "no:cacheprovider",
                        f"--junitxml={junit}", f"--basetemp={pathlib.Path(d) / 'bt'}"], cwd=root, capture_output=True,
                       text=True, check=False)
        tests: dict[str, str] = {}
        if junit.is_file():
            for case in ET.parse(junit).getroot().iter("testcase"):
                tags = {child.tag for child in case}
                tests[case.get("name", "")] = ("failed" if tags & {"failure", "error"} else "skipped" if "skipped" in tags
                                               else "passed")
    return {"head": _head(), "clean": _git("status", "--porcelain") == "", "tests": tests}


def _row_verified(prefixes: tuple[str, ...], tests: Mapping[str, str]) -> bool:
    for prefix in prefixes:
        hits = [outcome for name, outcome in tests.items() if name.startswith(prefix)]
        if not hits or any(o != "passed" for o in hits):
            return False
    return bool(prefixes)


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


def check(approvals_path: pathlib.Path | None = None, evidence: Mapping[str, Any] | None = None) -> dict[str, Any]:
    technical, owner = [], []
    committed = v03p.PREREG_PATH.read_bytes()
    prereg_sha = hashlib.sha256(committed).hexdigest()
    technical += [f"identity: {p}" for p in v03p.committed_doc_problems(committed)]
    for path, sha in ((v02p.V0_PREREG_PATH, v02p.V0_PREREG_SHA256), (v02p.V0_1_PREREG_PATH, v02p.V0_1_PREREG_SHA256),
                      (v02p.PREREG_PATH, V0_2_SHA256)):
        if hashlib.sha256(path.read_bytes()).hexdigest() != sha:
            technical.append(f"historical identity moved: {path.name}")
    head = _head()
    if not head:
        technical.append("cannot determine HEAD: evidence and OD-3 cannot be bound")
    if evidence is None:
        technical.append("no test evidence in this invocation (run the CLI, which collects it)")
        tests: Mapping[str, str] = {}
    else:
        tests = evidence.get("tests", {})
        if evidence.get("head") != head or not head or evidence.get("clean") is not True:
            technical.append("the test evidence is not from a clean tree at this HEAD")
    rows = blockers()
    for name, (status, prefixes, note) in sorted(rows.items()):
        if status in (FIXED, NOT_A_BLOCKER):
            if not _row_verified(prefixes, tests):
                technical.append(f"{name}: claimed {status}, but its tests {list(prefixes)} did not all pass here")
        elif status == BLOCKED_OD3:
            technical.append(f"{name}: {status} ({note})")
        else:
            owner.append(f"{name}: {status} ({note})")
    if _escrow_half() is not None:
        owner.append("engcore/blindfold/pair_bound.py is certified scope and UNCERTIFIED: OD-3")
    cases = agreement_cases()
    if cases and not all(c["agree"] for c in cases):
        technical.append(f"evaluator and escrow disagree on {sum(not c['agree'] for c in cases)} synthetic case(s)")
    if not _one_attempt_selftest():
        technical.append("the one-attempt registry admitted a second attempt on one root")
    doc = json.loads(committed)
    for value, why in ((doc["evaluator"]["pair_bound"], "w (pair bound): D1-scoring"),
                       (doc["formal"]["root_commitment_sha256"], "the formal root commitment: generated by the operator "
                                                                 "at freeze, D4"),
                       (doc["formal"]["environment_manifest_sha256"], "the environment manifest: measured on the "
                                                                      "approved machine, D7"),
                       (doc["formal"].get("candidate"), "the candidate (or NONE for a baseline-only attempt): D4")):
        if value == v03p.ODR:
            owner.append(f"{why} is OWNER_DECISION_REQUIRED")
    if doc.get("status") != "FROZEN":
        owner.append(f"identity status is {doc.get('status')!r}: freezing is the owner's act (D4, OD-19)")
    path = approvals_path or APPROVALS_PATH
    record = json.loads(path.read_bytes()) if path.is_file() else {}
    record = record if isinstance(record, Mapping) else {}
    for decision in REQUIRED_APPROVALS:
        entry = record.get(decision)
        ok = (isinstance(entry, Mapping) and entry.get("status") == "APPROVED" and bool(entry.get("choice"))
              and entry.get("prereg_sha256") == prereg_sha)
        if ok and decision == "D1-scoring":
            ok = entry.get("pair_bound") == doc["evaluator"]["pair_bound"] != v03p.ODR
        if ok and decision == "OD-3":
            ok = bool(head) and entry.get("certified_head") == head
        if not ok:
            owner.append(f"owner decision {decision} is not APPROVED for this preregistration ({prereg_sha[:12]}...) "
                         f"in {path.name}")
    status = BLOCKED if technical else PENDING_OWNER if owner else PASS
    return {"status": status, "technical_blockers": technical, "owner_and_certification": owner,
            "agreement_cases": len(cases), "evidence_tests": len(tests), "head": head, "prereg_sha256": prereg_sha,
            "ledger": {k: [v[0], list(v[1]), v[2]] for k, v in sorted(rows.items())},
            "pair_bound": v03e.PAIR_BOUND if not isinstance(v03e.PAIR_BOUND, v03e.PairBound) else v03e.PAIR_BOUND.to_dict()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Genesis-lite v0.3 freeze-readiness gate (read-only)")
    parser.add_argument("--approvals", type=pathlib.Path, default=None, help="the owner's approval record")
    args = parser.parse_args(argv)
    result = check(args.approvals, evidence=collect_evidence())
    sys.stdout.write(json.dumps(result, indent=1, sort_keys=True) + "\n")
    return 0 if result["status"] == PASS else 1


if __name__ == "__main__":
    raise SystemExit(main())
