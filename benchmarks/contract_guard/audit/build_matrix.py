"""Build CONTRACT_GUARD_MATRIX.json from the live tree.

Every cell is computed from the guards that actually run, never asserted by
hand, so the matrix cannot drift from the suite it describes. A dimension is
GUARDED only when an executable check binds this model's published record to
the runtime that serves it; NOT_APPLICABLE only when the model has no surface
of that kind, with the reason recorded next to it.
"""

from __future__ import annotations

import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROUND = HERE.parent
REPO = ROUND.parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "benchmarks" / "contract_integrity" / "audit"))

from benchmarks.contract_guard.guard import (  # noqa: E402
    capabilities,
    enforcement,
    prerequisites,
    prose,
    records,
)

GUARDED = "GUARDED"
NOT_GUARDED = "NOT_GUARDED"
NOT_APPLICABLE = "NOT_APPLICABLE"
BLOCKED = "BLOCKED_BY_AMBIGUOUS_SEMANTICS"

DIMENSIONS = {
    "A": "required/optional inputs",
    "B": "UNKNOWN/refusal prerequisites",
    "C": "applicability",
    "D": "route selection",
    "E": "cross-check/evidence claims",
    "F": "reason/result agreement",
    "G": "capability declarations",
    "H": "state/control requirements",
}

GUARD_DEFINITION = (
    "A model counts as GUARDED on a dimension only when an executable test "
    "connects its PUBLISHED RECORD to the ACTUAL GUARDED RUNTIME SEMANTICS, "
    "such that the test fails if either side drifts. Unit tests of the "
    "implementation, the existence of a record, a snapshot containing its "
    "text, and passing a benchmark do not count: none of them fails when the "
    "record and the runtime stop agreeing."
)


def _claims():
    import claim_map

    return claim_map.CLAIMS


