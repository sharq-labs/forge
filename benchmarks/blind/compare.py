"""Compare the frozen truth with a Forge run. Changes neither.

    python benchmarks/blind/compare.py [--run FORGE_FIRST_RUN.json]

Writes ``COMPARISON.json`` — or ``COMPARISON_POST_FIX.json`` for a post-fix
run — and prints the scorecard. It reads ``TRUTH.json`` and the run artifact
and writes to neither.

Denominators, and why there are several
---------------------------------------

One accuracy number over 444 cases would average together four different kinds
of claim, and the averaging is what makes such a number useless:

* a case decided by ``biot_number <= 0.1`` tests an approximation criterion
  with a citation;
* a case decided by ``radiation_to_convection_ratio <= 0.1`` tests a
  10 %-neglect allowance with no located source — agreement says the runtime
  implements a convention correctly and says nothing about physics;
* a case decided by an absent declaration tests the record's semantics;
* a case placed within the resolution floor of its bound tests floating point.

So every figure below carries the denominator it was computed over, the last
of those is excluded from the primary one, and the science and policy
scorecards are never added together.
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
V1 = HERE / "v1"
sys.path.insert(0, str(HERE.parent.parent))

from benchmarks.blind import bound_registry as reg          # noqa: E402


def _condition_names(keys) -> set[str]:
    """Strip the model prefix. A condition is compared by NAME.

    The truth attributes a condition to the model that declares it, and so
    does the run — but `temperature` and `reference_resistance` are declared by
    two material models each, and the electro-thermal boundary reports both.
    Comparing the qualified keys would score a report that named one of the two
    as having missed the other, which is a bookkeeping difference and not a
    disagreement about the case.
    """
    return {key.split("::")[-1] for key in keys}


def classify_reasons(truth_names: set[str], forge_names: set[str]) -> str:
    if not truth_names and not forge_names:
        return "NOT_APPLICABLE"
    if truth_names == forge_names:
        return "EXACT_REASON_MATCH"
    if forge_names and forge_names < truth_names:
        return "VALID_REASON_SUBSET"
    if truth_names and truth_names < forge_names:
        return "VALID_REASON_SUPERSET"
    if forge_names & truth_names:
        return "PARTIAL_OVERLAP"
    if not forge_names:
        return "MISSING_REASON"
    return "WRONG_REASON"


def classify_causal(causal: set[str], forge_names: set[str], status: str) -> str:
    if status in ("NOT_APPLICABLE", "UNRESOLVED"):
        return "NOT_SCORED"
    if not causal:
        return "NOT_SCORED"
    if causal <= forge_names:
        return "EXACT_CAUSAL_MATCH"
    if forge_names:
        return "VALID_CAUSAL_ALTERNATE" if forge_names & causal else \
            "WRONG_CAUSAL_MECHANISM"
    return "MISSING_CAUSAL_REASON"


def compare(truths: dict, results: dict) -> list[dict]:
    rows: list[dict] = []
    for case_id, truth in sorted(truths.items()):
        forge = results.get(case_id)
        if forge is None:
            rows.append({"case_id": case_id, "verdict_match": "NO_RESULT"})
            continue
        expected = truth["independent_verdict"]
        actual = forge["verdict"]
        truth_reasons = set(truth["reason_names"])
        if truth["independent_verdict"] == "NOT_SUPPORTED":
            forge_reasons = _condition_names(forge["violated"])
        elif truth["independent_verdict"] == "INSUFFICIENT_EVIDENCE":
            forge_reasons = _condition_names(forge["unknown"])
        else:
            forge_reasons = (_condition_names(forge["violated"])
                             | _condition_names(forge["unknown"]))
        causal = {name.split("::")[-1] for name in truth["causal_catcher_set"]}

        # False accept / false reject, in the direction that matters. A refusal
        # the truth does not support is a FALSE REJECT; an acceptance the truth
        # refuses is a FALSE ACCEPT, and only the second can put a bad design
        # into service.
        truth_refuses = expected in ("NOT_SUPPORTED", "REJECTED_AT_BOUNDARY")
        forge_refuses = actual in ("NOT_SUPPORTED", "REJECTED_AT_BOUNDARY")
        if expected == actual:
            direction = "MATCH"
        elif truth_refuses and not forge_refuses:
            direction = "FALSE_ACCEPT"
        elif forge_refuses and not truth_refuses:
            direction = "FALSE_REJECT"
        else:
            direction = "OTHER_MISMATCH"

        rows.append({
            "case_id": case_id,
            "system": truth["system"],
            "family": truth["family"],
            "truth_class": truth["truth_class"],
            "confidence": truth["truth_confidence_class"],
            "stratum": truth["boundary_stratum"],
            "expected": expected,
            "actual": actual,
            "verdict_match": "EXACT_VERDICT_MATCH" if expected == actual
                             else "VERDICT_MISMATCH",
            "direction": direction,
            "reason_match": classify_reasons(truth_reasons, forge_reasons),
            "causal_match": classify_causal(causal, forge_reasons,
                                            truth["primary_catcher_status"]),
            "catcher_status": truth["primary_catcher_status"],
            "truth_reasons": sorted(truth_reasons),
            "forge_reasons": sorted(forge_reasons),
            "policy_dependencies": truth["policy_dependencies"],
            "forge_note": forge.get("note", ""),
            "forge_detail": forge.get("detail", "")[:200],
        })
    return rows


def _tally(rows, key, predicate=None):
    return collections.Counter(
        row[key] for row in rows if predicate is None or predicate(row))


def scorecard(rows: list[dict]) -> dict:
    primary = [r for r in rows if r["confidence"] == "DECIDED"
               and r["truth_class"] != "UNRESOLVED"]
    sensitive = [r for r in rows if r["confidence"] == "ARITHMETIC_SENSITIVE"]

    def block(subset):
        n = len(subset)
        matches = sum(1 for r in subset if r["verdict_match"]
                      == "EXACT_VERDICT_MATCH")
        return {
            "n": n,
            "verdict_matches": matches,
            "verdict_accuracy": f"{matches}/{n}" + (
                f" ({100.0 * matches / n:.1f}%)" if n else ""),
            "false_accepts": sum(1 for r in subset
                                 if r["direction"] == "FALSE_ACCEPT"),
            "false_rejects": sum(1 for r in subset
                                 if r["direction"] == "FALSE_REJECT"),
            "other_mismatches": sum(1 for r in subset
                                    if r["direction"] == "OTHER_MISMATCH"),
        }

    by_class = {name: block([r for r in primary if r["truth_class"] == name])
                for name in sorted({r["truth_class"] for r in primary})}
    by_system = {name: block([r for r in primary if r["system"] == name])
                 for name in sorted({r["system"] for r in primary})}
    by_stratum = {name: block([r for r in primary if r["stratum"] == name])
                  for name in sorted({r["stratum"] for r in primary})}

    reason_scored = [r for r in primary
                     if r["reason_match"] != "NOT_APPLICABLE"]
    causal_scored = [r for r in primary if r["causal_match"] != "NOT_SCORED"]

    return {
        "primary": block(primary),
        "arithmetic_sensitive": block(sensitive),
        "denominator_note":
            "The primary denominator is the DECIDED, non-UNRESOLVED set. "
            "ARITHMETIC_SENSITIVE cases are reported beside it and never "
            "inside it: within the resolution floor the answer is decided by "
            "which implementation rounds which way.",
        "by_truth_class": by_class,
        "by_system": by_system,
        "by_boundary_stratum": by_stratum,
        "reasons": {
            "denominator": len(reason_scored),
            **dict(_tally(reason_scored, "reason_match")),
        },
        "reasons_science_only": {
            "denominator": sum(1 for r in reason_scored
                               if not r["policy_dependencies"]),
            **dict(_tally([r for r in reason_scored
                           if not r["policy_dependencies"]], "reason_match")),
        },
        "reasons_policy_only": {
            "denominator": sum(1 for r in reason_scored
                               if r["policy_dependencies"]),
            **dict(_tally([r for r in reason_scored
                           if r["policy_dependencies"]], "reason_match")),
        },
        "causal": {
            "denominator": len(causal_scored),
            **dict(_tally(causal_scored, "causal_match")),
            "not_scored_no_unique_primary": sum(
                1 for r in primary
                if r["catcher_status"] == "NO_UNIQUE_PRIMARY"),
            "note": "NO_UNIQUE_PRIMARY is not a failure. Where several "
                    "conditions are each violated, repairing any one leaves "
                    "the verdict where it was, so none is uniquely causal.",
        },
        # "truth said X, Forge said Y" -> how many. Written as one string per
        # shape because a JSON object cannot key on a pair, and the shape is
        # what a reader wants first: it says whether the round found one
        # systematic disagreement or a scatter of unrelated ones.
        "mismatch_shapes": {
            f"{expected} -> {actual}": count
            for (expected, actual), count in collections.Counter(
                (r["expected"], r["actual"]) for r in primary
                if r["verdict_match"] == "VERDICT_MISMATCH").most_common()},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", default="FORGE_FIRST_RUN.json")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    truths = json.loads((V1 / "TRUTH.json").read_text(encoding="utf-8"))["truths"]
    artifact = json.loads((V1 / args.run).read_text(encoding="utf-8"))
    if artifact["case_set_digest"] != json.loads(
            (V1 / "FREEZE.json").read_text(encoding="utf-8"))["case_set_digest"]:
        print("REFUSED: the run was made against a different case set")
        return 1

    rows = compare(truths, artifact["results"])
    card = scorecard(rows)
    out = V1 / (args.out or (
        "COMPARISON.json" if artifact["run_kind"] == "FIRST_RUN"
        else "COMPARISON_POST_FIX.json"))
    out.write_text(json.dumps({
        "run_kind": artifact["run_kind"],
        "run_head_sha": artifact["head_sha"],
        "case_set_digest": artifact["case_set_digest"],
        "scorecard": card,
        "rows": rows,
    }, sort_keys=True, indent=1, allow_nan=False) + "\n", encoding="utf-8")

    print(json.dumps(card, indent=1, sort_keys=True))
    print(f"\nwrote {out.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
