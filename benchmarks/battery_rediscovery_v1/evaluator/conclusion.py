"""The preregistered v1 primary analysis and conclusion rule (frozen in PLAN.json before the run).

Scored instances are the (problem, axis) pairs with a truth.  Each is classified for representability
(``representability.classify``): R = REPRESENTABLE_EXACTLY or REPRESENTABLE_APPROXIMATELY, N = NOT_REPRESENTABLE,
U = UNKNOWN.  A Mind FAILURE is a scored instance whose outcome is not CORRECT or CORRECT_REFUSAL.

    share_N   = |failures in N| / |failures|
    acc_R     = Mind (CORRECT + CORRECT_REFUSAL) / |R|     acc_N likewise on N
    acc_R_c   = CAREFUL_BASELINE (CORRECT + CORRECT_REFUSAL) / |R|
"""

from __future__ import annotations

from typing import Any, Mapping

THRESHOLDS = {
    "majority_of_failures": 0.5,        # "most failures fall in NOT_REPRESENTABLE": share_N > 0.5
    "material_gap": 0.25,               # "materially better on REPRESENTABLE": acc_R - acc_N >= 0.25
    "not_poor_fraction": 0.5,           # not "poor where representable": acc_R >= 0.5 * acc_R_c
    "contributes_share": 0.25,          # representation contributes: share_N >= 0.25
    "min_instances_per_side": 3,        # |R| >= 3 and |N| >= 3, else INCONCLUSIVE
}
RULE = [
    "LEAKAGE_INVALIDATED if the pre-run or post-seal mutation suite, the pre-seal audit or the post-seal audit fails",
    "INCONCLUSIVE if the Mind arm did not run end to end, any sealed output does not re-execute identically, any Mind "
    "trace does not replay VERIFIED, any instance is UNKNOWN, or |R| < 3 or |N| < 3",
    "BENCHMARK_NOT_DISCRIMINATING if the best trivial arm's CORRECT + CORRECT_REFUSAL >= CAREFUL_BASELINE's",
    "REPRESENTATION_BOTTLENECK_NOT_CONFIRMED if the Mind arm has no failure",
    "REPRESENTATION_BOTTLENECK_CONFIRMED if share_N > 0.5 and acc_R - acc_N >= 0.25 and acc_R >= 0.5 * acc_R_c",
    "REPRESENTATION_CONTRIBUTES_BUT_NOT_PRIMARY if share_N >= 0.25 (and not confirmed)",
    "REPRESENTATION_BOTTLENECK_NOT_CONFIRMED otherwise",
]
GOOD = ("CORRECT", "CORRECT_REFUSAL")


def analyse(instances: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """``instances``: key -> {"class", "mind_outcome", "careful_outcome"} for every scored instance."""
    R = [k for k, v in instances.items() if v["class"] in ("REPRESENTABLE_EXACTLY", "REPRESENTABLE_APPROXIMATELY")]
    N = [k for k, v in instances.items() if v["class"] == "NOT_REPRESENTABLE"]
    U = [k for k, v in instances.items() if v["class"] == "UNKNOWN"]
    E = [k for k, v in instances.items() if v["class"] == "REPRESENTABLE_EXACTLY"]
    fail = [k for k, v in instances.items() if v["mind_outcome"] not in GOOD]

    def acc(keys: list[str], who: str) -> float | None:
        return sum(instances[k][who] in GOOD for k in keys) / len(keys) if keys else None

    return {"R": R, "N": N, "U": U, "EXACT": E, "failures": fail,
            "failures_in_N": [k for k in fail if k in N], "failures_in_R": [k for k in fail if k in R],
            "share_N": (len([k for k in fail if k in N]) / len(fail)) if fail else None,
            "acc_R_mind": acc(R, "mind_outcome"), "acc_N_mind": acc(N, "mind_outcome"),
            "acc_R_careful": acc(R, "careful_outcome"), "acc_N_careful": acc(N, "careful_outcome"),
            "acc_EXACT_mind": acc(E, "mind_outcome"), "acc_EXACT_careful": acc(E, "careful_outcome")}


def conclude(*, leakage_ok: bool, end_to_end: bool, replay_ok: bool, careful_total: int, trivial_best: int,
             a: Mapping[str, Any]) -> dict[str, Any]:
    t = THRESHOLDS
    checks = {"leakage_ok": leakage_ok, "end_to_end": end_to_end, "replay_ok": replay_ok, "careful_total": careful_total,
              "trivial_best": trivial_best, "n_R": len(a["R"]), "n_N": len(a["N"]), "n_U": len(a["U"]),
              "share_N": a["share_N"], "acc_R_mind": a["acc_R_mind"], "acc_N_mind": a["acc_N_mind"],
              "acc_R_careful": a["acc_R_careful"]}
    if not leakage_ok:
        verdict = "LEAKAGE_INVALIDATED"
    elif (not end_to_end or not replay_ok or a["U"] or len(a["R"]) < t["min_instances_per_side"]
          or len(a["N"]) < t["min_instances_per_side"]):
        verdict = "INCONCLUSIVE"
    elif trivial_best >= careful_total:
        verdict = "BENCHMARK_NOT_DISCRIMINATING"
    elif not a["failures"]:
        verdict = "REPRESENTATION_BOTTLENECK_NOT_CONFIRMED"
    else:
        majority = a["share_N"] > t["majority_of_failures"]
        material = (a["acc_R_mind"] - a["acc_N_mind"]) >= t["material_gap"]
        not_poor = a["acc_R_mind"] >= t["not_poor_fraction"] * a["acc_R_careful"]
        checks.update({"majority_of_failures_in_N": majority, "materially_better_on_R": material,
                       "not_poor_where_representable": not_poor})
        if majority and material and not_poor:
            verdict = "REPRESENTATION_BOTTLENECK_CONFIRMED"
        elif a["share_N"] >= t["contributes_share"]:
            verdict = "REPRESENTATION_CONTRIBUTES_BUT_NOT_PRIMARY"
        else:
            verdict = "REPRESENTATION_BOTTLENECK_NOT_CONFIRMED"
    return {"conclusion": verdict, "checks": checks}


__all__ = ["RULE", "THRESHOLDS", "analyse", "conclude"]
