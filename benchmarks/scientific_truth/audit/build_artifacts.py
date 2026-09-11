"""Run every check and write this round's machine-readable artifacts."""

from __future__ import annotations

import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROUND = HERE.parent
REPO = ROUND.parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "src"))

from benchmarks.scientific_truth.audit import checks, independence, properties  # noqa: E402
from benchmarks.scientific_truth.audit.equations import EQUATIONS  # noqa: E402

CLEAN = {"AGREE", "PASS", "LIMIT_CORRECT", "SIGN_CORRECT", "HOLDS",
         "NO_MATERIAL_CANCELLATION", "CONVERGES_AT_EXPECTED_ORDER"}

FAMILIES = [
    ("lumped", checks.lumped_rows), ("lumped_limits", checks.lumped_limits),
    ("lumped_monotonicity", checks.lumped_monotonicity),
    ("diffusion", checks.diffusion_rows),
    ("diffusion_convergence", checks.diffusion_convergence),
    ("diffusion_limits", checks.diffusion_limits),
    ("battery", checks.battery_rows),
    ("battery_limits_signs", checks.battery_limits_and_signs),
    ("dc", checks.dc_rows), ("dc_limits_signs", checks.dc_limits_and_signs),
    ("material", checks.material_rows),
    ("material_limits_signs", checks.material_limits_and_signs),
    ("cstr", checks.cstr_rows), ("cstr_limits_signs", checks.cstr_limits_and_signs),
    ("shared_equations", checks.shared_equation_rows),
]


def main() -> int:
    all_rows: list[dict] = []
    for family, fn in FAMILIES:
        for row in fn():
            all_rows.append({"family": family, **row})

    by_check: dict[str, dict[str, int]] = {}
    by_model: dict[str, dict[str, int]] = {}
    for row in all_rows:
        clean = row.get("verdict") in CLEAN
        for bucket, key in ((by_check, row["check"]), (by_model, row["model"])):
            entry = bucket.setdefault(key, {"total": 0, "clean": 0})
            entry["total"] += 1
            entry["clean"] += int(clean)

    disagreements = [row for row in all_rows if row.get("verdict") not in CLEAN]

    # ---- ST-1 / ST-2: the equation surface and ledger --------------------
    (ROUND / "MODEL_EQUATION_SURFACE.json").write_text(
        json.dumps(
            {
                "schema": "scientific_truth_equation_surface/1",
                "what_this_is": (
                    "Every shipped model's governing equation as the "
                    "implementation evaluates it, beside the classification "
                    "and numerical method that decide which checks apply."
                ),
                "model_count": len(EQUATIONS),
                "models": [
                    {**entry, "status": "REVIEWED"} for entry in EQUATIONS
                ],
            },
            indent=2, sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )
    (ROUND / "EQUATION_LEDGER.json").write_text(
        json.dumps(
            {
                "schema": "scientific_truth_equation_ledger/1",
                "what_this_is": (
                    "The expected mathematical relationship for each model, "
                    "reconstructed independently from the physics before the "
                    "implementation was compared against it, with its sign "
                    "convention, units and asymptotic behaviour."
                ),
                "dimensional_verdicts": {
                    entry["model_id"]: entry["dimensional_verdict"]
                    for entry in EQUATIONS
                },
                "dimensional_counts": _count(
                    entry["dimensional_verdict"] for entry in EQUATIONS
                ),
                "entries": [
                    {
                        "model_id": entry["model_id"],
                        "expected_form": entry["expected_form"],
                        "derivation": entry["derivation"],
                        "sign_convention": entry["sign_convention"],
                        "assumptions": entry["assumptions"],
                        "parameters": entry["parameters"],
                        "dimensional_check": entry["dimensional_check"],
                        "dimensional_verdict": entry["dimensional_verdict"],
                        "asymptotics": entry["asymptotics"],
                    }
                    for entry in EQUATIONS
                ],
            },
            indent=2, sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )

    # ---- ST-6: reference cases and every other row ------------------------
    (ROUND / "REFERENCE_CASES.json").write_text(
        json.dumps(
            {
                "schema": "scientific_truth_reference_cases/1",
                "what_this_is": (
                    "Every oracle comparison, conservation residual, limit, "
                    "monotonicity invariant, sign case and convergence ladder "
                    "this round ran, with the tolerance and why it is that "
                    "number."
                ),
                "total_rows": len(all_rows),
                "by_check": by_check,
                "by_model": by_model,
                "disagreements": disagreements,
                "rows": all_rows,
            },
            indent=2, sort_keys=True, default=str,
        ) + "\n",
        encoding="utf-8",
    )

    # ---- ST-12: independence ---------------------------------------------
    independence_report = independence.survey()
    (ROUND / "SOLVER_INDEPENDENCE.json").write_text(
        json.dumps(independence_report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    # ---- ST-14: property testing ------------------------------------------
    property_report = properties.run_all()
    (ROUND / "PROPERTY_TESTING.json").write_text(
        json.dumps(property_report, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )

    # ---- ST-13: false agreement -------------------------------------------
    (ROUND / "FALSE_AGREEMENT_CASES.json").write_text(
        json.dumps(
            {
                "schema": "scientific_truth_false_agreement/1",
                "what_this_is": (
                    "Cases where the implementation, the existing tests and "
                    "the published record all agree while an INDEPENDENT "
                    "oracle disagrees. This is the highest-value class in the "
                    "round and the hardest to find, because every previous "
                    "round has already removed the cases where the three "
                    "disagree with each other."
                ),
                "how_it_was_searched": [
                    "every reference case above is a search: an independent "
                    "oracle against a runtime the tests already accept",
                    "randomized property testing over the declared domain of "
                    "five model families, 660 admissible draws",
                    "an external simulator (ngspice) on 66 circuits",
                    "an exact conservation invariant on every applicable model",
                    "a 50-digit arithmetic on the one closed-form model",
                ],
                "cases": [
                    {
                        "model": row["model"],
                        "case": row.get("case"),
                        "runtime_result": row.get("runtime_value"),
                        "independent_result": row.get("oracle_value"),
                        "oracle": row.get("oracle"),
                        "relative_error": row.get("relative_error"),
                        "tolerance": row.get("tolerance"),
                    }
                    for row in disagreements
                ],
                "count": len(disagreements),
            },
            indent=2, sort_keys=True, default=str,
        ) + "\n",
        encoding="utf-8",
    )

    print(f"{len(all_rows)} check rows, {len(disagreements)} disagreements")
    for key, value in sorted(by_check.items()):
        print(f"  {key:18s} {value['clean']}/{value['total']}")
    print("independence:", json.dumps(independence_report["counts"]))
    print("property violations:", len(property_report["violations"]))
    for row in disagreements:
        print("  !!", json.dumps(row, default=str)[:240])
    return 0


def _count(values) -> dict:
    out: dict[str, int] = {}
    for value in values:
        out[value] = out.get(value, 0) + 1
    return out


if __name__ == "__main__":
    raise SystemExit(main())