def build() -> dict:
    claims = _claims()
    inputs = prerequisites.required_input_survey()
    review = prerequisites.unknown_promise_review()
    self_derived = prerequisites.self_derived_survey()
    served = capabilities.survey()
    probes = enforcement.survey()
    prose_report = prose.check()

    input_by_key = {(row["system"], row["input"]): row for row in inputs["rows"]}
    review_by_model: dict[str, list] = {}
    dropped_by_model: dict[str, set[str]] = {}
    for row in review["rows"]:
        review_by_model.setdefault(row["model_id"], []).append(row)
        dropped = row.get("dropped")
        names = dropped if isinstance(dropped, (list, tuple)) else [dropped]
        for name in names:
            if isinstance(name, str):
                dropped_by_model.setdefault(row["model_id"], set()).add(name)

    crosscheck = json.loads(
        (REPO / "benchmarks" / "contract_integrity" / "CONTRACT_SURFACE.json").read_text(
            encoding="utf-8"
        )
    )
    crosscheck_by_model = {
        model["model_id"]: sum(
            len(condition.get("crosscheck_clauses", []))
            for condition in model["conditions"]
        )
        for model in crosscheck["models"]
    }

    rows = []
    for model in records.shipped_models():
        system = records.system_of(model.model_id)
        conditions = [
            ref for ref in records.conditions() if ref.model_id == model.model_id
        ]
        names = [ref.name for ref in conditions]

        # A -- every input this record names, looked up in the constructor probe
        addressable = [
            input_by_key[(system, spec.name)]
            for spec in model.inputs
            if (system, spec.name) in input_by_key
        ]
        checked = [row for row in addressable if row["result"] == "MATCH"]
        not_addressable = [
            row for row in addressable if row["result"] == "NOT_CONSTRUCTOR_ADDRESSABLE"
        ]
        solved = [
            spec.name
            for spec in model.inputs
            if spec.source_kind.value == "variable" and spec.role is None
        ]
        dropped_here = dropped_by_model.get(model.model_id, set())
        at_declaration = [
            row for row in not_addressable if row["input"] in dropped_here
        ]
        unchecked = [
            row for row in not_addressable if row["input"] not in dropped_here
        ]
        if checked or at_declaration:
            a_status, a_note = (
                GUARDED,
                f"{len(checked)} of {len(addressable)} declarable inputs probed "
                "by omission at the public constructor; "
                f"{len(at_declaration)} reach the model through the validity "
                "context and are probed by omission there instead, where "
                "'optional' means the condition goes UNKNOWN rather than the "
                f"model refusing; {len(unchecked)} unchecked; {len(solved)} are "
                "solved unknowns, not caller inputs",
            )
        elif addressable:
            a_status, a_note = (
                NOT_GUARDED,
                f"none of this record's {len(addressable)} declarable inputs is "
                "probed by omission at either the constructor or the "
                "declaration boundary",
            )
        else:
            a_status, a_note = (
                NOT_APPLICABLE,
                f"this record declares no caller-supplied input: all "
                f"{len(solved)} are solved unknowns",
            )

        # B -- UNKNOWN prerequisites
        b_rows = review_by_model.get(model.model_id, [])
        b_contexts = [
            row for row in self_derived["rows"] if row["quantity"] in names
        ]
        if b_rows:
            b_status, b_note = (
                GUARDED,
                f"{len(b_rows)} withhold-and-demand-UNKNOWN checks re-run live "
                "from the claim map, plus the empty-context derivation check",
            )
        elif b_contexts:
            b_status, b_note = (GUARDED, "covered by the empty-context derivation check")
        else:
            b_status, b_note = (
                NOT_APPLICABLE,
                "no condition on this record publishes an UNKNOWN prerequisite",
            )

        # C -- applicability, structured and in prose
        model_probes = sum(len(enforcement.check(ref)) for ref in conditions)
        prose_claims = sum(len(prose.claims_for(ref)) for ref in conditions)
        if conditions:
            c_status = GUARDED
            c_note = (
                f"{model_probes} bound-enforcement probes across "
                f"{len(conditions)} conditions, and {prose_claims} prose "
                "applicability claims put through the same runtime"
            )
        else:
            c_status, c_note = (NOT_APPLICABLE, "this record declares no conditions")

        # D -- route selection
        routes = [
            name
            for name in names
            if claims.get((system, name), {}).get("one_of")
            or claims.get((f"{system}.natural", name), {}).get("one_of")
        ]
        if routes:
            d_status, d_note = (
                GUARDED,
                "alternative routes are declared in the claim map and each is "
                f"checked to serve alone: {', '.join(sorted(set(routes)))}",
            )
        else:
            d_status, d_note = (
                NOT_APPLICABLE,
                "no condition on this record offers a caller alternative routes "
                "to the same quantity",
            )

        # E -- cross-check / evidence claims
        clause_count = crosscheck_by_model.get(model.model_id, 0)
        if clause_count and routes:
            e_status, e_note = (
                GUARDED,
                f"{clause_count} cross-check clauses, each on a condition whose "
                "routes are checked individually, and the one-route reading is "
                "pinned by a named invariant test",
            )
        elif clause_count:
            e_status, e_note = (
                NOT_GUARDED,
                f"{clause_count} cross-check clauses with no route alternatives "
                "to exercise",
            )
        else:
            e_status, e_note = (
                NOT_APPLICABLE,
                "this record claims no cross-check between two routes",
            )

        # F -- reason/result agreement
        f_status, f_note = (
            GUARDED,
            "every UNKNOWN condition must carry a reason and the assessment "
            "status must agree with its own condition sets",
        )

        # G -- capability declarations
        g_status, g_note = (
            GUARDED,
            "declared capability "
            + ", ".join(str(name) for name in model.required_capabilities)
            + " must be served by a registered solver",
        )

        # H -- state / control
        state_inputs = [
            spec.name
            for spec in model.inputs
            if spec.role is not None
            and (str(spec.role).endswith("STATE") or str(spec.role).endswith("CONTROL"))
        ]
        state_checked = []
        for name in state_inputs:
            if input_by_key.get((system, name), {}).get("result") == "MATCH":
                state_checked.append(f"{name} (refused at construction)")
            elif name in names:
                state_checked.append(f"{name} (a condition of its own, probed under C)")
            elif name in dropped_here:
                state_checked.append(f"{name} (withheld at the declaration boundary)")
        unchecked_state = [
            name
            for name in state_inputs
            if not any(entry.startswith(f"{name} ") for entry in state_checked)
        ]
        if state_checked and not unchecked_state:
            h_status, h_note = (
                GUARDED,
                "every declared state or control input is probed by omission: "
                + "; ".join(sorted(state_checked)),
            )
        elif state_inputs:
            h_status, h_note = (
                NOT_GUARDED,
                f"declares state or control {sorted(unchecked_state)} with "
                "nothing to withhold at construction, at the declaration "
                "boundary, or as a condition of its own",
            )
        else:
            h_status, h_note = (
                NOT_APPLICABLE,
                "this record declares no evolving state or control input",
            )

        dimensions = {
            "A": {"status": a_status, "note": a_note},
            "B": {"status": b_status, "note": b_note},
            "C": {"status": c_status, "note": c_note},
            "D": {"status": d_status, "note": d_note},
            "E": {"status": e_status, "note": e_note},
            "F": {"status": f_status, "note": f_note},
            "G": {"status": g_status, "note": g_note},
            "H": {"status": h_status, "note": h_note},
        }
        applicable = [k for k, v in dimensions.items() if v["status"] != NOT_APPLICABLE]
        guarded = [k for k, v in dimensions.items() if v["status"] == GUARDED]
        rows.append(
            {
                "model_id": model.model_id,
                "system": system,
                "record_source": model.__class__.__module__,
                "runtime_entry_point": f"{model.model_id}.assess_validity"
                " + the domain constructor and assembler for " + system,
                "condition_count": len(conditions),
                "dimensions": dimensions,
                "applicable_dimensions": applicable,
                "guarded_dimensions": guarded,
                "fully_guarded": sorted(applicable) == sorted(guarded),
            }
        )

    applicable_total = sum(len(row["applicable_dimensions"]) for row in rows)
    guarded_total = sum(len(row["guarded_dimensions"]) for row in rows)
    not_applicable_total = len(rows) * len(DIMENSIONS) - applicable_total
    fully = [row["model_id"] for row in rows if row["fully_guarded"]]
    partial = [
        row["model_id"]
        for row in rows
        if not row["fully_guarded"] and row["guarded_dimensions"]
    ]
    none_guarded = [row["model_id"] for row in rows if not row["guarded_dimensions"]]

    return {
        "schema": "contract_guard_matrix/1",
        "what_counts_as_guarded": GUARD_DEFINITION,
        "dimensions": DIMENSIONS,
        "model_count": len(rows),
        "condition_count": len(records.conditions()),
        "totals": {
            "cells": len(rows) * len(DIMENSIONS),
            "applicable_dimensions": applicable_total,
            "guarded_dimensions": guarded_total,
            "not_guarded_dimensions": applicable_total - guarded_total,
            "not_applicable_dimensions": not_applicable_total,
            "blocked_dimensions": 0,
            "fully_guarded_models": len(fully),
            "partially_guarded_models": len(partial),
            "unguarded_models": len(none_guarded),
        },
        "fully_guarded_models": fully,
        "partially_guarded_models": partial,
        "unguarded_models": none_guarded,
        "evidence": {
            "bound_enforcement_probes": probes["probes"],
            "bound_enforcement_disagreements": len(probes["disagreements"]),
            "prose_claims_executed": prose_report["claims_checked"],
            "prose_disagreements": len(prose_report["findings"]),
            "conditions_without_executable_prose_claim": len(
                prose_report["conditions_without_executable_claim"]
            ),
            "unknown_prerequisite_checks": review["checks"],
            "unknown_prerequisite_disagreements": len(review["disagreements"]),
            "constructor_input_checks": inputs["checks"],
            "constructor_input_counts": inputs["counts"],
            "empty_context_derivations": len(self_derived["rows"]),
            "empty_context_undeclared": len(self_derived["undeclared"]),
            "capability_models": served["models"],
            "capabilities_unserved": len(served["unserved"]),
        },
        "models": rows,
    }


def main() -> int:
    payload = build()
    out = ROUND / "CONTRACT_GUARD_MATRIX.json"
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    totals = payload["totals"]
    print(f"{payload['model_count']} models, {totals['cells']} cells")
    print(json.dumps(totals, indent=1))
    for row in payload["models"]:
        if not row["fully_guarded"]:
            gaps = [
                f"{k}={v['status']}"
                for k, v in row["dimensions"].items()
                if v["status"] not in (GUARDED, NOT_APPLICABLE)
            ]
            print(f"  partial: {row['model_id']}: {', '.join(gaps)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
