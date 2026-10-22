"""The preregistered hypotheses and the single conclusion of battery_rediscovery_v2 (frozen in PLAN.json).

Counts are over scored instances (one per problem and axis); FR = FALSE_REFUSE, FS = FALSE_SUPPORT.

H1  REPRESENTATION_PLUS_ROLES reduces false refusal relative to OLD_MIND without increasing false support:
    FR(combined) <= FR(old) - MIN_FR_REDUCTION  and  FS(combined) <= FS(old).
H2  The combined arm outperforms each single-layer arm on the scientifically assessable (decided-truth) instances:
    for X in (REPRESENTATION_ONLY, SEMANTIC_ROLES_ONLY): correct_decided(combined) > correct_decided(X)
    and FS_decided(combined) <= FS_decided(X).
H3  The combined arm moves toward CAREFUL_BASELINE on held-out real data: on the held-out instances,
    gap(arm) = correct(CAREFUL) - correct(arm);  gap(combined) < gap(old)  and  FS_heldout(combined) <= FS_heldout(old).

Exactly one conclusion, checked in this order:
1. LEAKAGE_INVALIDATED                if the seal or the post-seal leakage audit is not PASS.
2. INCONCLUSIVE                       if replay is not exact for every arm, or fewer than MIN_DECIDED instances have a
                                      decided truth (too few assessable real-data questions to test H2/H3).
3. REAL_DATA_IMPROVEMENT_CONFIRMED    if H1, H2 and H3 all hold.
4. PARTIAL_REAL_DATA_IMPROVEMENT      if FS(combined) <= FS(old) and at least one of H1, H2, H3 holds.
5. Otherwise the combined arm's scored failures (FALSE_REFUSE, FALSE_SUPPORT, FALSE_REJECT, UNSUPPORTED_DECISION) are
   attributed by its own recorded refusal: REPRESENTATION_UNAVAILABLE with a role-binding condition -> ROLES; any other
   REPRESENTATION_UNAVAILABLE -> REPRESENTATION; everything else (evidence, domain, wrong decisions) -> OTHER.
   REPRESENTATION_STILL_LIMITING      if REPRESENTATION is at least half of the failures;
   SEMANTIC_ROLES_STILL_LIMITING      else if ROLES is at least half of the failures;
   NO_REAL_DATA_IMPROVEMENT           otherwise.
No threshold here may change after the seal; there is no amendment mechanism (a post-seal defect invalidates v2).
"""

from __future__ import annotations

from typing import Any, Mapping

MIN_FR_REDUCTION = 2
MIN_DECIDED = 4
OLD, REPR, ROLES, COMB, CAREFUL = ("OLD_MIND", "REPRESENTATION_ONLY", "SEMANTIC_ROLES_ONLY", "REPRESENTATION_PLUS_ROLES",
                                   "CAREFUL_BASELINE")
ROLE_CONDITION_KEYS = ("slot", "candidates", "legacy_roles", "measurements", "undeclared_parameters",
                       "applicability_variable", "not_declared_latent_parameters_of_family")
VERDICTS = ("REAL_DATA_IMPROVEMENT_CONFIRMED", "PARTIAL_REAL_DATA_IMPROVEMENT", "NO_REAL_DATA_IMPROVEMENT",
            "REPRESENTATION_STILL_LIMITING", "SEMANTIC_ROLES_STILL_LIMITING", "LEAKAGE_INVALIDATED", "INCONCLUSIVE")
THRESHOLDS = {"MIN_FR_REDUCTION": MIN_FR_REDUCTION, "MIN_DECIDED": MIN_DECIDED,
              "false_support_materiality": "any increase of FALSE_SUPPORT over OLD_MIND is material"}


def _c(s: Mapping[str, Any], block: str, key: str) -> int:
    return s[block]["counts"][key] if key in s[block]["counts"] else s[block][key]


