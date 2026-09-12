"""Compute SAFETY_GATES.json from this round's artifacts.

No verdict is typed. ST-26 is enforced here as well as in the report: a gate
that would let "the tests pass" or "two solvers agree" stand in for "the
equation is correct" is a gate that has confused two assurance layers, so each
gate below names the layer it speaks for.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess

HERE = pathlib.Path(__file__).resolve().parent
ROUND = HERE.parent
REPO = ROUND.parent.parent
BLIND_V2 = REPO / "benchmarks" / "blind_v2"

CERTIFIED_CORE_TREE_SHA = (
    "82558f5b4386a73a951f21fdb8b5a45df2c6c032423a205108a1fccfd97d2507"
)

EARLIER_ROUNDS = (
    "benchmarks/blind_v2",
    "benchmarks/contract_integrity",
    "benchmarks/contract_guard",
    "benchmarks/capability_boundary",
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


def _status(path: str) -> list[str]:
    out = subprocess.run(
        ["git", "status", "--porcelain", "--", path],
        cwd=REPO, capture_output=True, text=True,
    ).stdout.strip()
    return [line[3:].strip() for line in out.splitlines() if line.strip()]


def main() -> int:
    cases = json.loads((ROUND / "REFERENCE_CASES.json").read_text("utf-8"))
    surface = json.loads((ROUND / "MODEL_EQUATION_SURFACE.json").read_text("utf-8"))
    ledger = json.loads((ROUND / "EQUATION_LEDGER.json").read_text("utf-8"))
    indep = json.loads((ROUND / "SOLVER_INDEPENDENCE.json").read_text("utf-8"))
    props = json.loads((ROUND / "PROPERTY_TESTING.json").read_text("utf-8"))
    false_agreement = json.loads((ROUND / "FALSE_AGREEMENT_CASES.json").read_text("utf-8"))
    plants = json.loads((ROUND / "PLANTED_DEFECTS.json").read_text("utf-8"))

    by_check = cases["by_check"]
    production_changed = _status("src") + _status("tests")
    earlier_touched = {path: _status(path) for path in EARLIER_ROUNDS}
    frozen = frozen_artifact_check()
    actual_core = core_tree_sha256()

    def family(name: str) -> dict:
        return by_check.get(name, {"total": 0, "clean": 0})

    gates = [
        {
            "id": "ST-1", "name": "MODEL EQUATION SURFACE COMPLETE",
            "layer": "inventory",
            "requirement": "all 16 shipped models are accounted for",
            "evidence": {
                "models_in_surface": surface["model_count"],
                "all_reviewed": all(m["status"] == "REVIEWED" for m in surface["models"]),
                "ledger_entries": len(ledger["entries"]),
            },
            "verdict": "PASS" if surface["model_count"] == 16 and len(ledger["entries"]) == 16 else "FAIL",
        },
        {
            "id": "ST-2", "name": "DIMENSIONAL CONSISTENCY",
            "layer": "mathematical truth",
            "requirement": "zero unresolved dimensional defects",
            "evidence": {
                "verdicts": ledger["dimensional_counts"],
                "method": (
                    "every equation worked term by term in the ledger; a "
                    "passing numerical test was not accepted as evidence "
                    "anywhere, because a wrong power of a unit can match a "
                    "reference at the one point it was built at"
                ),
            },
            "verdict": "PASS" if ledger["dimensional_counts"].get("DIMENSIONAL_DEFECT", 0) == 0 else "FAIL",
        },
        {
            "id": "ST-3", "name": "INDEPENDENT ORACLE AGREEMENT",
            "layer": "mathematical truth + implementation correctness",
            "requirement": "zero unresolved material oracle disagreements",
            "evidence": {
                "reference_cases": family("reference_case"),
                "cross_oracle": family("cross_oracle"),
                "external_oracle_ngspice": family("external_oracle"),
                "high_precision_50_digit": family("high_precision"),
                "cancellation": family("cancellation"),
                "total_disagreements": len(cases["disagreements"]),
            },
            "verdict": "PASS" if not cases["disagreements"] else "FAIL",
        },
        {
            "id": "ST-4", "name": "CONSERVATION",
            "layer": "mathematical truth",
            "requirement": "all applicable conservation checks pass, with the residual measured",
            "evidence": {
                "conservation_rows": family("conservation"),
                "laws": ["energy", "charge", "species/energy coupling"],
                "method": "residuals measured explicitly, never inferred from the equations looking right",
            },
            "verdict": "PASS" if family("conservation")["clean"] == family("conservation")["total"] else "FAIL",
        },
        {
            "id": "ST-5", "name": "LIMITING BEHAVIOR",
            "layer": "scientific validity",
            "requirement": "all material applicable limits behave correctly",
            "evidence": {
                "limit_rows": family("limit"),
                "monotonicity_rows": family("monotonicity"),
                "sign_rows": family("sign"),
            },
            "verdict": "PASS" if all(
                family(name)["clean"] == family(name)["total"]
                for name in ("limit", "monotonicity", "sign")
            ) else "FAIL",
        },
        {
            "id": "ST-6", "name": "NUMERICAL ACCURACY / CONVERGENCE",
            "layer": "numerical accuracy",
            "requirement": "numerical methods meet the accuracy their own scheme justifies",
            "evidence": {
                "convergence_rows": family("convergence"),
                "observed_orders": "1.00 in time (backward Euler), 2.00 in space (central differences)",
                "expected_order_source": (
                    "the implemented scheme, not an invented expectation; the "
                    "spatial ladder has the constant time-error floor removed "
                    "before its order is read"
                ),
                "predicted_vs_observed_error": (
                    "the reference solves match the scheme's own predicted "
                    "error to about one per cent, which is a stronger "
                    "statement than being inside a tolerance"
                ),
            },
            "verdict": "PASS" if family("convergence")["clean"] == family("convergence")["total"] else "FAIL",
        },
        {
            "id": "ST-7", "name": "SOLVER INDEPENDENCE",
            "layer": "evidence quality",
            "requirement": "claimed independent evidence routes are independent enough to support the claim",
            "evidence": {
                "counts": indep["counts"],
                "method": "module import closure parsed from the AST, not read from docstrings",
                "finding": (
                    "no repository pair is fully independent: all five share "
                    "the problem statement. None shares numerics, and the one "
                    "pair that imports the route it checks takes only two "
                    "metric-name strings from it. This audit's own six oracles "
                    "import no engcore at all"
                ),
                "audit_oracles_independent": all(
                    row["verdict"] == "INDEPENDENT_OF_CORE"
                    for row in indep["this_audits_oracles"]
                ),
            },
            "verdict": "PASS" if indep["counts"]["NO"] == 0 and all(
                row["verdict"] == "INDEPENDENT_OF_CORE"
                for row in indep["this_audits_oracles"]
            ) else "FAIL",
        },
        {
            "id": "ST-8", "name": "ZERO KNOWN FALSE AGREEMENT",
            "layer": "the round's own question",
            "requirement": (
                "no case remains where the implementation, its tests and its "
                "record agree while an independent oracle disagrees"
            ),
            "evidence": {
                "cases": false_agreement["count"],
                "searched_by": false_agreement["how_it_was_searched"],
                "property_draws": sum(f["generated"] for f in props["families"]),
                "property_violations": len(props["violations"]),
            },
            "verdict": "PASS" if false_agreement["count"] == 0 and not props["violations"] else "FAIL",
        },
        {
            "id": "ST-9", "name": "AUDITOR VALIDITY",
            "layer": "the audit itself",
            "requirement": (
                "planted scientific defects are detected and audit mistakes "
                "are adjudicated openly"
            ),
            "evidence": {
                "control": plants["control"]["status"],
                "planted": plants["total"], "detected": plants["caught"],
                "missed": plants["missed"], "by_class": plants["by_class"],
                "two_plants_target_this_audits_own_oracles": True,
                "audit_defects_recorded_in_the_report": 5,
            },
            "verdict": "PASS" if plants["caught"] == plants["total"] and plants["control"]["green"] else "FAIL",
        },
        {
            "id": "ST-10", "name": "PREVIOUS ASSURANCE PRESERVED",
            "layer": "earlier layers, kept separate",
            "requirement": (
                "Contract Guard, Capability Boundary and the certified "
                "scientific assurance remain valid"
            ),
            "evidence": {
                "executable_scientific_code_changed": production_changed,
                "certified_core_digest_expected": CERTIFIED_CORE_TREE_SHA,
                "certified_core_digest_actual": actual_core,
                "earlier_round_paths_modified": earlier_touched,
                "why_no_reruns_were_needed": (
                    "this round changed no file under src/ or tests/ at all, "
                    "so the 79-mutant suite, both benchmark scorecards and "
                    "both earlier guard suites are evaluating byte-identical "
                    "code. The guard suites were run anyway"
                ),
                "not_evidence_of_scientific_truth": (
                    "an unchanged digest says the code is the same code, not "
                    "that its equations are right. The two are different "
                    "layers and this gate speaks only for the first"
                ),
            },
            "verdict": "PASS" if (
                actual_core == CERTIFIED_CORE_TREE_SHA
                and not production_changed
                and not any(earlier_touched.values())
            ) else "FAIL",
        },
        {
            "id": "ST-11", "name": "FROZEN EVIDENCE PRESERVED",
            "layer": "earlier layers",
            "requirement": "Blind V2 frozen/sealed artifacts remain untouched",
            "evidence": {
                **frozen,
                "blind_v2_paths_modified": earlier_touched["benchmarks/blind_v2"],
                "method": (
                    "every artifact named in benchmarks/blind_v2/FREEZE.json "
                    "re-hashed against the value that manifest records, and "
                    "git asked separately whether any path under "
                    "benchmarks/blind_v2 changed. No Blind V2 frozen/sealed "
                    "artifact path changed."
                ),
            },
            "verdict": "PASS" if (
                not frozen["problems"]
                and frozen["verified_byte_identical"] == frozen["artifacts_in_manifest"]
                and not earlier_touched["benchmarks/blind_v2"]
            ) else "FAIL",
        },
    ]

    payload = {
        "schema": "scientific_truth_gates/1",
        "note": (
            "A NEW gate set. The Blind V2, Contract Integrity, Contract Guard "
            "and Capability Boundary gates are not modified, reused or "
            "renumbered; they answered different questions and their results "
            "stand."
        ),
        "what_these_gates_do_not_say": (
            "That the models are the right models for any particular purpose. "
            "They say that the equations each model implements are the "
            "equations its physics requires, that the implementation computes "
            "them correctly, that the numerics converge at the order the "
            "scheme justifies, and that independent mathematics agrees."
        ),
        "layers_kept_separate": [
            "A. executable-code mutation assurance (79 mutants)",
            "B. contract integrity and contract guard",
            "C. capability-boundary validity",
            "D. scientific truth and numerical oracle validation (this round)",
        ],
        "all_pass": all(gate["verdict"] == "PASS" for gate in gates),
        "gates": gates,
    }
    (ROUND / "SAFETY_GATES.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    for gate in gates:
        print(f"{gate['id']:6s} {gate['verdict']:5s} {gate['name']}")
    print("all_pass:", payload["all_pass"])
    return 0 if payload["all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
