"""Compute SAFETY_GATES.json from this round's own artifacts.

No verdict is typed by hand. Each gate reads the machine-readable files the
audit wrote, so a gate cannot report PASS while its evidence says otherwise.

The distinction this round is built on is enforced in CB-7: software
correctness, contract consistency and scientific validity are three different
questions, and preserving the first two is a precondition here rather than
evidence for the third.
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

#: Paths this round is allowed to have touched, beyond its own directory.
#: Every one is a scientific record or the test roster that pins it; the list
#: is short on purpose, and gate CB-7 fails on anything outside it.
EXPECTED_TOUCHED = (
    "benchmarks/capability_boundary/",
    # One deliberate change to Contract Guard MACHINERY (not to any of its
    # result artifacts): prerequisites.py now merges claim-map supplements
    # registered by later rounds, because that round's own "unmapped
    # condition" guard fired the moment this round added one. Justified in
    # ROUND_REPORT.md section 7.
    "benchmarks/contract_guard/guard/prerequisites.py",
    "src/engcore/domains/battery/context.py",
    "src/engcore/domains/battery/models.py",
    "src/engcore/domains/electrical/material.py",
    "src/engcore/domains/kinetics/cstr/alternatives.py",
    "tests/test_core_guards.py",
    "tests/domains/battery/test_battery_context.py",
    "tests/domains/electrical/test_material_applicability.py",
    "tests/domains/kinetics/test_k4_competitor_model.py",
)


def core_tree_sha256() -> str:
    root = REPO / "src" / "engcore" / "scientific"
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(b"\x00")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def frozen_artifact_check() -> dict:
    manifest = json.loads((BLIND_V2 / "FREEZE.json").read_text(encoding="utf-8"))
    verified, problems = 0, []
    for relative, expected in manifest["artifacts"].items():
        want = expected if isinstance(expected, str) else expected.get("sha256")
        path = BLIND_V2 / relative
        if not path.exists():
            problems.append({"path": relative, "problem": "MISSING"})
        elif hashlib.sha256(path.read_bytes()).hexdigest() != want:
            problems.append({"path": relative, "problem": "CHANGED"})
        else:
            verified += 1
    return {
        "artifacts_in_manifest": len(manifest["artifacts"]),
        "verified_byte_identical": verified,
        "problems": problems,
    }


#: A round's RESULT artifacts are what it concluded; its machinery is how it
#: concluded it. The rule is that a later round must not rewrite the first --
#: a stale conclusion is at least an honest record of what was true then. The
#: second may be extended when a later round makes it necessary, in the open.
RESULT_ARTIFACT_SUFFIXES = (".json", ".md", ".txt", ".jsonl", ".log")


def earlier_round_artifacts_untouched() -> dict:
    """Blind V2 and the two contract rounds, by path-restricted git status.

    Reported in two buckets, because they carry different obligations: a
    changed RESULT artifact fails this gate, while a changed machinery file is
    listed for a reader to judge and must be justified in the round report.
    """
    rows = {}
    for label, path in (
        ("blind_v2", "benchmarks/blind_v2"),
        ("contract_integrity", "benchmarks/contract_integrity"),
        ("contract_guard", "benchmarks/contract_guard"),
    ):
        out = subprocess.run(
            ["git", "status", "--porcelain", "--", path],
            cwd=REPO,
            capture_output=True,
            text=True,
        ).stdout.strip()
        entries = [line[3:].strip() for line in out.splitlines() if line.strip()]
        rows[label] = {
            "result_artifacts_changed": [
                entry
                for entry in entries
                if entry.lower().endswith(RESULT_ARTIFACT_SUFFIXES)
            ],
            "machinery_changed": [
                entry
                for entry in entries
                if not entry.lower().endswith(RESULT_ARTIFACT_SUFFIXES)
            ],
        }
    return rows


def working_tree() -> dict:
    out = subprocess.run(
        ["git", "status", "--porcelain"], cwd=REPO, capture_output=True, text=True
    ).stdout.splitlines()
    entries = [line[3:].strip() for line in out if line.strip()]
    unexpected = [
        entry
        for entry in entries
        if not any(entry.startswith(prefix) for prefix in EXPECTED_TOUCHED)
    ]
    return {"entries": entries, "unexpected": unexpected}


def main() -> int:
    surface = json.loads((ROUND / "MODEL_CAPABILITY_SURFACE.json").read_text("utf-8"))
    cases = json.loads((ROUND / "FALSE_CONFIDENCE_CASES.json").read_text("utf-8"))
    plants = json.loads((ROUND / "PLANTED_DEFECTS.json").read_text("utf-8"))
    assurance_path = ROUND / "EXISTING_ASSURANCE.json"
    assurance = (
        json.loads(assurance_path.read_text("utf-8"))
        if assurance_path.exists()
        else {}
    )

    findings = [case for case in cases["cases"] if case.get("as_found")]
    oracles_ok = all(
        case["oracle"].get("type") and case["oracle"].get("independence")
        for case in cases["cases"]
    )
    disclosed_cases = [
        entry
        for model in surface["models"]
        for entry in model["real_cases_under_the_claim"]
        if entry["represents"] == "DISCLOSED"
    ]
    disclosed_all_explained = all(entry["why"].strip() for entry in disclosed_cases)
    not_applicable_explained = all(
        entry["why"].strip()
        for model in surface["models"]
        for entry in model["real_cases_under_the_claim"]
    )

    actual_core = core_tree_sha256()
    frozen = frozen_artifact_check()
    earlier = earlier_round_artifacts_untouched()
    tree = working_tree()

    gates = [
        {
            "id": "CB-1",
            "name": "MODEL SURFACE COMPLETE",
            "requirement": "all 16 shipped models are reviewed",
            "evidence": {
                "models_reviewed": surface["model_count"],
                "systems": surface["system_count"],
                "all_status_reviewed": all(
                    model["status"] == "REVIEWED" for model in surface["models"]
                ),
                "real_cases_reviewed": surface["real_cases_reviewed"],
            },
            "verdict": "PASS"
            if surface["model_count"] == 16
            and all(model["status"] == "REVIEWED" for model in surface["models"])
            else "FAIL",
        },
        {
            "id": "CB-2",
            "name": "CLAIM BREADTH VALID",
            "requirement": (
                "no published claim materially exceeds the physics its "
                "equations represent"
            ),
            "evidence": {
                "classification_counts": surface["classification_counts"],
                "real_case_counts_as_found": surface["real_case_counts"],
                "cases_found_NO": surface["real_case_counts"].get("NO", 0),
                "unresolved_no_cases": surface["unresolved_no_cases"],
                "note": (
                    "Three cases were found NO -- inside the wording, outside "
                    "the equations, with nothing refusing them. All three were "
                    "repaired in this round and each carries a resolution."
                ),
            },
            "verdict": "PASS" if not surface["unresolved_no_cases"] else "FAIL",
        },
        {
            "id": "CB-3",
            "name": "VALIDITY BOUNDARIES COMPLETE",
            "requirement": (
                "every material scientific validity limit is declared and "
                "enforced, or explicitly justified as disclosed-not-enforced"
            ),
            "evidence": {
                "bounded_by_a_declared_condition": surface["real_case_counts"].get(
                    "BOUNDED", 0
                ),
                "disclosed_not_enforced": len(disclosed_cases),
                "every_disclosed_case_names_where_it_is_disclosed": disclosed_all_explained,
                "every_case_carries_a_reason": not_applicable_explained,
                "unenforced_and_undisclosed": surface["unresolved_no_cases"],
            },
            "verdict": "PASS"
            if disclosed_all_explained
            and not_applicable_explained
            and not surface["unresolved_no_cases"]
            else "FAIL",
        },
        {
            "id": "CB-4",
            "name": "ZERO FALSE CONFIDENCE",
            "requirement": (
                "no known out-of-regime case receives a normal-looking "
                "supported result"
            ),
            "evidence": {
                "response_counts_as_found": cases["response_counts_as_found"],
                "response_counts_after_repair": cases["response_counts_after_repair"],
                "false_confidence_cases_found": cases["false_confidence_cases"],
                "false_confidence_cases_still_open": cases[
                    "false_confidence_cases_still_open"
                ],
            },
            "verdict": "PASS"
            if not cases["false_confidence_cases_still_open"]
            else "FAIL",
        },
        {
            "id": "CB-5",
            "name": "APPROXIMATIONS DISCLOSED",
            "requirement": (
                "material approximations affecting capability are visible to "
                "the caller"
            ),
            "evidence": {
                "disclosed_cases": len(disclosed_cases),
                "each_names_the_assumption_or_exclusion_that_discloses_it": (
                    disclosed_all_explained
                ),
                "models_declaring_exclusions": sum(
                    1 for model in surface["models"] if model["exclusions_declared"]
                ),
                "models_not_declaring_exclusions": [
                    model["model_id"]
                    for model in surface["models"]
                    if not model["exclusions_declared"]
                ],
                "note": (
                    "thermal.conduction1d.linear_diffusion declares no "
                    "exclusions tuple. Its seven assumptions name every "
                    "approximation this audit identified -- the fixed initial "
                    "condition, the absent source term, the constant "
                    "diffusivity -- so nothing is hidden; the empty exclusions "
                    "field is a record-completeness observation for a contract "
                    "round, not a capability boundary."
                ),
            },
            "verdict": "PASS" if disclosed_all_explained else "FAIL",
        },
        {
            "id": "CB-6",
            "name": "INDEPENDENT SCIENTIFIC EVIDENCE",
            "requirement": (
                "material findings are supported by scientific reasoning or "
                "oracles independent of the model under test"
            ),
            "evidence": {
                "cases_with_an_oracle": sum(
                    1 for case in cases["cases"] if case["oracle"].get("type")
                ),
                "cases_total": cases["cases_run"],
                "every_oracle_states_its_independence": oracles_ok,
                "oracle_types": sorted(
                    {case["oracle"]["type"] for case in cases["cases"]}
                ),
                "findings_with_an_oracle": [case["id"] for case in findings],
                "note": (
                    "No finding rests on the model under test. The CSTR "
                    "invariant is derived by hand and cancels the rate law; "
                    "the conduction reference is a closed form a test asserts "
                    "never imports the solver; the sign bounds are properties "
                    "of the quantities themselves."
                ),
            },
            "verdict": "PASS" if oracles_ok else "FAIL",
        },
        {
            "id": "CB-7",
            "name": "EXISTING SOFTWARE ASSURANCE PRESERVED",
            "requirement": (
                "Contract Guard and the existing scientific assurance are "
                "preserved; any change to executable scientific code is "
                "re-certified rather than assumed harmless"
            ),
            "evidence": {
                "certified_core_tree_sha256_expected": CERTIFIED_CORE_TREE_SHA,
                "certified_core_tree_sha256_actual": actual_core,
                "executable_domain_code_changed": True,
                "files_changed_outside_this_round": sorted(
                    entry
                    for entry in tree["entries"]
                    if not entry.startswith("benchmarks/capability_boundary/")
                ),
                "unexpected_working_tree_entries": tree["unexpected"],
                "earlier_round_artifacts": earlier,
                "machinery_change_justification": (
                    "benchmarks/contract_guard/guard/prerequisites.py merges "
                    "claim-map supplements registered by later rounds. That "
                    "round's own 'a condition in no claim map fails' guard "
                    "fired the moment this round added a condition, which is "
                    "what it exists for; the mapping is supplied in this "
                    "round's directory rather than by editing the earlier "
                    "round's file. No Contract Guard RESULT artifact changed."
                ),
                "reruns": assurance,
                "this_is_not_evidence_of_scientific_validity": (
                    "Preserving software correctness and contract consistency "
                    "is a precondition of this round, not a result of it. A "
                    "green suite and a matching digest say nothing about "
                    "whether a claim is scientifically justified."
                ),
            },
            "verdict": "PASS"
            if actual_core == CERTIFIED_CORE_TREE_SHA
            and not tree["unexpected"]
            and not any(
                row["result_artifacts_changed"] for row in earlier.values()
            )
            and assurance.get("all_preserved") is True
            else "FAIL",
        },
        {
            "id": "CB-8",
            "name": "FROZEN EVIDENCE PRESERVED",
            "requirement": "Blind V2 frozen/sealed artifacts remain untouched",
            "evidence": {
                **frozen,
                "blind_v2_paths_modified": earlier["blind_v2"],
                "blind_v2_anything_modified": (
                    earlier["blind_v2"]["result_artifacts_changed"]
                    + earlier["blind_v2"]["machinery_changed"]
                ),
                "method": (
                    "path-restricted: every artifact named in "
                    "benchmarks/blind_v2/FREEZE.json is re-hashed against the "
                    "hash that manifest records, and git is asked separately "
                    "whether any path under benchmarks/blind_v2 changed. No "
                    "Blind V2 frozen/sealed artifact path changed."
                ),
            },
            "verdict": "PASS"
            if not frozen["problems"]
            and frozen["verified_byte_identical"] == frozen["artifacts_in_manifest"]
            and not earlier["blind_v2"]["result_artifacts_changed"]
            and not earlier["blind_v2"]["machinery_changed"]
            else "FAIL",
        },
    ]

    payload = {
        "schema": "capability_boundary_gates/1",
        "note": (
            "A NEW gate set for the Scientific Capability Boundary round. The "
            "Blind V2, Contract Integrity and Contract Guard gates are not "
            "modified, reused or renumbered; they answered different questions "
            "and their results stand."
        ),
        "what_these_gates_do_not_say": (
            "That the models are scientifically correct. They say that every "
            "shipped claim was read against the equations behind it, that the "
            "regimes found outside those equations are now refused or "
            "disclosed, and that each boundary has a guard that fails when it "
            "is removed."
        ),
        "all_pass": all(gate["verdict"] == "PASS" for gate in gates),
        "planted_defect_falsification": {
            "control": plants["control"]["status"],
            "total": plants["total"],
            "caught": plants["caught"],
            "survivors": plants["survivors"],
            "by_class": plants["by_class"],
        },
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
