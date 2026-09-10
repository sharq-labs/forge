"""Adjudicate the first run: triage every mismatch, and score it twice.

The frozen truth is never edited. Where it was wrong, the correction is
recorded here as an erratum with its own independent justification, and the
adjudicated score is reported **beside** the first-run score, never instead of
it.

Every erratum in this file was discovered because the certified Core disagreed
with the frozen truth. That is contamination and it is recorded as such. What
was *not* taken from the Core is the corrected answer: each erratum is
re-derived from something outside it -- exact rational arithmetic on the
declared decimals, the physical range of an emissivity, the type the public
contract declares for a field. A disagreement pointing at a case is not the
same as a disagreement supplying its answer, and the two are reported apart.
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib

BLIND = pathlib.Path(__file__).resolve().parent.parent

#: Exceptions that are a domain's declared refusal, not a crash. The runner
#: only knew about the core's own two and filed these as core_error; that was
#: the runner being wrong about the taxonomy, and it is corrected here rather
#: than by rewriting the sealed run.
DECLARED_DOMAIN_REFUSALS = (
    "ReactorConfigurationError",
    "SlabConfigurationError",
    "InvalidScientificProblem",
    "UnitCompatibilityError",
    "ModelValidityError",
    "CircuitConfigurationError",
    "CellConfigurationError",
)


def classify(row: dict) -> tuple[str, str]:
    """(triage class, erratum id or '') for one mismatched row."""
    detail = row["detail"] or ""
    if row["exact"]:
        return "AGREEMENT", ""
    if row["forge_outcome"] == "SUPPORTED" and row["truth_outcome"] != "SUPPORTED":
        if row["case_id"] in ERRATA_BY_CASE:
            return ERRATA_BY_CASE[row["case_id"]]["triage"], ERRATA_BY_CASE[row["case_id"]]["id"]
        return "CORE_DEFECT", "CORE-1"
    if "surface_emissivity must lie" in detail or "usable_soc" in detail:
        return "ORACLE_DEFECT", "ERR-3"
    if "got NoneType" in detail:
        return "CHALLENGE_TRUTH_DEFECT", "ERR-5"
    if "derating line was declared without" in detail:
        return "EXPECTED_CONTRACT_DIFFERENCE", "ERR-6"
    if "must be finite and" in detail:
        return "REPRESENTATION_BOUNDARY", "ERR-7"
    if "dimensionally compatible" in detail or "incompatible units" in detail:
        return "CHALLENGE_TRUTH_DEFECT", "ERR-8"
    if row["acceptable_match"]:
        return "EXPECTED_CONTRACT_DIFFERENCE", "ERR-7"
    return "UNRESOLVED", ""


ERRATA = [
    {
        "id": "ERR-1",
        "cases": ["V2-BATTERY_CELL-00044", "V2-BATTERY_CELL-00048"],
        "frozen_truth": "NOT_SUPPORTED",
        "corrected_truth": "SUPPORTED",
        "triage": "CHALLENGE_TRUTH_DEFECT",
        "error_source": (
            "the oracle formed |I/Q_nom| / rating in binary floating point, "
            "through a capacity converted to coulomb and a rate converted to "
            "inverse seconds, and landed one ULP above 1"
        ),
        "evidence": (
            "in exact rational arithmetic on the declared decimals -- 3.75 A "
            "against 2.5 Ah at 1.5/h, and 15 A against 5 Ah at 3/h -- the "
            "utilization is exactly 1. The bound is 1 and the record declares "
            "it inclusive, so the boundary state is inside the domain."
        ),
        "discovered_because_of_forge_disagreement": True,
        "repair_was_forge_guided": False,
        "repair_basis": "exact rational arithmetic on the declared values, computed independently",
    },
    {
        "id": "ERR-2",
        "cases": ["V2-ELECTRICAL_DC-00088"],
        "frozen_truth": "REJECTED_AT_BOUNDARY",
        "corrected_truth": "SUPPORTED",
        "triage": "CHALLENGE_TRUTH_DEFECT",
        "error_source": (
            "the challenge aimed a wrong-dimension refusal probe at "
            "derating_factor, which ComponentRating declares as a bare float"
        ),
        "evidence": (
            "ComponentRating.derating_factor has type float in the public "
            "record. There is no unit on it for a dimension to be wrong "
            "about, so the declaration is legal and the case is the "
            "underlying nominal, which is supported."
        ),
        "discovered_because_of_forge_disagreement": True,
        "repair_was_forge_guided": False,
        "repair_basis": "the declared type of the field in the public contract",
    },
    {
        "id": "ERR-3",
        "cases": [
            "V2-THERMAL_LUMPED-00007",
            "V2-THERMAL_LUMPED-00039",
            "V2-THERMAL_LUMPED-00043",
            "V2-BATTERY_CELL-00021",
        ],
        "frozen_truth": "SUPPORTED or NOT_SUPPORTED",
        "corrected_truth": "REJECTED_AT_BOUNDARY",
        "triage": "ORACLE_DEFECT",
        "error_source": (
            "the lever that drives radiation_to_convection_ratio raises "
            "surface_emissivity, and the one that drives soc_window_margin "
            "raises usable_soc_minimum. Neither the lever nor the oracle "
            "bounded the field it was moving, so the search walked emissivity "
            "past 1 and a state-of-charge edge below 0 and computed with them."
        ),
        "evidence": (
            "a total hemispherical emissivity is a ratio of emitted to "
            "black-body flux and lies in [0, 1] by definition; a state of "
            "charge is a fraction of a cell's usable charge and lies in "
            "[0, 1]. A declaration outside those has no physical reading, and "
            "refusing it at construction is correct."
        ),
        "discovered_because_of_forge_disagreement": True,
        "repair_was_forge_guided": False,
        "repair_basis": "the definition of the two quantities, independent of any implementation",
    },
    {
        "id": "ERR-5",
        "cases": "49 cases: 26 kinetics.cstr, 23 thermal.conduction1d",
        "frozen_truth": "INSUFFICIENT_EVIDENCE",
        "corrected_truth": "REJECTED_AT_BOUNDARY",
        "triage": "CHALLENGE_TRUTH_DEFECT",
        "error_source": (
            "the challenge's evidence map treated required declarations as "
            "droppable evidence. Dropping heat_of_reaction from a reactor or "
            "the diffusivity from a slab does not leave a condition unknown, "
            "it leaves a record that cannot be built."
        ),
        "evidence": (
            "SYSTEM_INVENTORY.json records these inputs as required=true, "
            "read from the models' own declarations before the freeze. The "
            "challenge had the fact and did not use it."
        ),
        "discovered_because_of_forge_disagreement": True,
        "repair_was_forge_guided": False,
        "repair_basis": "the required flag in the frozen system inventory",
        "safety_axis_unchanged": True,
    },
    {
        "id": "ERR-6",
        "cases": "15 electrical.dc cases",
        "frozen_truth": "INSUFFICIENT_EVIDENCE",
        "corrected_truth": "REJECTED_AT_BOUNDARY",
        "triage": "EXPECTED_CONTRACT_DIFFERENCE",
        "error_source": (
            "the challenge dropped rated_power while leaving the two "
            "temperatures that define the derating line, and expected the "
            "condition to report unknown"
        ),
        "evidence": (
            "the Core refuses the combination at construction: a derating "
            "line was declared without a rated_power for it to pass through. "
            "That is stricter than the challenge expected and is the safer "
            "of the two: a half-declared line is a declaration error, not a "
            "gap in evidence."
        ),
        "discovered_because_of_forge_disagreement": True,
        "repair_was_forge_guided": False,
        "repair_basis": "the geometry of the derating line: two points do not define it without the power they pass through",
        "safety_axis_unchanged": True,
    },
    {
        "id": "ERR-7",
        "cases": "16 cases where a strictly-positive parameter was driven to zero or below",
        "frozen_truth": "NOT_SUPPORTED",
        "corrected_truth": "REJECTED_AT_BOUNDARY (also acceptable)",
        "triage": "REPRESENTATION_BOUNDARY",
        "error_source": (
            "CHALLENGE_SPEC registered channel ambiguity for this exact "
            "situation, and the flag was applied only to the branch that "
            "forced a value directly, not to the branch that reached zero by "
            "solving for a margin"
        ),
        "evidence": (
            "the registered rule already says a physically invalid but "
            "dimensionally legal declaration may be refused at construction "
            "or caught as a condition, and that both are refusals. The "
            "accounting missed a branch; the rule did not."
        ),
        "discovered_because_of_forge_disagreement": True,
        "repair_was_forge_guided": False,
        "repair_basis": "a rule registered in CHALLENGE_SPEC.json before the corpus existed",
        "safety_axis_unchanged": True,
    },
    {
        "id": "ERR-8",
        "cases": ["V2-KINETICS_CSTR-00091", "V2-KINETICS_CSTR-00100"],
        "frozen_truth": "REJECTED_AT_BOUNDARY",
        "corrected_truth": "REJECTED_AT_BOUNDARY (unchanged)",
        "triage": "RUNNER_DEFECT",
        "error_source": (
            "the runner treated only ScientificCoreError and "
            "UnitCompatibilityError as declared refusals, so a domain's own "
            "ReactorConfigurationError was filed as a core_error"
        ),
        "evidence": (
            "the two cases were refused for a wrong-dimension declaration, "
            "which is exactly what the frozen truth predicted. The verdict "
            "agreed; only the runner's label did not."
        ),
        "discovered_because_of_forge_disagreement": False,
        "repair_was_forge_guided": False,
        "repair_basis": "the exception classes the domains declare",
    },
]

CORE_DEFECTS = [
    {
        "id": "CORE-1",
        "cases": ["V2-THERMAL_LUMPED-00065", "V2-THERMAL_LUMPED-00074"],
        "triage": "CORE_DEFECT",
        "defect_class": "SHIPPED_CONTRACT_INTEGRITY",
        "title": (
            "Published capability contract contradicts guarded runtime "
            "semantics"
        ),
        "not_this": (
            "NOT an incorrect numerical or scientific runtime implementation. "
            "The computed quantities, the verdicts and every benchmark figure "
            "are unaffected, and the runtime semantics were found to be "
            "deliberate."
        ),
        "severity": "MEDIUM",
        "false_confidence": True,
        "summary": (
            "The lumped model's geometry_route_ratio condition shipped a "
            "published record that contradicted its own guarded runtime "
            "semantics. The record stated, verbatim, that the condition is "
            "UNKNOWN unless characteristic_length, body_volume and "
            "surface_area are all supplied -- 'with one route there is nothing "
            "to compare, which is not the same as two that agree'. The "
            "derivation returns 1.0 with a single route, so the condition is "
            "reported in `satisfied` and the assessment reaches IN_DOMAIN. "
            "Both statements are shipped; they cannot both describe the "
            "product. The defect is that contradiction, located in the "
            "published record."
        ),
        "runtime_semantics_are_deliberate": (
            "test_one_route_alone_is_not_a_contradiction guards the "
            "single-route behaviour by name and states the reason: demanding "
            "all three fields would be a larger claim than this condition "
            "makes, and the Biot number is computed from an unambiguous value "
            "either way. Changing the derivation to return None broke 25 "
            "existing tests. The behaviour is intentional and guarded, so the "
            "record was the half that was wrong."
        ),
        "independent_evidence": (
            "geometry_route_ratio(declared=1 mm, volume=None, surface_area="
            "0.01 m^2) returns 1.0 dimensionless, and an assessment over that "
            "declaration reaches IN_DOMAIN with the condition in `satisfied`. "
            "The published record predicted UNKNOWN. The disagreement is "
            "between two shipped statements about the same condition, and is "
            "observable without reference to any verdict being right or wrong."
        ),
        "forge_evidence": (
            "a body declaring characteristic_length and surface_area but no "
            "body_volume assesses IN_DOMAIN with geometry_route_ratio in "
            "satisfied; declaring the volume as well changes nothing"
        ),
        "mechanism": (
            "the published description on the RangeCondition named "
            "geometry_route_ratio asserted an UNKNOWN precondition that "
            "context.geometry_route_ratio deliberately does not implement"
        ),
        "root_cause": (
            "a shipped record that did not describe the guarded behaviour it "
            "documents. The derivation's own docstring argued the opposite "
            "case coherently; the model record was never brought into line "
            "with it, and the model record is the contract a caller reads and "
            "the one this challenge read."
        ),
        "false_confidence_impact": (
            "a reader of the assessment sees geometry_route_ratio in "
            "`satisfied` and, going by the published record, concludes that "
            "two independently declared geometry routes were compared and "
            "agreed. With one route nothing was compared. The numbers are "
            "right; what the record led a reader to believe about them was "
            "not."
        ),
        "behavioural_false_accepts_after_adjudication": 0,
        "contract_false_accepts_under_frozen_published_contract": 2,
        "false_accept_note": (
            "Both cases were false accepts RELATIVE TO THE FROZEN PUBLISHED "
            "CONTRACT the challenge read before the run: independent truth, "
            "derived from the record, refused; the system reported SUPPORTED. "
            "That satisfies the frozen Gate 3 definition and the gate result "
            "stands. Post-adjudication evidence then established that the "
            "runtime behaviour was deliberate and guarded, so neither case is "
            "a behavioural false accept: the runtime was doing what the "
            "product intends, and the published record misdescribed it."
        ),
        "resolution": (
            "the published record was corrected to describe the guarded "
            "behaviour, and a regression guard now pins the record and the "
            "derivation together so they cannot drift apart again. No "
            "executable scientific behaviour changed."
        ),
        "fix_commit": "0e9bcc219ba7d19eb823cd739dec11c115012ad3",
    }
]

ERRATA_BY_CASE = {}
for erratum in ERRATA:
    if isinstance(erratum["cases"], list):
        for case_id in erratum["cases"]:
            ERRATA_BY_CASE[case_id] = erratum
CORRECTED = {}
for erratum in ERRATA:
    if isinstance(erratum["cases"], list) and erratum["id"] in ("ERR-1", "ERR-2", "ERR-3"):
        for case_id in erratum["cases"]:
            CORRECTED[case_id] = erratum["corrected_truth"]


def adjudicate(rows: list[dict]) -> dict:
    triaged = []
    for row in rows:
        klass, erratum = classify(row)
        corrected = CORRECTED.get(row["case_id"], row["truth_outcome"])
        # ERR-5/6/7/8 all move truth from "refuse late" to "refuse early".
        # They never move a case across the accept/refuse line.
        if erratum in ("ERR-5", "ERR-6", "ERR-7", "ERR-8"):
            corrected = "REJECTED_AT_BOUNDARY"
        adjudicated_exact = row["forge_outcome"] == corrected
        triaged.append(
            {
                **row,
                "triage_class": klass,
                "erratum": erratum,
                "corrected_truth": corrected,
                "adjudicated_exact": adjudicated_exact,
                "adjudicated_safety": (
                    "TRUE_ACCEPT"
                    if corrected == "SUPPORTED" and row["forge_outcome"] == "SUPPORTED"
                    else "FALSE_ACCEPT"
                    if corrected != "SUPPORTED" and row["forge_outcome"] == "SUPPORTED"
                    else "FALSE_REJECT"
                    if corrected == "SUPPORTED"
                    else "TRUE_REJECT"
                ),
                "core_error_reclassified": row["exception_type"] in DECLARED_DOMAIN_REFUSALS,
            }
        )
    return triaged


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--comparison", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    comparison = json.loads(pathlib.Path(args.comparison).read_text())
    rows = adjudicate(comparison["rows"])

    first_run = {
        "exact": sum(1 for r in rows if r["exact"]),
        "acceptable": sum(1 for r in rows if r["acceptable_match"]),
        "safety": dict(sorted(collections.Counter(r["safety"] for r in rows).items())),
    }
    adjudicated = {
        "exact": sum(1 for r in rows if r["adjudicated_exact"]),
        "safety": dict(
            sorted(collections.Counter(r["adjudicated_safety"] for r in rows).items())
        ),
    }
    payload = {
        "schema": "blind_v2_adjudication/1",
        "rule": (
            "The first-run score is preserved exactly as it was measured. The "
            "adjudicated score applies the errata below, each independently "
            "justified. Neither replaces the other."
        ),
        "first_run_score": first_run,
        "adjudicated_score": adjudicated,
        "score_interpretation": {
            "adjudicated_safety.FALSE_ACCEPT": (
                "2. Both are the CORE-1 cases and both are false accepts "
                "RELATIVE TO THE FROZEN PUBLISHED CONTRACT: independent truth "
                "was derived from the published record, the record said "
                "UNKNOWN, the system said SUPPORTED. Post-adjudication "
                "evidence established that the runtime behaviour is deliberate "
                "and guarded, so BEHAVIOURAL FALSE ACCEPTS AFTER ADJUDICATION "
                "ARE 0 and the defect is a shipped contract-integrity one. See "
                "core_defects[0]."
            ),
            "adjudicated_safety.FALSE_REJECT": (
                "0. The two first-run false rejects were challenge oracle "
                "defects (ERR-3), not Core behaviour."
            ),
        },
        "triage_classes": dict(
            sorted(collections.Counter(r["triage_class"] for r in rows).items())
        ),
        "core_errors_reclassified_as_declared_refusals": sum(
            1 for r in rows if r["outcome_kind"] == "core_error" and r["core_error_reclassified"]
        ),
        "genuine_core_crashes": sum(
            1
            for r in rows
            if r["outcome_kind"] == "core_error" and not r["core_error_reclassified"]
        ),
        "core_defects": CORE_DEFECTS,
        "errata": ERRATA,
        "contamination": {
            "rule": (
                "A correction found because the Core disagreed is contamination "
                "of the challenge's independence, whether or not the Core "
                "supplied the answer. Both facts are recorded."
            ),
            "FOUND_WITHOUT_FORGE": [e["id"] for e in ERRATA if not e["discovered_because_of_forge_disagreement"]],
            "FORGE_GUIDED_DISCOVERY": [e["id"] for e in ERRATA if e["discovered_because_of_forge_disagreement"]],
            "FORGE_GUIDED_REPAIR": [e["id"] for e in ERRATA if e["repair_was_forge_guided"]],
            "note": (
                "Every erratum but ERR-8 was found because the Core disagreed. "
                "No erratum took its corrected answer from the Core: each was "
                "re-derived from exact arithmetic, from the definition of the "
                "quantity, or from a fact the challenge had frozen before the "
                "run and failed to use."
            ),
        },
        "rows": rows,
    }
    pathlib.Path(args.out).write_text(
        json.dumps(payload, indent=1, sort_keys=True) + "\n", encoding="utf-8"
    )
    print("first run  :", json.dumps(first_run))
    print("adjudicated:", json.dumps(adjudicated))
    print("triage     :", json.dumps(payload["triage_classes"]))
    print("core crashes:", payload["genuine_core_crashes"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
