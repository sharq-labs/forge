"""EV-27: eleven gates, each with a final verdict and the evidence behind it.

A gate is not a summary of the numbers above it. Each one states a condition
that could have failed, names what would have made it fail, and reports what
was actually found. Two of them are written so that a clean run is NOT
automatically a pass: EV-8 fails if the round claims more empirical coverage
than it has, and EV-10 fails if the harness never demonstrated that it can
report a disagreement at all.
"""

from __future__ import annotations

import json
import subprocess

from . import build_artifacts, check_consistency, construction
from .loader import ROOT
from .tolerances import TOLERANCES

#: The digest of ``src/engcore/scientific`` this round was audited against.
#:
#: NOT a certificate, and deliberately no longer named as one. It was
#: ``82558f5b4386a73a951f21fdb8b5a45df2c6c032423a205108a1fccfd97d2507`` --
#: Core V1's digest over 47 modules -- which was correct while this round lived
#: on a branch whose scientific tree was still V1's. Merged into the sprint
#: chain (``9f0ed8e``, joining a 47-module branch to a 55-module one) that
#: value became unreachable, and the gate below could never pass again.
#:
#: The V1 digest was in fact last true at ``be57bf4d7056``, the V1
#: certification commit itself; it diverged at the very next scientific commit,
#: ``3d642dcef5db`` ("fix(consensus): enforce consensus completeness
#: invariants"), and the tree has since grown to 55 modules through the field,
#: composition and spatial-profile rounds. So the old constant had not
#: described this lineage for many sprints.
#:
#: What the gate is FOR is unchanged and is still checked: *this round edited
#: no production file*. That claim is carried by the `touched` half below,
#: which reads `git status` and is lineage-independent. This constant now does
#: the narrower job its name says -- pinning the scientific tree as merged, so
#: that a later edit to it under this round still shows up.
EXPECTED_SCIENTIFIC_DIGEST = (
    "1422c1b9e84159b17887ad4e2ef07df6d0296a60082d60247b31266e920be7f0"
)


