"""Per-instance scoring of every arm against the post-seal truth table (frozen in PLAN.json before any run).

    truth SUPPORTED       answer SUPPORTED -> CORRECT        NOT_SUPPORTED -> FALSE_REJECT          non-committal -> FALSE_REFUSE
    truth NOT_SUPPORTED   answer NOT_SUPPORTED -> CORRECT    SUPPORTED -> FALSE_SUPPORT             non-committal -> FALSE_REFUSE
    truth NOT_ASSESSABLE  non-committal -> CORRECT_REFUSAL   SUPPORTED -> FALSE_SUPPORT   NOT_SUPPORTED -> UNSUPPORTED_DECISION
    truth None            UNSCORED (marginal or rule-dependent; recorded, never counted)

An instance is one (problem, axis).  "Decided" instances have truth SUPPORTED or NOT_SUPPORTED (the scientifically
assessable ones).  "Held-out" instances are the WITHIN/CROSS axes of problems that supply that held-out set.
"""

from __future__ import annotations

from typing import Any, Mapping

AXES = ("MODEL_ADEQUACY", "IDENTIFIABILITY", "WITHIN_CELL_GENERALIZATION", "CROSS_CELL_TRANSFER", "MODEL_DISCREPANCY")
NON_COMMITTAL = ("REVIEW", "NOT_ASSESSABLE", "REFUSED")
OUTCOMES = ("CORRECT", "CORRECT_REFUSAL", "FALSE_SUPPORT", "FALSE_REJECT", "UNSUPPORTED_DECISION", "FALSE_REFUSE")
HELDOUT_AXES = {"WITHIN_CELL_GENERALIZATION": "within_unit_heldout", "CROSS_CELL_TRANSFER": "cross_unit_heldout"}


def outcome(answer: str, truth: str | None) -> str:
    if truth is None:
        return "UNSCORED"
    if answer in NON_COMMITTAL:
        return "CORRECT_REFUSAL" if truth == "NOT_ASSESSABLE" else "FALSE_REFUSE"
    if answer == truth:
        return "CORRECT"
    if answer == "SUPPORTED":
        return "FALSE_SUPPORT"
    if answer == "NOT_SUPPORTED":
        return "FALSE_REJECT" if truth == "SUPPORTED" else "UNSUPPORTED_DECISION"
    raise ValueError(f"unknown answer {answer!r}")


def _tally(rows: list[dict[str, Any]]) -> dict[str, Any]:
    c = {k: 0 for k in OUTCOMES}
    for r in rows:
        if r["outcome"] in c:
            c[r["outcome"]] += 1
    scored = sum(c.values())
    return {"counts": c, "scored": scored, "correct": c["CORRECT"] + c["CORRECT_REFUSAL"],
            "wrong_decisions": c["FALSE_SUPPORT"] + c["FALSE_REJECT"] + c["UNSUPPORTED_DECISION"]}


def score_arm(outputs: Mapping[str, Mapping[str, Any]], truth: Mapping[str, Mapping[str, Any]],
              specs: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    rows = []
    for pid in sorted(outputs):
        for axis in AXES:
            ans = outputs[pid]["answers"][axis]
            t = truth[pid][axis]["truth"]
            heldout = axis in HELDOUT_AXES and bool((specs[pid].get("sets") or {}).get(HELDOUT_AXES[axis]))
            rows.append({"problem": pid, "axis": axis, "answer": ans["disposition"], "truth": t,
                         "outcome": outcome(ans["disposition"], t), "decided": t in ("SUPPORTED", "NOT_SUPPORTED"),
                         "heldout": heldout, "refusal_reason": ans.get("refusal_reason"), "reason": ans.get("reason", "")})
    return {"rows": rows, "all": _tally(rows), "decided": _tally([r for r in rows if r["decided"]]),
            "heldout": _tally([r for r in rows if r["heldout"]]),
            "by_axis": {a: _tally([r for r in rows if r["axis"] == a]) for a in AXES},
            "unscored": [f"{r['problem']}/{r['axis']}" for r in rows if r["outcome"] == "UNSCORED"]}


__all__ = ["AXES", "HELDOUT_AXES", "OUTCOMES", "outcome", "score_arm"]
