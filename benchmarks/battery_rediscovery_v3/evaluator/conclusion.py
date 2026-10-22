"""The preregistered hypotheses, robustness check and single conclusion of battery_rediscovery_v3 (frozen in PLAN.json).

Input: one record per PRIMARY instance (problem, axis): ``{"key", "truth", "heldout", "answers": {arm: disposition}}``.
The bridge problems never enter.  Outcomes per (arm, instance) follow v2's scoring table (``score.outcome``): CORRECT,
CORRECT_REFUSAL, FALSE_SUPPORT, FALSE_REJECT, UNSUPPORTED_DECISION, FALSE_REFUSE, or UNSCORED when the truth is None.

* decided   = truth SUPPORTED or NOT_SUPPORTED;   unassessable = truth NOT_ASSESSABLE;   scored = decided + unassessable.
* correct   = CORRECT + CORRECT_REFUSAL.          FS = FALSE_SUPPORT, FR = FALSE_REFUSE (over scored instances).
* held-out  = decided instances of the WITHIN/CROSS axes of problems that supply that set.
* FS_material(X vs Y, base N) iff FS(X) > FS(Y) and (FS(X) - FS(Y) >= FS_MATERIAL_EXTRA or FS(X) > FS_MATERIAL_RATE * N).

Criteria (C) and hypotheses (H):

C1 PRIMARY COMPARISON  paired over decided instances, combined vs OLD_MIND: wins > losses and the exact two-sided sign
                       test p <= SIGN_TEST_ALPHA.
C2                     not FS_material(combined vs OLD_MIND, base = decided N) over all scored instances.
C3 (= H2)              for X in REPRESENTATION_ONLY, SEMANTIC_ROLES_ONLY: correct_decided(combined) > correct_decided(X)
                       and not FS_material(combined vs X, base = decided N) on decided instances.
C4                     on held-out decided instances: correct(combined) > correct(OLD_MIND), H3 holds.
H1                     FR(combined) <= FR(OLD_MIND) - max(MIN_FR_REDUCTION, ceil(MIN_FR_REDUCTION_FRACTION * scored N))
                       and C2.
H3                     held-out decided N >= MIN_HELDOUT_DECIDED (v2 had 2), the Wilson 95 % lower bound of combined's
                       held-out correct proportion >= H3_WILSON_LOWER_MIN, and not FS_material(combined vs OLD_MIND,
                       base = held-out decided N) on held-out instances.
H4                     SINGLE_INSTANCE_ROBUSTNESS: the conclusion's advantage status is unchanged when any one decided
                       instance is removed, and when any one decided instance's truth is flipped (SUPPORTED <->
                       NOT_SUPPORTED, every arm's outcome recomputed).  Flips of NOT_ASSESSABLE instances are not
                       meaningful (the correct answer is a refusal either way) and are not made.

ADVANTAGE_CORE = C1 and C2 and C3 and C4.

Exactly one conclusion, checked in this order:
1. LEAKAGE_INVALIDATED                  the seal, the post-seal audit or the post-seal mutation suite is not PASS.
2. INCONCLUSIVE                         replay is not exact for every primary arm.
3. TRUTH_INSUFFICIENT                   decided N < MIN_DECIDED, held-out decided N < MIN_HELDOUT_DECIDED, or the
                                        fraction of primary instances unscored by REFERENCE_DISAGREEMENT exceeds
                                        MAX_REFERENCE_DISAGREEMENT.
4. GEN1_REAL_DATA_ADVANTAGE_CONFIRMED   ADVANTAGE_CORE holds and H4 holds;  BENCHMARK_UNDERPOWERED if ADVANTAGE_CORE
                                        holds but some single perturbation breaks it.
5. GEN1_REAL_DATA_ADVANTAGE_PARTIAL     C2 holds and at least one of C1, C3, C4, H1 holds.
6. NO_GEN1_REAL_DATA_ADVANTAGE          otherwise;  BENCHMARK_UNDERPOWERED instead if some single perturbation makes
                                        ADVANTAGE_CORE hold.
No threshold here may change after the seal; there is no amendment mechanism (a post-seal defect invalidates v3).
"""

from __future__ import annotations

import copy
import math
from typing import Any, Mapping, Sequence