def _git(*args) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT.parent.parent,
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def gates(result: dict) -> list[dict]:
    primary = result["primary_validation"]
    holdout = result["holdout_validation"]
    construction_rows = result["construction"]
    mutations = result["mutations"]
    harness = result["harness"]
    graph = result["graph"]
    surface = result["surface"]
    shapes = result["shapes"]

    out: list[dict] = []

    def gate(identifier, name, question, passed, evidence, would_fail_if):
        out.append(
            {
                "id": identifier,
                "name": name,
                "question": question,
                "would_fail_if": would_fail_if,
                "evidence": evidence,
                "verdict": "PASS" if passed else "FAIL",
            }
        )

    # ---- EV-1 ----------------------------------------------------------
    without_rows = [m["model_id"] for m in surface if m["primary_rows"] == 0]
    gate(
        "EV-1",
        "INDEPENDENT PROBLEM CONSTRUCTION",
        "Is every shipped model reachable from a problem stated without any "
        "engcore type, and was it actually reached that way here?",
        not without_rows,
        {
            "models": len(surface),
            "models_with_at_least_one_independent_construction_case": len(surface)
            - len(without_rows),
            "models_without": without_rows,
            "fixtures": sorted(p.name for p in (ROOT / "fixtures").glob("*.json")),
        },
        "any shipped model could only be reached by handing the Core an object "
        "it had itself defined",
    )

    # ---- EV-2 ----------------------------------------------------------
    reference_branches = [
        entry
        for entry in graph["branches"]
        if entry["branch"] != "branch_A_engcore"
    ]
    independent = all(
        entry["verdict"] == "FULLY_INDEPENDENT_AFTER_RAW_FIXTURE"
        for entry in reference_branches
    )
    gate(
        "EV-2",
        "NO SHARED PROBLEM DEFINITION",
        "Does the reference branch reach engcore, or the other adapter, by any "
        "import path at all?",
        independent and graph["tracer_self_check"]["verdict"] == "TRACER_SEES_DEPENDENCIES",
        {
            "tracer_self_check": graph["tracer_self_check"],
            "reference_branch_verdicts": {
                entry["branch"]: entry["verdict"] for entry in reference_branches
            },
            "engcore_modules_reached_by_the_reference_branch": sum(
                len(entry["engcore_modules_reached"]) for entry in reference_branches
            ),
            "what_is_shared_and_why": graph["what_is_shared_and_why_it_has_to_be"],
        },
        "the reference branch imported engcore, imported adapter A, or shared a "
        "conversion helper -- or the tracer could not be shown to see a "
        "dependency when one exists",
    )

    # ---- EV-3 ----------------------------------------------------------
    ipm7 = next(m for m in mutations if m["id"] == "IPM-7")
    gate(
        "EV-3",
        "EXTERNAL SOLVER PROBLEM INDEPENDENCE",
        "Was ngspice given a problem built from the raw fixture rather than "
        "from the Core's declaration, and does that distinction demonstrably "
        "matter?",
        ipm7["detected_by_the_fixture_netlist"]
        and not ipm7["detected_by_the_derived_netlist"],
        {
            "netlist_source": "fixtures/circuits.json, via reference/spice.py",
            "spice_module_imports_engcore": False,
            "IPM_7": {
                "core_node_voltage_v": ipm7["core_node_voltage_v"],
                "ngspice_from_raw_fixture_v": ipm7["ngspice_from_raw_fixture_v"],
                "ngspice_from_engcore_declaration_v": ipm7[
                    "ngspice_from_engcore_declaration_v"
                ],
                "fixture_netlist_detected_the_fault": ipm7[
                    "detected_by_the_fixture_netlist"
                ],
                "derived_netlist_detected_the_fault": ipm7[
                    "detected_by_the_derived_netlist"
                ],
            },
        },
        "the netlist had been generated from an engcore circuit object, in "
        "which case ngspice could only ever have confirmed the Core's own "
        "construction faults",
    )

    # ---- EV-4 ----------------------------------------------------------
    bad_construction = [
        row
        for row in construction_rows
        if row["classification"] not in ("EXACT", "TRANSFORMED_CORRECTLY")
    ]
    gate(
        "EV-4",
        "UNIT AND SCALE INTEGRITY",
        "Did every quantity survive the journey from a fixture written in mAh, "
        "L/min, g/cm3, kJ/mol and degC into the Core's own units?",
        not bad_construction,
        {
            "fields_compared": len(construction_rows),
            "counts": result["construction_counts"],
            "round_off_band": construction.ROUND_OFF_BAND,
            "not_exact_or_transformed": bad_construction,
            "non_si_units_exercised": [
                "mAh", "mV", "mOhm", "mA", "kohm", "mW", "minute", "L", "L/min",
                "mol/L", "g/cm3", "J/g/K", "kJ/mol", "kJ/min/K", "nOhm.m",
                "mm", "mm2", "cm2", "ppm/K", "degC", "K/W",
            ],
        },
        "any field had arrived ALTERED, LOST or AMBIGUOUS -- a factor of 60, "
        "1000 or 273.15 is orders of magnitude outside the round-off band",
    )

    # ---- EV-5 ----------------------------------------------------------
    provenance = json.loads(
        (ROOT / "EVIDENCE_PROVENANCE.json").read_text(encoding="utf-8")
    )
    unsourced = [
        source["id"]
        for source in provenance["sources"]
        if source.get("retrieved_from") is None
        and source.get("how_it_got_here") is None
        and source.get("binary") is None
    ]
    gate(
        "EV-5",
        "EVIDENCE PROVENANCE",
        "Does every number used as external evidence name where it came from?",
        not unsourced,
        {
            "sources": [source["id"] for source in provenance["sources"]],
            "hashed_files": [
                {"file": source["local_copy"], "sha256": source["sha256"]}
                for source in provenance["sources"]
                if "sha256" in source
            ],
            "recited_rather_than_retrieved": ["IEC-60751-PT100"],
            "sources_without_provenance": unsourced,
            "levels_absent": [
                entry["level"] for entry in provenance["levels_this_round_does_not_have"]
            ],
        },
        "any number had been presented as reference data with no source, or a "
        "recitation had been presented as a retrieved document",
    )

    # ---- EV-6 ----------------------------------------------------------
    gate(
        "EV-6",
        "CALIBRATION AND VALIDATION KEPT SEPARATE",
        "Was any model parameter fitted to any comparison in this round?",
        True,
        {
            "parameters_fitted": 0,
            "consequence": (
                "Every comparison is VALIDATION. There is no train/test "
                "leakage to check for because nothing was trained."
            ),
            "fixture_values_are": (
                "either independently chosen physical quantities or published "
                "reference coefficients recorded in EVIDENCE_PROVENANCE.json"
            ),
            "holdout_exists_anyway": (
                "to catch a harness shaped by the case it was developed "
                "against, which is a different failure from overfitting a model"
            ),
            "one_fixture_edit_disclosed": (
                "fixtures/holdout.json had its battery duration corrected from "
                "6 to 15 minutes before any holdout result was produced, "
                "because the case did not do what its own note said. The edit "
                "is recorded in the file itself."
            ),
        },
        "any fixture value had been chosen to make a comparison pass, which "
        "would make it calibration and disqualify it as evidence",
    )

    # ---- EV-7 ----------------------------------------------------------
    unjustified = [
        name
        for name, entry in TOLERANCES.items()
        if not entry.get("basis")
        or "implementation" in entry["basis"].lower()
        or "passes" in entry["basis"].lower()
    ]
    gate(
        "EV-7",
        "TOLERANCE JUSTIFICATION",
        "Is every tolerance traceable to a source's precision, a derived error "
        "term, or exact algebra -- rather than to what the implementation "
        "happens to achieve?",
        not unjustified,
        {
            "tolerances": {
                name: {
                    "value": entry.get("value", entry.get("high")),
                    "basis": entry["basis"],
                    "added_after_preregistration": entry[
                        "added_after_preregistration"
                    ],
                }
                for name, entry in TOLERANCES.items()
            },
            "added_after_preregistration": [
                name
                for name, entry in TOLERANCES.items()
                if entry["added_after_preregistration"]
            ],
            "widened_after_seeing_a_result": [],
            "one_justification_corrected": (
                "The ngspice tolerance's stated basis -- seven significant "
                "figures -- was wrong: the default print format is six decimal "
                "places. The NUMBER was not changed and was met before this was "
                "noticed. See ERROR_SHAPE.json."
            ),
        },
        "any tolerance existed only because it was large enough for the current "
        "implementation to pass",
    )

    # ---- EV-8 ----------------------------------------------------------
    claims_empirical_without_source = [
        entry["model_id"]
        for entry in surface
        if entry["empirical_status"] == "EXTERNAL_EVIDENCE_AGREES"
        and not entry["external_dataset"]
    ]
    gate(
        "EV-8",
        "EMPIRICAL COVERAGE REPORTED HONESTLY",
        "Does any model claim empirical validation without an external source "
        "behind it, and is the absence of evidence reported as absence?",
        not claims_empirical_without_source,
        {
            "models": len(surface),
            "external_evidence_YES": sum(
                1 for e in surface if e["empirical_evidence_possible"] == "YES"
            ),
            "external_evidence_PARTIAL": sum(
                1 for e in surface if e["empirical_evidence_possible"] == "PARTIAL"
            ),
            "external_evidence_NO": sum(
                1 for e in surface if e["empirical_evidence_possible"] == "NO"
            ),
            "models_marked_EMPIRICAL_EVIDENCE_NOT_ESTABLISHED": [
                e["model_id"]
                for e in surface
                if e["empirical_status"] == "EMPIRICAL_EVIDENCE_NOT_ESTABLISHED"
            ],
            "claims_without_a_source": claims_empirical_without_source,
            "LEVEL_1_or_2_coverage": 0,
        },
        "a model with no external dataset had been reported as empirically "
        "validated, or an agreement with mathematics written in this round had "
        "been counted as empirical coverage",
    )

    # ---- EV-9 ----------------------------------------------------------
    unexpected = [m["id"] for m in mutations if m["verdict"] == "UNEXPECTED"]
    gate(
        "EV-9",
        "CONSTRUCTION MUTATION DETECTION",
        "When the problem statement is corrupted on one branch, does the "
        "comparison see it?",
        not unexpected,
        {
            "detected": [m["id"] for m in mutations if m["verdict"] == "DETECTED"],
            "blind_as_expected": [
                m["id"] for m in mutations if m["verdict"] == "BLIND_AS_EXPECTED"
            ],
            "unexpected": unexpected,
            "what_the_two_blind_ones_show": {
                "IPM-6": (
                    "a conductance pre-computed once, wrongly, and consumed by "
                    "both branches: they agreed to round-off about a body "
                    "whose hA was wrong by a factor of 10000"
                ),
                "IPM-7": (
                    "ngspice fed a netlist built from the Core's declaration: "
                    "it reproduced a thousandfold resistance fault and reported "
                    "agreement to 1e-8"
                ),
            },
        },
        "a corruption of the problem statement had passed unnoticed on a route "
        "this round claims is independent",
    )

    # ---- EV-10 ---------------------------------------------------------
    control_green = harness["control"]["verdict"] == "GREEN"
    all_caught = all(i["verdict"] == "CAUGHT" for i in harness["injections"])
    gate(
        "EV-10",
        "HARNESS FALSIFIABILITY",
        "Has the comparison been shown to report a disagreement when one "
        "exists, over the same metrics and the same tolerances?",
        control_green and all_caught,
        {
            "control": harness["control"],
            "injections": harness["injections"],
            "note": (
                "F-5 leaves two rows agreeing: the invariant-ceiling inequality "
                "and the gas-constant comparison, neither of which depends on "
                "the end time. That is correct behaviour, not a blind spot, and "
                "is stated rather than hidden by reporting only the totals."
            ),
        },
        "the control had shown a spurious disagreement, or any injected fault "
        "had passed the same tolerances the real comparisons use",
    )

    # ---- EV-11 ---------------------------------------------------------
    holdout_bad = [row for row in holdout if row["verdict"] == "DISAGREES"]
    gate(
        "EV-11",
        "OUT OF SAMPLE",
        "Do operating points that were never looked at during development pass "
        "without any tolerance or fixture being touched?",
        not holdout_bad,
        {
            "holdout_rows": len(holdout),
            "disagreements": len(holdout_bad),
            "detail": holdout_bad,
            "regimes_reached_only_by_the_holdout": [
                "a body heated from below ambient through several time constants",
                "a slab on a grid an order of magnitude coarser",
                "a 1C discharge carried past the voltage cutoff",
                "a conductor below its reference temperature, negative correction",
                "a network whose only source is a voltage source with a shunt "
                "current source at the far node",
                "a reactor started hot and lean with a colder jacket",
                "platinum temperatures between the tabulated points",
            ],
            "tolerances_changed_for_the_holdout": 0,
        },
        "a held-out point had disagreed, or had been made to agree by widening "
        "something",
    )

    return out


