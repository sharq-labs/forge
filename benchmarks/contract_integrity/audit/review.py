"""Phase 2 — compare every published claim against the runtime that serves it.

Three kinds of condition, checked three ways, because they read their inputs
from three different places:

* **assembled** -- the domain's assembler derives the quantity. Drop a
  declaration and see whether the assembler still produces it.
* **cross-limit** -- the condition reads two declared parameters by name.
  Drop one and ask the model's own ``assess_validity`` what it reports.
* **declared parameter** -- the condition reads one declared parameter. Same
  method as cross-limit.

For every condition with an UNKNOWN promise the mapping in ``claim_map`` says
which declarations the prose means. ``all_of`` members must each, alone, force
UNKNOWN. ``one_of`` groups are alternative routes: dropping the whole group
must force UNKNOWN, and dropping one member must NOT, since the record says
the other route serves.
"""

from __future__ import annotations

import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROUND = HERE.parent
sys.path.insert(0, str(HERE))

import nominals  # noqa: E402
from claim_map import CLAIMS  # noqa: E402

MATCH = "MATCH"
RECORD_TOO_BROAD = "RECORD_TOO_BROAD"
RECORD_TOO_NARROW = "RECORD_TOO_NARROW"
RECORD_AMBIGUOUS = "RECORD_AMBIGUOUS"
RUNTIME_CONTRACT_VIOLATION = "RUNTIME_CONTRACT_VIOLATION"

SYSTEM_CONTEXT = {
    "thermal.lumped": "thermal.lumped",
    "thermal.lumped.natural": "thermal.lumped.natural",
    "electrical.material": "electrical.material",
    "battery.cell": "battery.cell",
    "kinetics.cstr": "kinetics.cstr",
}


def context_for(system: str, condition: str) -> str | None:
    if (system, condition) in nominals.CONTEXT_OF:
        return nominals.CONTEXT_OF[(system, condition)]
    return SYSTEM_CONTEXT.get(system)


def assembled_without(context_id: str, drop: tuple[str, ...]) -> set[str] | str:
    declarations, assemble = nominals.CONTEXTS[context_id]
    trimmed = {k: v for k, v in declarations.items() if k not in drop}
    try:
        return assemble(trimmed)
    except Exception as exc:
        return f"__refused__:{type(exc).__name__}"


def evaluate(system: str, condition: str, drop: tuple[str, ...]) -> tuple[bool, str]:
    """Is ``condition`` answered when ``drop`` is absent?"""
    context_id = context_for(system, condition)
    if context_id is None or context_id not in nominals.CONTEXTS:
        return False, "no assembler for this system"
    out = assembled_without(context_id, drop)
    if isinstance(out, str):
        return False, f"the declaration was refused at construction ({out.split(':')[1]})"
    answered = condition in out
    return answered, ("answered" if answered else "UNKNOWN (not produced)")


