"""Scoring, the historical-rediscovery comparison and the preregistered development conclusion (see PLAN.json)."""

from __future__ import annotations

from typing import Any, Mapping

from ..candidate.common import AXES, NON_COMMITTAL, NOT_ASSESSABLE, NOT_SUPPORTED, SUPPORTED

TRIVIAL = ("ALWAYS_FIT", "ALWAYS_REFUSE")
OUTCOMES = ("CORRECT", "CORRECT_REFUSAL", "FALSE_SUPPORT", "FALSE_REJECT", "UNSUPPORTED_DECISION", "FALSE_REFUSE")
REPRESENTATION_KEYS = {"problem_refused", "empty_region", "unidentifiable_passive_association"}


def outcome(answer: str, truth: str | None) -> str:
    if truth is None:
        return "UNSCORED"
    if answer in NON_COMMITTAL:
        return "CORRECT_REFUSAL" if truth == NOT_ASSESSABLE else "FALSE_REFUSE"
    if answer == truth:
        return "CORRECT"
    if answer == SUPPORTED:
        return "FALSE_SUPPORT"
    if answer == NOT_SUPPORTED:
        return "FALSE_REJECT" if truth == SUPPORTED else "UNSUPPORTED_DECISION"
    raise ValueError(answer)


def score_arm(outputs: Mapping[str, Mapping[str, Any]], truth: Mapping[str, Any]) -> dict[str, Any]:
    per, counts = {}, {k: 0 for k in OUTCOMES}
    for pid, rec in sorted(outputs.items()):
        for axis in AXES:
            t = truth["table"][pid][axis]["truth"]
            a = rec["answers"][axis]["disposition"]
            o = outcome(a, t)
            per[f"{pid}/{axis}"] = {"answer": a, "truth": t, "outcome": o}
            if o in counts:
                counts[o] += 1
    scored = sum(counts.values())
    return {"per_instance": per, "counts": counts, "scored": scored,
            "correct_total": counts["CORRECT"] + counts["CORRECT_REFUSAL"]}


def best_baseline(scores: Mapping[str, Mapping[str, Any]]) -> str:
    cands = [a for a in scores if a != "MIND"]
    return sorted(cands, key=lambda a: (-scores[a]["correct_total"], scores[a]["counts"]["FALSE_SUPPORT"],
                                        scores[a]["counts"]["FALSE_REJECT"] + scores[a]["counts"]["UNSUPPORTED_DECISION"],
                                        a))[0]


def _mind_cause(rec: Mapping[str, Any], axis: str) -> str:
    """Why a non-committal Mind answer is non-committal: REPRESENTATION/INTERFACE or EVIDENCE."""
    ans = rec["answers"][axis]
    if ans["reason"].startswith("the declared 1RC family is not in"):
        return "REPRESENTATION"
    if ans["reason"] == "no held-out set of this kind is supplied":
        return "EVIDENCE"
    det = rec["detail"]
    seed = str(rec["primary_seed"])
    runs = []
    if axis == "IDENTIFIABILITY":
        runs = [det["probes"]["RELAXATION"]["per_seed"][seed]]
    else:
        target = "within_cell_heldout" if axis == "WITHIN_CELL_GENERALIZATION" else "cross_cell_heldout"
        runs = [v["per_seed"][seed] for v in det["prediction"].values() if v["set"] == target]
    for r in runs:
        if r["translation"]["disposition"] not in NON_COMMITTAL:
            continue
        if r["translation"]["key"] in REPRESENTATION_KEYS or r.get("queries_refused"):
            return "REPRESENTATION"
        c = r.get("conclusion") or {}
        refuted = len(c.get("diagnostics", {}).get("refuted", []))
        # the Mind's own statement that its hypothesis space lacks the dependence: every fitted rival refuted, or the
        # leading rival misfits beyond the replicate noise ("the rivals entertained do not contain the dependence")
        reason = c.get("reason", "")
        if "do not contain the dependence" in reason or (refuted and reason.startswith("no rival is both fitted and unrefuted")):
            return "REPRESENTATION"
    return "EVIDENCE"


def rediscovery(mind: Mapping[str, Mapping[str, Any]], truth: Mapping[str, Any]) -> dict[str, Any]:
    rows = {}
    for pid, rec in sorted(mind.items()):
        for axis in AXES:
            t = truth["table"][pid][axis]
            a = rec["answers"][axis]["disposition"]
            if t["history_class"] == "HISTORY_NOT_ASSESSABLE":
                cls = "HISTORY_NOT_ASSESSABLE"
            else:
                cls = "AGREED_WITH_HISTORY" if outcome(a, t["truth"]) in ("CORRECT", "CORRECT_REFUSAL") \
                    else "DISAGREED_WITH_HISTORY"
            rows[f"{pid}/{axis}"] = {"mind": a, "history": t["truth"], "class": cls,
                                     "mind_reason": rec["answers"][axis]["reason"][:300]}
    hypotheses = []
    for pid, rec in sorted(mind.items()):
        det = rec["detail"]
        seed = str(rec["primary_seed"])
        runs = {"RELAXATION": det["probes"]["RELAXATION"]["per_seed"][seed]}
        runs.update({f"PREDICTION[{k}]": v["per_seed"][seed] for k, v in det["prediction"].items()})
        for name, r in runs.items():
            c = r.get("conclusion")
            if not c:
                continue
            if c["laws"]:
                for law in c["laws"]:
                    hypotheses.append({"problem": pid, "probe": name, "class": "NEW_UNVALIDATED_HYPOTHESIS",
                                       "kind": c["kind"], "law": law})
            elif c["kind"] == "unidentifiable_passive_association":
                hypotheses.append({"problem": pid, "probe": name, "class": "NEW_UNVALIDATED_HYPOTHESIS",
                                   "kind": c["kind"], "statement": c["reason"]})
    return {"axes": rows, "new_hypotheses": hypotheses}


