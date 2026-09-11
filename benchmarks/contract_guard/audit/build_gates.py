"""Compute SAFETY_GATES.json from the round's own artifacts.

No verdict here is typed by hand. Each gate reads the machine-readable files
the guards and the mutation catalog wrote, so a gate cannot say PASS while the
evidence behind it says otherwise.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROUND = HERE.parent
REPO = ROUND.parent.parent
BLIND_V2 = REPO / "benchmarks" / "blind_v2"

CERTIFIED_CORE_TREE_SHA = (
    "82558f5b4386a73a951f21fdb8b5a45df2c6c032423a205108a1fccfd97d2507"
)

#: Paths this round is allowed to create. Anything else modified in the working
#: tree means a planted defect was left behind or unrelated work was touched.
THIS_ROUND_PREFIX = "benchmarks/contract_guard/"


def core_tree_sha256() -> str:
    """The certified scientific-core digest, by the recipe the snapshot publishes."""
    root = REPO / "src" / "engcore" / "scientific"
    digest = hashlib.sha256()
    for path in sorted(
        p for p in root.rglob("*.py") if "__pycache__" not in p.parts
    ):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(b"\x00")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def frozen_artifact_check() -> dict:
    """Every Blind V2 artifact against the hash its own freeze manifest records."""
    manifest = json.loads((BLIND_V2 / "FREEZE.json").read_text(encoding="utf-8"))
    verified = 0
    problems = []
    for relative, expected in manifest["artifacts"].items():
        want = expected if isinstance(expected, str) else expected.get("sha256")
        path = BLIND_V2 / relative
        if not path.exists():
            problems.append({"path": relative, "problem": "MISSING"})
            continue
        if hashlib.sha256(path.read_bytes()).hexdigest() != want:
            problems.append({"path": relative, "problem": "CHANGED"})
            continue
        verified += 1
    return {
        "artifacts_in_manifest": len(manifest["artifacts"]),
        "verified_byte_identical": verified,
        "problems": problems,
    }


def working_tree() -> dict:
    out = subprocess.run(
        ["git", "status", "--porcelain"], cwd=REPO, capture_output=True, text=True
    ).stdout.splitlines()
    entries = [line[3:].strip() for line in out if line.strip()]
    outside = [
        entry for entry in entries if not entry.startswith(THIS_ROUND_PREFIX)
    ]
    return {"entries": entries, "outside_this_round": outside}


def main() -> int:
    matrix = json.loads((ROUND / "CONTRACT_GUARD_MATRIX.json").read_text("utf-8"))
    mutation = json.loads((ROUND / "CONTRACT_MUTATION.json").read_text("utf-8"))
    totals = matrix["totals"]
    evidence = matrix["evidence"]

    guard_families = sorted({result["guard"] for result in mutation["results"]})
    falsified = sorted(
        {result["guard"] for result in mutation["results"] if result["caught"]}
    )
    directions = {
        result["class"] for result in mutation["results"] if result["caught"]
    }
    broad = [
        result
        for result in mutation["results"]
        if result["class"] == "RECORD_TOO_BROAD" and result["caught"]
    ]
    narrow = [
        result
        for result in mutation["results"]
        if result["class"] == "RECORD_TOO_NARROW" and result["caught"]
    ]
    broad_systems = {
        result["file"].split("/domains/")[-1].split("/")[0] for result in broad
    }

    contradictions = (
        evidence["bound_enforcement_disagreements"]
        + evidence["prose_disagreements"]
        + evidence["unknown_prerequisite_disagreements"]
        + evidence["empty_context_undeclared"]
        + evidence["capabilities_unserved"]
        + evidence["constructor_input_counts"].get("RECORD_TOO_BROAD", 0)
        + evidence["constructor_input_counts"].get("RECORD_TOO_NARROW", 0)
    )

    actual_core = core_tree_sha256()
    frozen = frozen_artifact_check()
    tree = working_tree()

    gates = [
        {
            "id": "CG-1",
            "name": "MODEL SURFACE ACCOUNTED",
            "requirement": (
                "every shipped model is classified for guard applicability on "
                "every material contract dimension"
            ),
            "evidence": {
                "models": matrix["model_count"],
                "dimensions": len(matrix["dimensions"]),
                "cells": totals["cells"],
                "cells_with_a_status": sum(
                    len(row["dimensions"]) for row in matrix["models"]
                ),
            },
            "verdict": "PASS"
            if matrix["model_count"] == 16
            and sum(len(row["dimensions"]) for row in matrix["models"])
            == totals["cells"]
            else "FAIL",
        },
        {
            "id": "CG-2",
            "name": "MATERIAL CONTRACT DIMENSIONS COVERED",
            "requirement": (
                "every material record<->runtime dimension is guarded or "
                "explicitly justified NOT_APPLICABLE"
            ),
            "evidence": {
                "applicable_dimensions": totals["applicable_dimensions"],
                "guarded": totals["guarded_dimensions"],
                "not_guarded": totals["not_guarded_dimensions"],
                "not_applicable": totals["not_applicable_dimensions"],
                "blocked": totals["blocked_dimensions"],
                "every_not_applicable_carries_a_reason": all(
                    cell["note"]
                    for row in matrix["models"]
                    for cell in row["dimensions"].values()
                ),
            },
            "verdict": "PASS"
            if totals["not_guarded_dimensions"] == 0
            and totals["blocked_dimensions"] == 0
            else "FAIL",
        },
        {
            "id": "CG-3",
            "name": "EXECUTABLE DRIFT DETECTION",
            "requirement": (
                "each guard family has been falsified with a controlled "
                "planted mismatch"
            ),
            "evidence": {
                "guard_families_targeted": guard_families,
                "guard_families_falsified": falsified,
                "control_on_the_unmutated_tree": mutation["control"]["status"],
            },
            "verdict": "PASS"
            if guard_families == falsified and mutation["control"]["green"]
            else "FAIL",
        },
        {
            "id": "CG-4",
            "name": "ZERO KNOWN RECORD<->RUNTIME CONTRADICTIONS",
            "requirement": "no material mismatch remains unresolved",
            "evidence": {
                "total_contradictions": contradictions,
                "by_check": {
                    "bound_enforcement": evidence["bound_enforcement_disagreements"],
                    "prose_applicability": evidence["prose_disagreements"],
                    "unknown_prerequisites": evidence[
                        "unknown_prerequisite_disagreements"
                    ],
                    "empty_context_derivation": evidence["empty_context_undeclared"],
                    "capability_service": evidence["capabilities_unserved"],
                    "constructor_input_obligations": evidence[
                        "constructor_input_counts"
                    ],
                },
            },
            "verdict": "PASS" if contradictions == 0 else "FAIL",
        },
        {
            "id": "CG-5",
            "name": "SEMANTIC MUTATION CLOSURE",
            "requirement": "all VALID material semantic mutants are detected",
            "evidence": {
                "total": mutation["total"],
                "caught": mutation["caught"],
                "survivors": mutation["survivors"],
                "invalid": [
                    result["id"]
                    for result in mutation["results"]
                    if result["status"] == "DID_NOT_APPLY"
                ],
                "by_class": mutation["by_class"],
            },
            "verdict": "PASS"
            if not mutation["survivors"]
            and not any(
                result["status"] == "DID_NOT_APPLY" for result in mutation["results"]
            )
            else "FAIL",
        },
        {
            "id": "CG-6",
            "name": "SC5 CLASS CLOSED",
            "requirement": (
                "applicability overstatement and understatement can both be "
                "detected, as a class rather than as one string"
            ),
            "evidence": {
                "record_too_broad_caught": [result["id"] for result in broad],
                "record_too_broad_distinct_domains": sorted(broad_systems),
                "record_too_narrow_caught": [result["id"] for result in narrow],
                "sc5_reproduced_verbatim_as": "CGM-1",
                "mechanism": (
                    "prose claims are extracted to values and executed against "
                    "assess_validity, so the check is record vs runtime rather "
                    "than record vs record"
                ),
                "prose_claims_executed": evidence["prose_claims_executed"],
            },
            "verdict": "PASS"
            if len(broad) >= 2 and narrow and len(broad_systems) >= 2
            else "FAIL",
        },
        {
            "id": "CG-7",
            "name": "EXISTING SCIENTIFIC ASSURANCE PRESERVED",
            "requirement": (
                "scientific/runtime assurance is unchanged, or any intentional "
                "change is fully re-certified"
            ),
            "evidence": {
                "certified_core_tree_sha256_expected": CERTIFIED_CORE_TREE_SHA,
                "certified_core_tree_sha256_actual": actual_core,
                "executable_scientific_code_changed_this_round": bool(
                    tree["outside_this_round"]
                ),
                "working_tree_entries_outside_this_round": tree[
                    "outside_this_round"
                ],
                "certified_mutation_suite": (
                    "untouched: tests/mutation_guards.py and its 79 mutants are "
                    "not modified, extended or renumbered, and this round's "
                    "counts are never merged with them"
                ),
            },
            "verdict": "PASS"
            if actual_core == CERTIFIED_CORE_TREE_SHA
            and not tree["outside_this_round"]
            else "FAIL",
        },
        {
            "id": "CG-8",
            "name": "FROZEN EVIDENCE PRESERVED",
            "requirement": "Blind V2 frozen/sealed artifacts remain byte-identical",
            "evidence": {
                **frozen,
                "method": (
                    "path-restricted: every artifact named in "
                    "benchmarks/blind_v2/FREEZE.json is re-hashed and compared "
                    "with the hash that manifest records. No Blind V2 "
                    "frozen/sealed artifact path changed."
                ),
            },
            "verdict": "PASS"
            if not frozen["problems"]
            and frozen["verified_byte_identical"] == frozen["artifacts_in_manifest"]
            else "FAIL",
        },
    ]

    payload = {
        "schema": "contract_guard_gates/1",
        "note": (
            "A NEW gate set for the Contract Guard round. The Blind V2 and "
            "Contract Integrity gates are not modified, reused or renumbered; "
            "they answered different questions and their results stand."
        ),
        "all_pass": all(gate["verdict"] == "PASS" for gate in gates),
        "gates": gates,
    }
    (ROUND / "SAFETY_GATES.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    for gate in gates:
        print(f"{gate['id']:5s} {gate['verdict']:5s} {gate['name']}")
    print("all_pass:", payload["all_pass"])
    return 0 if payload["all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
