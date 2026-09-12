"""How much of the v2 result rests on a number nobody printed in a source.

Four of the fifty-four bounds this challenge relies on are classed
INTERNAL_POLICY in BOUND_REGISTER.json: a repository convention with no source
behind the value. This asks, for every case those bounds decided, whether the
verdict survives a reasonable alternative value.

No production threshold is changed. The frozen condition values are re-read
against alternative bounds, here, and nothing is written back. A verdict that
moves is not wrong -- it is a verdict resting on a convention, and saying which
ones those are is the point.
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib

#: Alternatives a reasonable reviewer might have chosen instead, and why.
ALTERNATIVES = {
    "geometry_route_ratio": {
        "shipped": (1.0 / 3.0, 3.0),
        "variants": {
            "cylinder_only (factor 2)": (0.5, 2.0),
            "generous (factor 4)": (0.25, 4.0),
        },
        "why": (
            "the shape factor between L_c and V/A_s is 1 for a plane wall, 2 "
            "for a long cylinder and 3 for a sphere. Admitting the whole range "
            "to the sphere is a choice; stopping at the cylinder is another."
        ),
    },
    "convection_conductance_agreement_ratio": {
        "shipped": (0.5, 2.0),
        "variants": {
            "tight (factor 1.5)": (1.0 / 1.5, 1.5),
            "loose (factor 3)": (1.0 / 3.0, 3.0),
        },
        "why": (
            "the record itself says no source prints a factor for this "
            "comparison. Correlation scatter, shape idealisation and film "
            "property evaluation are real; where they stop is a judgement."
        ),
    },
    "polarization_unmodelled_fraction": {
        "shipped": (None, 0.05),
        "variants": {"strict (2%)": (None, 0.02), "lenient (10%)": (None, 0.10)},
        "why": "the relaxation form is standard; the 5% budget is a repository choice.",
    },
    "reference_reduced_debye_temperature": {
        "shipped": (0.2, None),
        "variants": {"stricter (1/4)": (0.25, None), "looser (1/6)": (1.0 / 6.0, None)},
        "why": (
            "chosen to admit beryllium, which clears theta_D/5 by 2%. A "
            "threshold picked to accept one real datasheet is defensible and "
            "is still a choice."
        ),
    },
}


def decide(value: float, low: float | None, high: float | None) -> str:
    if low is not None and value < low:
        return "VIOLATED"
    if high is not None and value > high:
        return "VIOLATED"
    return "SATISFIED"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--truth", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    truth = [json.loads(line) for line in pathlib.Path(args.truth).read_text().splitlines()]

    per_bound = {}
    robust = fragile = 0
    fragile_cases = []
    for name, spec in ALTERNATIVES.items():
        low, high = spec["shipped"]
        touched = []
        moved = collections.Counter()
        for record in truth:
            value = (record.get("condition_values") or {}).get(name)
            if value is None:
                continue
            shipped = decide(value, low, high)
            touched.append(record["case_id"])
            for label, (alt_low, alt_high) in spec["variants"].items():
                if decide(value, alt_low, alt_high) != shipped:
                    moved[label] += 1
                    if record["case_id"] not in fragile_cases:
                        fragile_cases.append(record["case_id"])
        any_moved = set()
        for record in truth:
            value = (record.get("condition_values") or {}).get(name)
            if value is None:
                continue
            shipped = decide(value, low, high)
            if any(
                decide(value, a, b) != shipped for a, b in spec["variants"].values()
            ):
                any_moved.add(record["case_id"])
        per_bound[name] = {
            "class": "INTERNAL_POLICY",
            "why_it_is_a_convention": spec["why"],
            "shipped_bounds": spec["shipped"],
            "cases_where_this_bound_was_computable": len(touched),
            "cases_whose_condition_verdict_moves_under_an_alternative": len(any_moved),
            "per_variant_moves": dict(moved),
        }
        robust += len(touched) - len(any_moved)
        fragile += len(any_moved)

    payload = {
        "schema": "blind_v2_policy_sensitivity/1",
        "what_this_measures": (
            "scientific defensibility, not correctness. A condition verdict "
            "that survives every reasonable alternative value rests on the "
            "physics; one that moves rests on the convention."
        ),
        "production_thresholds_changed": False,
        "frozen_truth_changed": False,
        "condition_verdicts_robust": robust,
        "condition_verdicts_policy_boundary_dependent": fragile,
        "per_bound": per_bound,
        "policy_boundary_dependent_cases": sorted(set(fragile_cases)),
    }
    pathlib.Path(args.out).write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({k: v for k, v in payload.items() if k != "policy_boundary_dependent_cases"}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