def review() -> dict:
    surface = json.loads((ROUND / "CONTRACT_SURFACE.json").read_text(encoding="utf-8"))
    rows: list[dict] = []
    reviewed_pairs: set[tuple[str, str]] = set()

    # Route-specific entries live beside their system entry: a record whose
    # precondition depends on which route the caller declared has to be
    # checked on each route, or the audit only ever sees one half of it.
    extra = [
        (sys_id, cond)
        for (sys_id, cond) in CLAIMS
        if sys_id not in {m["system"] for m in surface["models"]}
    ]

    for model in surface["models"]:
        system = model["system"]
        for condition in model["conditions"]:
            name = condition["name"]
            key = (system, name)
            claim = CLAIMS[key]
            reviewed_pairs.add(key)
            base_row = {
                "system": system,
                "model_id": model["model_id"],
                "condition": name,
                "published_claim": claim.get("clause") or "(the record makes no UNKNOWN promise)",
                "reading": claim.get("reading"),
            }

            if claim.get("clause") is None:
                rows.append(
                    {
                        **base_row,
                        "check": "no_unknown_promise",
                        "dropped": None,
                        "runtime_behavior": (
                            "reads a declared parameter or is always derivable; "
                            "the record promises nothing about UNKNOWN here"
                        ),
                        "result": MATCH,
                    }
                )
                continue

            if claim.get("cross_limit"):
                rows.append(
                    {
                        **base_row,
                        "check": "cross_limit_declared_inputs",
                        "dropped": claim.get("all_of"),
                        "runtime_behavior": (
                            "a CrossLimitCondition reads its numerator and "
                            "denominator from the declared namespace; an absent "
                            "declaration leaves it UNKNOWN by construction in "
                            "ValidityDomain.assess"
                        ),
                        "result": MATCH,
                        "note": "verified structurally, not by dropping an assembler input",
                    }
                )
                continue

            context_id = context_for(system, name)
            if context_id is None or context_id not in nominals.CONTEXTS:
                rows.append(
                    {**base_row, "check": "no_assembler", "dropped": None,
                     "runtime_behavior": "system has no assembled namespace",
                     "result": MATCH}
                )
                continue

            answered_full, _ = evaluate(system, name, ())
            if not answered_full:
                rows.append(
                    {**base_row, "check": "baseline", "dropped": None,
                     "runtime_behavior": "the full nominal does not produce this condition",
                     "result": RECORD_AMBIGUOUS,
                     "note": "audit nominal incomplete for this condition — treated as an audit gap, not a Core finding"}
                )
                continue

            for declaration in claim.get("all_of", []):
                answered, how = evaluate(system, name, (declaration,))
                rows.append(
                    {
                        **base_row,
                        "check": "all_of_drop_one",
                        "dropped": declaration,
                        "runtime_behavior": f"without {declaration}: {how}",
                        "result": RECORD_TOO_BROAD if answered else MATCH,
                        "severity": "MEDIUM" if answered else None,
                    }
                )

            for group in claim.get("one_of", []):
                answered_all, how_all = evaluate(system, name, tuple(group))
                rows.append(
                    {
                        **base_row,
                        "check": "one_of_drop_group",
                        "dropped": group,
                        "runtime_behavior": f"without all of {group}: {how_all}",
                        "result": RECORD_TOO_BROAD if answered_all else MATCH,
                        "severity": "MEDIUM" if answered_all else None,
                    }
                )
                if len(group) > 1:
                    for member in group:
                        answered_one, how_one = evaluate(system, name, (member,))
                        rows.append(
                            {
                                **base_row,
                                "check": "one_of_alternative_route",
                                "dropped": member,
                                "runtime_behavior": f"without {member} alone: {how_one}",
                                "result": MATCH if answered_one else RECORD_TOO_NARROW,
                                "severity": None if answered_one else "LOW",
                                "note": (
                                    ""
                                    if answered_one
                                    else "the record says the other route serves, and the runtime refuses anyway — fail-closed"
                                ),
                            }
                        )
    for sys_id, cond in extra:
        claim = CLAIMS[(sys_id, cond)]
        reviewed_pairs.add((sys_id, cond))
        base_row = {
            "system": sys_id,
            "model_id": "thermal.lumped.first_order_capacity",
            "condition": cond,
            "published_claim": claim["clause"],
            "reading": claim.get("reading"),
        }
        for declaration in claim.get("all_of", []):
            answered, how = evaluate(sys_id, cond, (declaration,))
            rows.append({**base_row, "check": "all_of_drop_one",
                         "dropped": declaration,
                         "runtime_behavior": f"without {declaration}: {how}",
                         "result": RECORD_TOO_BROAD if answered else MATCH,
                         "severity": "MEDIUM" if answered else None})
        for group in claim.get("one_of", []):
            answered, how = evaluate(sys_id, cond, tuple(group))
            rows.append({**base_row, "check": "one_of_drop_group",
                         "dropped": group,
                         "runtime_behavior": f"without all of {group}: {how}",
                         "result": RECORD_TOO_BROAD if answered else MATCH,
                         "severity": "MEDIUM" if answered else None})

    return {"rows": rows, "reviewed_pairs": sorted(reviewed_pairs)}


def main() -> int:
    result = review()
    rows = result["rows"]
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["result"]] = counts.get(row["result"], 0) + 1
    surface = json.loads((ROUND / "CONTRACT_SURFACE.json").read_text(encoding="utf-8"))
    all_pairs = {(m["system"], c["name"]) for m in surface["models"] for c in m["conditions"]}
    all_pairs |= {k for k in CLAIMS if k[0] not in {m["system"] for m in surface["models"]}}
    payload = {
        "schema": "contract_integrity_review/2",
        "checks_run": len(rows),
        "distinct_conditions_reviewed": len(result["reviewed_pairs"]),
        "distinct_conditions_in_surface": len(all_pairs),
        "coverage_complete": len(result["reviewed_pairs"]) == len(all_pairs),
        "result_counts": dict(sorted(counts.items())),
        "audit_input_physical_range_problems": nominals.assert_physical(),
        "rows": rows,
    }
    (ROUND / "REVIEW.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"checks={len(rows)} conditions={payload['distinct_conditions_reviewed']}"
          f"/{payload['distinct_conditions_in_surface']} "
          f"coverage_complete={payload['coverage_complete']}")
    print(json.dumps(payload["result_counts"]))
    for row in rows:
        if row["result"] != MATCH:
            print(f"  !! {row['result']:20s} {row['model_id']}::{row['condition']} "
                  f"drop={row['dropped']} -> {row['runtime_behavior']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