from benchmarks.battery_rediscovery_v2.evaluator.score import NON_COMMITTAL, outcome

from . import stats

OLD, REPR, ROLES, COMB, CAREFUL = ("OLD_MIND", "REPRESENTATION_ONLY", "SEMANTIC_ROLES_ONLY", "REPRESENTATION_PLUS_ROLES",
                                   "CAREFUL_BASELINE")
ARMS = (OLD, REPR, ROLES, COMB, CAREFUL)
AXES = ("MODEL_ADEQUACY", "IDENTIFIABILITY", "WITHIN_CELL_GENERALIZATION", "CROSS_CELL_TRANSFER", "MODEL_DISCREPANCY")
DECIDED = ("SUPPORTED", "NOT_SUPPORTED")

MIN_DECIDED = 20
MIN_HELDOUT_DECIDED = 10
MAX_REFERENCE_DISAGREEMENT = 0.25
MIN_FR_REDUCTION = 2
MIN_FR_REDUCTION_FRACTION = 0.10
SIGN_TEST_ALPHA = 0.05
FS_MATERIAL_EXTRA = 2
FS_MATERIAL_RATE = 0.05
H3_WILSON_LOWER_MIN = 0.5
THRESHOLDS = {"MIN_DECIDED": MIN_DECIDED, "MIN_HELDOUT_DECIDED": MIN_HELDOUT_DECIDED,
              "MAX_REFERENCE_DISAGREEMENT": MAX_REFERENCE_DISAGREEMENT, "MIN_FR_REDUCTION": MIN_FR_REDUCTION,
              "MIN_FR_REDUCTION_FRACTION": MIN_FR_REDUCTION_FRACTION, "SIGN_TEST_ALPHA": SIGN_TEST_ALPHA,
              "FS_MATERIAL_EXTRA": FS_MATERIAL_EXTRA, "FS_MATERIAL_RATE": FS_MATERIAL_RATE,
              "H3_WILSON_LOWER_MIN": H3_WILSON_LOWER_MIN, "interval": "Wilson score, 95 %",
              "paired_test": "exact two-sided binomial sign test on discordant pairs"}
VERDICTS = ("GEN1_REAL_DATA_ADVANTAGE_CONFIRMED", "GEN1_REAL_DATA_ADVANTAGE_PARTIAL", "NO_GEN1_REAL_DATA_ADVANTAGE",
            "BENCHMARK_UNDERPOWERED", "TRUTH_INSUFFICIENT", "LEAKAGE_INVALIDATED", "INCONCLUSIVE")
CORRECT = ("CORRECT", "CORRECT_REFUSAL")


def _axis(inst: Mapping[str, Any]) -> str:
    return inst["key"].split("/", 1)[1]


def _oc(inst: Mapping[str, Any], arm: str) -> str:
    return outcome(inst["answers"][arm], inst["truth"])


def _count(insts: Sequence[Mapping[str, Any]], arm: str, kinds: Sequence[str]) -> int:
    return sum(_oc(i, arm) in kinds for i in insts)


def _fs_material(fs_x: int, fs_y: int, base: int) -> bool:
    return fs_x > fs_y and (fs_x - fs_y >= FS_MATERIAL_EXTRA or fs_x > FS_MATERIAL_RATE * base)


def arm_statistics(insts: Sequence[Mapping[str, Any]], arm: str) -> dict[str, Any]:
    decided = [i for i in insts if i["truth"] in DECIDED]
    held = [i for i in decided if i["heldout"]]
    scored = [i for i in insts if i["truth"] is not None]
    cd = _count(decided, arm, CORRECT)
    ch = _count(held, arm, CORRECT)
    by_axis = {}
    for ax in AXES:
        xs = [i for i in scored if _axis(i) == ax]
        by_axis[ax] = {"scored": len(xs), "correct": _count(xs, arm, CORRECT),
                       "decided": sum(i["truth"] in DECIDED for i in xs),
                       "correct_decided": _count([i for i in xs if i["truth"] in DECIDED], arm, CORRECT)}
    return {"decided_n": len(decided), "correct_n": cd,
            "incorrect_n": _count(decided, arm, ("FALSE_SUPPORT", "FALSE_REJECT", "FALSE_REFUSE")),
            "false_support_n": _count(scored, arm, ("FALSE_SUPPORT",)), "false_reject_n": _count(decided, arm, ("FALSE_REJECT",)),
            "false_refuse_n": _count(scored, arm, ("FALSE_REFUSE",)),
            "unsupported_decision_n": _count(scored, arm, ("UNSUPPORTED_DECISION",)),
            "correct_refusal_n": _count(scored, arm, ("CORRECT_REFUSAL",)),
            "unassessable_n": sum(i["truth"] == "NOT_ASSESSABLE" for i in insts),
            "unscored_n": sum(i["truth"] is None for i in insts), "scored_n": len(scored),
            "correct_scored_n": _count(scored, arm, CORRECT),
            "heldout_decided_n": len(held), "heldout_correct_n": ch,
            "correct_decided_wilson95": stats.wilson(cd, len(decided)),
            "heldout_correct_wilson95": stats.wilson(ch, len(held)),
            "by_axis": by_axis}