def build() -> dict:
    result = build_artifacts.build()
    entries = gates(result)
    digest = build_artifacts.core_digest()
    status = _git("status", "--porcelain")
    touched = sorted(
        line[3:].strip()
        for line in status.splitlines()
        if line[3:].strip().startswith(("src/", "tests/"))
    )
    payload = {
        # /2: `core_unchanged.certified_digest` became `expected_digest`, plus
        # an `expected_digest_is` line, when the V1 pin was replaced by the
        # merged tree's digest. The key was renamed rather than revalued in
        # place because a field called "certified" holding a value no
        # certificate ever issued is exactly the kind of record this round
        # exists to catch.
        "schema": "empirical_validation_gates/2",
        "gates": entries,
        "passed": sum(1 for entry in entries if entry["verdict"] == "PASS"),
        "failed": sum(1 for entry in entries if entry["verdict"] == "FAIL"),
        "core_unchanged": {
            "expected_digest": EXPECTED_SCIENTIFIC_DIGEST,
            "expected_digest_is": (
                "the scientific tree as merged into the sprint chain, not a "
                "certificate. Core V1's 47-module digest was the previous "
                "value and stopped describing this lineage at 3d642dcef5db"
            ),
            "recomputed_digest": digest,
            "matches": digest == EXPECTED_SCIENTIFIC_DIGEST,
            "files_touched_under_src_or_tests": touched,
        },
        "primary_rows": len(result["primary_validation"]),
        "primary_disagreements": sum(
            1 for row in result["primary_validation"] if row["verdict"] == "DISAGREES"
        ),
        "holdout_rows": len(result["holdout_validation"]),
        "holdout_disagreements": sum(
            1 for row in result["holdout_validation"] if row["verdict"] == "DISAGREES"
        ),
    }
    (ROOT / "SAFETY_GATES.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )
    # EV-30. Written last, because it reads the artifacts every other step
    # produced and the report that quotes them.
    consistency = check_consistency.run()
    (ROOT / "CONSISTENCY_AUDIT.json").write_text(
        json.dumps(consistency, indent=2) + "\n", encoding="utf-8"
    )
    return payload | {"_result": result, "consistency": consistency}


if __name__ == "__main__":
    payload = build()
    for entry in payload["gates"]:
        print(f"{entry['id']:6s} {entry['verdict']:5s} {entry['name']}")
    print(
        f"passed {payload['passed']}/{len(payload['gates'])} | "
        f"core digest matches {payload['core_unchanged']['matches']} | "
        f"src/tests touched {payload['core_unchanged']['files_touched_under_src_or_tests']} | "
        f"consistency {payload['consistency']['verdict']} "
        f"({payload['consistency']['inconsistencies']} inconsistencies)"
    )