def attention(mind: Mapping[str, Mapping[str, Any]], truth: Mapping[str, Any]) -> dict[str, Any]:
    """The brief's 'pay special attention' items, read from the Mind's primary answers."""
    def ans(pid: str, axis: str) -> str:
        return mind[pid]["answers"][axis]["disposition"]

    supports = [f"{p}/{a}" for p in mind for a in AXES if ans(p, a) == SUPPORTED and truth["table"][p][a]["truth"] != SUPPORTED]
    return {
        "parameter_non_identifiability (P1)": {"mind": ans("P1", "IDENTIFIABILITY"),
                                               "independently_found": ans("P1", "IDENTIFIABILITY") == NOT_SUPPORTED},
        "within_cell_limitations (P1 applicability; P2 constant-current failure)": {
            "mind": {p: ans(p, "WITHIN_CELL_GENERALIZATION") for p in mind}},
        "cross_cell_transfer (P1 failure)": {"mind": ans("P1", "CROSS_CELL_TRANSFER"),
                                             "independently_found": ans("P1", "CROSS_CELL_TRANSFER") == NOT_SUPPORTED},
        "structured_model_discrepancy": {"mind": {p: ans(p, "MODEL_DISCREPANCY") for p in mind},
                                         "independently_found": any(ans(p, "MODEL_DISCREPANCY") == NOT_SUPPORTED for p in mind)},
        "applicability_limits": {p: [r for r in (mind[p]["detail"]["prediction"][k]["per_seed"][str(mind[p]["primary_seed"])]
                                                 .get("conclusion", {}).get("diagnostics", {}).get("extrapolates"),)]
                                 for p in mind for k in mind[p]["detail"]["prediction"]},
        "refused_unsupported_conclusions": {"false_support_instances": supports, "none": not supports},
    }


def conclusion(*, leakage_ok: bool, mind_end_to_end: bool, mind_replay_ok: bool, scores: Mapping[str, Mapping[str, Any]],
               mind: Mapping[str, Mapping[str, Any]], truth: Mapping[str, Any]) -> dict[str, Any]:
    best = best_baseline(scores)
    m, b = scores["MIND"], scores[best]
    nontrivial = [a for a in scores if a not in TRIVIAL]
    best_nontrivial = max(scores[a]["correct_total"] for a in nontrivial)
    trivial_best = max(scores[a]["correct_total"] for a in TRIVIAL)
    causes = {}
    for pid, rec in mind.items():
        for axis in AXES:
            if truth["table"][pid][axis]["truth"] is None:
                continue
            if rec["answers"][axis]["disposition"] in NON_COMMITTAL:
                causes[f"{pid}/{axis}"] = _mind_cause(rec, axis)
    rep = sum(1 for c in causes.values() if c == "REPRESENTATION")
    checks = {"leakage_ok": leakage_ok, "mind_end_to_end": mind_end_to_end, "mind_replay_ok": mind_replay_ok,
              "best_baseline": best, "mind_correct_total": m["correct_total"], "best_baseline_correct_total": b["correct_total"],
              "mind_false_support": m["counts"]["FALSE_SUPPORT"], "best_baseline_false_support": b["counts"]["FALSE_SUPPORT"],
              "best_nontrivial_correct_total": best_nontrivial, "best_trivial_correct_total": trivial_best,
              "mind_noncommittal_causes": causes, "mind_representation_noncommittal": rep, "mind_scored": m["scored"]}
    if not leakage_ok:
        verdict = "LEAKAGE_INVALIDATED"
    elif not (mind_end_to_end and mind_replay_ok):
        verdict = "INCONCLUSIVE"
    elif m["correct_total"] > b["correct_total"] and m["counts"]["FALSE_SUPPORT"] <= b["counts"]["FALSE_SUPPORT"]:
        verdict = "PROMISING_SIGNAL"
    elif trivial_best >= best_nontrivial:
        verdict = "BENCHMARK_TOO_EASY"
    elif 2 * rep >= m["scored"]:
        verdict = "REPRESENTATION_BOTTLENECK"
    else:
        verdict = "NO_MEASURED_ADVANTAGE"
    return {"conclusion": verdict, "checks": checks}


__all__ = ["OUTCOMES", "attention", "best_baseline", "conclusion", "outcome", "rediscovery", "score_arm"]