def _paired(insts: Sequence[Mapping[str, Any]], a: str, b: str) -> dict[str, Any]:
    decided = [i for i in insts if i["truth"] in DECIDED]
    return stats.paired([_oc(i, a) in CORRECT for i in decided], [_oc(i, b) in CORRECT for i in decided])


def criteria(insts: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    st = {a: arm_statistics(insts, a) for a in ARMS}
    c, o = st[COMB], st[OLD]
    n_dec, n_scored, n_ho = c["decided_n"], c["scored_n"], c["heldout_decided_n"]
    pv = _paired(insts, COMB, OLD)
    c1 = pv["win"] > pv["loss"] and pv["p_sign"] <= SIGN_TEST_ALPHA
    c2 = not _fs_material(c["false_support_n"], o["false_support_n"], n_dec)
    decided = [i for i in insts if i["truth"] in DECIDED]
    h2_parts = {}
    for x in (REPR, ROLES):
        fs_c, fs_x = _count(decided, COMB, ("FALSE_SUPPORT",)), _count(decided, x, ("FALSE_SUPPORT",))
        h2_parts[x] = {"correct_decided_combined": c["correct_n"], "correct_decided_arm": st[x]["correct_n"],
                       "fs_decided_combined": fs_c, "fs_decided_arm": fs_x,
                       "holds": c["correct_n"] > st[x]["correct_n"] and not _fs_material(fs_c, fs_x, n_dec)}
    c3 = all(p["holds"] for p in h2_parts.values())
    held = [i for i in decided if i["heldout"]]
    fsh_c, fsh_o = _count(held, COMB, ("FALSE_SUPPORT",)), _count(held, OLD, ("FALSE_SUPPORT",))
    lo = c["heldout_correct_wilson95"][0]
    h3 = (n_ho >= MIN_HELDOUT_DECIDED and lo is not None and lo >= H3_WILSON_LOWER_MIN
          and not _fs_material(fsh_c, fsh_o, n_ho))
    c4 = c["heldout_correct_n"] > o["heldout_correct_n"] and h3
    need = max(MIN_FR_REDUCTION, math.ceil(MIN_FR_REDUCTION_FRACTION * n_scored))
    h1 = c["false_refuse_n"] <= o["false_refuse_n"] - need and c2
    return {"statistics": st,
            "C1_primary_comparison": {"holds": c1, **pv, "alpha": SIGN_TEST_ALPHA},
            "C2_false_support_not_material": {"holds": c2, "FS_combined": c["false_support_n"],
                                              "FS_old": o["false_support_n"], "base_decided_n": n_dec},
            "C3_beats_single_layer_arms": {"holds": c3, "parts": h2_parts},
            "C4_heldout_improvement": {"holds": c4, "heldout_correct_combined": c["heldout_correct_n"],
                                       "heldout_correct_old": o["heldout_correct_n"], "H3": h3},
            "H1": {"holds": h1, "FR_combined": c["false_refuse_n"], "FR_old": o["false_refuse_n"], "required_reduction": need},
            "H2": {"holds": c3}, "H3": {"holds": h3, "heldout_decided_n": n_ho, "wilson_lower": lo,
                                         "FS_heldout_combined": fsh_c, "FS_heldout_old": fsh_o},
            "advantage_core": c1 and c2 and c3 and c4,
            "partial": c2 and (c1 or c3 or c4 or h1)}


def _flip(t: str) -> str:
    return "NOT_SUPPORTED" if t == "SUPPORTED" else "SUPPORTED"


def robustness(insts: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    base = criteria(insts)["advantage_core"]
    breaking, checked = [], 0
    for k, inst in enumerate(insts):
        if inst["truth"] not in DECIDED:
            continue
        removed = [x for j, x in enumerate(insts) if j != k]
        flipped = copy.deepcopy(list(insts))
        flipped[k]["truth"] = _flip(inst["truth"])
        for kind, variant in (("remove", removed), ("flip", flipped)):
            checked += 1
            if criteria(variant)["advantage_core"] != base:
                breaking.append({"perturbation": kind, "instance": inst["key"]})
    return {"advantage_core": base, "robust": not breaking, "perturbations_checked": checked, "breaking": breaking}


def conclude(*, instances: Sequence[Mapping[str, Any]], seal_ok: bool, leakage_ok: bool, replay_exact: bool,
             reference_disagreement_fraction: float) -> dict[str, Any]:
    cr = criteria(instances)
    rb = robustness(instances)
    st = cr["statistics"]
    n_dec, n_ho = st[COMB]["decided_n"], st[COMB]["heldout_decided_n"]
    if not (seal_ok and leakage_ok):
        verdict, why = "LEAKAGE_INVALIDATED", "the seal, the post-seal audit or the post-seal mutation suite is not PASS"
    elif not replay_exact:
        verdict, why = "INCONCLUSIVE", "replay is not exact for every primary arm"
    elif n_dec < MIN_DECIDED or n_ho < MIN_HELDOUT_DECIDED or reference_disagreement_fraction > MAX_REFERENCE_DISAGREEMENT:
        verdict, why = "TRUTH_INSUFFICIENT", (f"decided {n_dec} (min {MIN_DECIDED}), held-out decided {n_ho} (min "
                                              f"{MIN_HELDOUT_DECIDED}), reference disagreement "
                                              f"{reference_disagreement_fraction:.3f} (max {MAX_REFERENCE_DISAGREEMENT})")
    elif cr["advantage_core"]:
        if rb["robust"]:
            verdict, why = "GEN1_REAL_DATA_ADVANTAGE_CONFIRMED", "C1-C4 hold and no single decided instance breaks them"
        else:
            verdict, why = "BENCHMARK_UNDERPOWERED", (f"C1-C4 hold but {len(rb['breaking'])} single-instance "
                                                      f"perturbation(s) break them")
    elif cr["partial"]:
        held = [k for k in ("C1_primary_comparison", "C3_beats_single_layer_arms", "C4_heldout_improvement", "H1")
                if cr[k]["holds"]]
        verdict, why = "GEN1_REAL_DATA_ADVANTAGE_PARTIAL", f"C2 holds and {held} hold; the full advantage does not"
    elif not rb["robust"]:
        verdict, why = "BENCHMARK_UNDERPOWERED", (f"no advantage, but {len(rb['breaking'])} single-instance "
                                                  f"perturbation(s) would establish one")
    else:
        verdict, why = "NO_GEN1_REAL_DATA_ADVANTAGE", "neither the full nor a partial advantage holds"
    assert verdict in VERDICTS
    hyp = {"H1": cr["H1"], "H2": cr["H2"], "H3": cr["H3"], "H4": {"holds": rb["robust"]}}
    return {"verdict": verdict, "why": why, "criteria": {k: v for k, v in cr.items() if k.startswith("C")},
            "hypotheses": hyp, "robustness": rb, "statistics": st,
            "paired": {a: {"vs_OLD_MIND": _paired(instances, a, OLD), "vs_CAREFUL_BASELINE": _paired(instances, a, CAREFUL)}
                       for a in ARMS},
            "gates": {"seal_ok": seal_ok, "leakage_ok": leakage_ok, "replay_exact": replay_exact,
                      "reference_disagreement_fraction": reference_disagreement_fraction},
            "thresholds": THRESHOLDS}


__all__ = ["ARMS", "AXES", "NON_COMMITTAL", "THRESHOLDS", "VERDICTS", "arm_statistics", "conclude", "criteria",
           "robustness"]