def hypotheses(scores: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    old, comb = scores[OLD], scores[COMB]
    fr_o, fr_c = _c(old, "all", "FALSE_REFUSE"), _c(comb, "all", "FALSE_REFUSE")
    fs_o, fs_c = _c(old, "all", "FALSE_SUPPORT"), _c(comb, "all", "FALSE_SUPPORT")
    h1 = fr_c <= fr_o - MIN_FR_REDUCTION and fs_c <= fs_o
    h2_parts = {}
    for x in (REPR, ROLES):
        h2_parts[x] = {"correct_decided_combined": comb["decided"]["correct"], "correct_decided_arm": scores[x]["decided"]["correct"],
                       "fs_decided_combined": _c(comb, "decided", "FALSE_SUPPORT"),
                       "fs_decided_arm": _c(scores[x], "decided", "FALSE_SUPPORT")}
        p = h2_parts[x]
        p["holds"] = p["correct_decided_combined"] > p["correct_decided_arm"] and p["fs_decided_combined"] <= p["fs_decided_arm"]
    h2 = all(p["holds"] for p in h2_parts.values())
    gap_o = scores[CAREFUL]["heldout"]["correct"] - old["heldout"]["correct"]
    gap_c = scores[CAREFUL]["heldout"]["correct"] - comb["heldout"]["correct"]
    fsh_o, fsh_c = _c(old, "heldout", "FALSE_SUPPORT"), _c(comb, "heldout", "FALSE_SUPPORT")
    h3 = gap_c < gap_o and fsh_c <= fsh_o
    return {"H1": {"holds": h1, "FR_old": fr_o, "FR_combined": fr_c, "FS_old": fs_o, "FS_combined": fs_c,
                   "min_reduction": MIN_FR_REDUCTION},
            "H2": {"holds": h2, "parts": h2_parts},
            "H3": {"holds": h3, "heldout_correct": {a: scores[a]["heldout"]["correct"] for a in (OLD, COMB, CAREFUL)},
                   "heldout_scored": {a: scores[a]["heldout"]["scored"] for a in (OLD, COMB, CAREFUL)},
                   "gap_old": gap_o, "gap_combined": gap_c, "FS_heldout_old": fsh_o, "FS_heldout_combined": fsh_c}}


def attribute(rows: list[Mapping[str, Any]], claims: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """The combined arm's failures, by its own recorded refusal.  ``claims``: problem -> axis -> repsem claim dict."""
    out = {"REPRESENTATION": [], "ROLES": [], "OTHER": []}
    for r in rows:
        if r["outcome"] not in ("FALSE_REFUSE", "FALSE_SUPPORT", "FALSE_REJECT", "UNSUPPORTED_DECISION"):
            continue
        claim = claims[r["problem"]][r["axis"]]
        ref = claim.get("refusal") or {}
        key = f"{r['problem']}/{r['axis']}:{r['outcome']}"
        if ref.get("reason") == "REPRESENTATION_UNAVAILABLE":
            cond = ref.get("condition") or {}
            (out["ROLES"] if any(k in cond for k in ROLE_CONDITION_KEYS) else out["REPRESENTATION"]).append(key)
        else:
            out["OTHER"].append(key)
    return out


def conclude(*, seal_ok: bool, leakage_ok: bool, replay_exact: bool, scores: Mapping[str, Mapping[str, Any]],
             combined_claims: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    n_decided = scores[COMB]["decided"]["scored"]
    hyp = hypotheses(scores)
    attr = attribute(scores[COMB]["rows"], combined_claims)
    n_fail = sum(len(v) for v in attr.values())
    if not (seal_ok and leakage_ok):
        verdict, why = "LEAKAGE_INVALIDATED", "the seal or the post-seal leakage audit is not PASS"
    elif not replay_exact:
        verdict, why = "INCONCLUSIVE", "replay is not exact for every arm"
    elif n_decided < MIN_DECIDED:
        verdict, why = "INCONCLUSIVE", f"only {n_decided} decided-truth instances (< {MIN_DECIDED})"
    elif hyp["H1"]["holds"] and hyp["H2"]["holds"] and hyp["H3"]["holds"]:
        verdict, why = "REAL_DATA_IMPROVEMENT_CONFIRMED", "H1, H2 and H3 hold"
    elif hyp["H1"]["FS_combined"] <= hyp["H1"]["FS_old"] and any(hyp[h]["holds"] for h in ("H1", "H2", "H3")):
        held = [h for h in ("H1", "H2", "H3") if hyp[h]["holds"]]
        verdict, why = "PARTIAL_REAL_DATA_IMPROVEMENT", f"{held} hold, the others do not; false support not increased"
    elif n_fail and 2 * len(attr["REPRESENTATION"]) >= n_fail:
        verdict, why = "REPRESENTATION_STILL_LIMITING", f"{len(attr['REPRESENTATION'])}/{n_fail} combined failures are representation refusals"
    elif n_fail and 2 * len(attr["ROLES"]) >= n_fail:
        verdict, why = "SEMANTIC_ROLES_STILL_LIMITING", f"{len(attr['ROLES'])}/{n_fail} combined failures are role-binding refusals"
    else:
        verdict, why = "NO_REAL_DATA_IMPROVEMENT", "no hypothesis holds and the failures are not mainly representation or roles"
    assert verdict in VERDICTS
    return {"verdict": verdict, "why": why, "hypotheses": hyp, "combined_failure_attribution": attr,
            "decided_instances": n_decided, "thresholds": THRESHOLDS}


__all__ = ["THRESHOLDS", "VERDICTS", "attribute", "conclude", "hypotheses"]
