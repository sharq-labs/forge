"""Build MODEL_CAPABILITY_SURFACE.json — the CB-1 inventory.

The published half is read from the live records; the derived half is the
audit's own scientific reading, held in ``capability_table`` so that it is
reviewable as data rather than buried in prose. Nothing here is typed twice.
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

from benchmarks.capability_boundary.audit.capability_table import CAPABILITY  # noqa: E402
from benchmarks.contract_guard.guard import records  # noqa: E402

#: Where each model's equations are actually evaluated, as opposed to declared.
ENTRY_POINTS = {
    "thermal.lumped": "engcore.domains.thermal_models.lumped (ThermalBody -> LumpedCapacitySolver)",
    "thermal.conduction1d": "engcore.domains.thermal.conduction1d.solver.solve_slab",
    "battery.cell": "engcore.domains.battery.solver.evaluate_step",
    "electrical.dc": "engcore.domains.electrical.dc.solver.ElectricalDCSolver (MNA)",
    "electrical.material": "engcore.domains.electrical.material.ResistancePropertySolver",
    "kinetics.cstr": "engcore.domains.kinetics.cstr.solver (shared CSTR kernel)",
}


def _conditions(model) -> list[dict]:
    rows = []
    for condition in model.validity.conditions:
        payload = condition.to_dict()
        rows.append(
            {
                "name": condition.name,
                "kind": type(condition).__name__,
                "is_reserved_derived": condition.name in model.derived_quantities,
                "minimum": payload.get("minimum"),
                "maximum": payload.get("maximum"),
                "conservative_screen": payload.get("conservative_screen", False),
            }
        )
    return rows


def build() -> dict:
    rows = []
    for model in records.shipped_models():
        system = records.system_of(model.model_id)
        derived = CAPABILITY[model.model_id]
        try:
            exclusions = list(model.exclusions)
            exclusions_declared = True
        except TypeError:
            exclusions = []
            exclusions_declared = False
        rows.append(
            {
                "system": system,
                "model_id": model.model_id,
                "published_name": model.name,
                "model_type": model.model_type.value,
                "validation_status": model.validation_status.value,
                "published_capability_claim": model.description,
                "implementation_entry_point": ENTRY_POINTS[system],
                "governing_equations": derived["equations"],
                "declared_assumptions": list(model.assumptions),
                "declared_exclusions": exclusions,
                "exclusions_declared": exclusions_declared,
                "declared_validity_limits": _conditions(model),
                "reserved_derived_quantities": sorted(model.derived_quantities),
                "required_physical_regime": derived["regime"],
                "real_cases_under_the_claim": [
                    {"case": case, "represents": verdict, "why": why}
                    for case, verdict, why in derived["real_cases"]
                ],
                "references": list(model.references),
                "capability_classification": derived["classification"],
                "finding": derived["finding"],
                "resolution": derived.get("resolution", ""),
                "note": derived.get("note", ""),
                "status": "REVIEWED",
            }
        )

    counts: dict[str, int] = {}
    case_counts: dict[str, int] = {}
    unresolved = []
    for row in rows:
        counts[row["capability_classification"]] = (
            counts.get(row["capability_classification"], 0) + 1
        )
        for case in row["real_cases_under_the_claim"]:
            case_counts[case["represents"]] = case_counts.get(case["represents"], 0) + 1
            if case["represents"] == "NO" and not row["resolution"]:
                unresolved.append(f"{row['model_id']}: {case['case']}")

    return {
        "schema": "capability_boundary_surface/1",
        "what_this_is": (
            "Every shipped model's published capability claim beside the "
            "regime its equations actually define, and the real physical "
            "cases a competent caller would read into the claim. The "
            "published half is read from the live records; the derived half "
            "is this audit's scientific reading, kept as reviewable data."
        ),
        "not_what_this_is": (
            "Not a record-versus-runtime check. That question was settled by "
            "the Contract Guard round and its agreement is assumed here, not "
            "re-derived, and is not evidence of scientific validity."
        ),
        "represents_legend": {
            "YES": "the equations carry this case",
            "BOUNDED": "the equations do not carry it and a declared validity condition refuses or UNKNOWNs it",
            "DISCLOSED": "the equations do not carry it, nothing refuses it, and the record says so",
            "NO": "the equations do not carry it, nothing refuses it, and the record does not say so",
        },
        "verdicts_are_as_found": (
            "Every 'represents' verdict below is what the audit FOUND. The "
            "three NO cases were repaired in this round and each carries a "
            "'resolution' on its model saying so; 'unresolved_no_cases' is the "
            "count that would still be open, and it is the one to read."
        ),
        "model_count": len(rows),
        "system_count": len({row["system"] for row in rows}),
        "classification_counts": dict(sorted(counts.items())),
        "real_case_counts": dict(sorted(case_counts.items())),
        "real_cases_reviewed": sum(case_counts.values()),
        "unresolved_no_cases": unresolved,
        "models_with_findings": sorted(
            row["model_id"] for row in rows if row["finding"]
        ),
        "models": rows,
    }


def main() -> int:
    payload = build()
    (ROUND / "MODEL_CAPABILITY_SURFACE.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"{payload['model_count']} models, {payload['system_count']} systems")
    print("classifications:", json.dumps(payload["classification_counts"]))
    print("real cases (as found):", json.dumps(payload["real_case_counts"]))
    print("unresolved NO cases:", payload["unresolved_no_cases"])
    for row in payload["models"]:
        if row["finding"]:
            print(f"  {row['finding']}  {row['model_id']}: {row['capability_classification']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
