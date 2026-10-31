"""Development scorer for the owner-approved FDA-05 amendment (2026-10-28).

This is NOT a frozen campaign or an independent implementation of v2. It reuses
the v2 interpreter. Exact zero predictions pass zero truths; other zero-truth
predictions fail (no new absolute tolerance). Bracketing alone never recovers
a law. Historical scoring and preregistrations are
unchanged. ``evaluate_campaign`` reconciles with the v0.3 development path
(``benchmarks.genesis_lite.harness_v3``); statistical review, isolation and
preregistration remain prerequisites for any formal v0.3 campaign.
"""

from __future__ import annotations

from typing import Any, Mapping
import math

from . import score as v2

BENCHMARK_ID = "genesis_lite.blindfold_l5.v0_3"
EVALUATOR_SCHEMA = "forge.genesis_lite.independent_evaluator/3"
READINESS = "DEVELOPMENT_ONLY"


def _relative_error(prediction: float, truth: float) -> float:
    if not math.isfinite(prediction) or truth is None or not math.isfinite(truth):
        return math.inf
    if prediction == truth:
        return 0.0
    return abs(prediction - truth) / abs(truth) if truth != 0 else math.inf


def fraction_within(law, truths, tolerance):
    if not math.isfinite(tolerance) or tolerance < 0:
        raise v2.EvaluatorRefused("finite non-negative tolerance required")
    if not truths:
        return 0.0
    return sum(_relative_error(v2.value(law, p), t) <= tolerance for p, t in truths) / len(truths)


def _pair_distance(a: float, b: float) -> float:
    """Owner-approved v3 distance: |a-b|/max(|a|,|b|), zero for two zeros."""
    if not math.isfinite(a) or not math.isfinite(b):
        return math.inf
    scale = max(abs(a), abs(b))
    if scale == 0:
        return 0.0
    difference = abs(a - b)
    return difference / scale if math.isfinite(difference) else abs(a / scale - b / scale)


def _pair_outcome(laws, entry):
    tol, sigma = float(entry["tolerance"]), float(entry["noise_sigma"])
    inbox, truths, box = entry["inbox"], entry["evaluation"], entry["box"]
    a, b = laws
    if not inbox or not truths or not all(math.isfinite(v2.value(law, p))
                                         for law in laws for p, _ in [*inbox, *truths]):
        return "indistinguishable_miss"
    if (any(_pair_distance(v2.value(a, p), v2.value(b, p)) > sigma for p, _ in inbox)
            or any(fraction_within(law, inbox, tol) < v2.PASS_FRACTION for law in laws)):
        return "indistinguishable_miss"
    outside = [(p, t) for p, t in truths if v2._outside(p, box)]
    if not outside or sum(_pair_distance(v2.value(a, p), v2.value(b, p)) > tol
                          for p, _ in outside) / len(outside) < v2.PAIR_DIFFER_FRACTION:
        return "indistinguishable_miss"
    if any(fraction_within(law, truths, tol) >= v2.PASS_FRACTION for law in laws):
        return "indistinguishable_hit"
    bracketed = 0
    for p, t in truths:
        if t is None or not math.isfinite(t):
            continue
        lo, hi = sorted((v2.value(a, p), v2.value(b, p)))
        bracketed += lo - tol * abs(lo) <= t <= hi + tol * abs(hi)
    return ("indistinguishable_unresolved" if bracketed / len(truths) >= v2.PASS_FRACTION
            else "indistinguishable_miss")


def score_universe(proposal: Mapping[str, Any], entry: Mapping[str, Any]) -> dict[str, Any]:
    """Require one accurate law as well as all existing pair eligibility checks.

    A bracketing-only pair is explicitly unresolved, never a recovery. Positive
    recovery credit becomes zero; existing nonpositive penalties are retained.
    Exact matches at zero are accepted without widening any tolerance.
    This function neither authenticates inputs nor proves isolation.
    """
    result = v2.score_universe(proposal, entry)
    tol = float(entry["tolerance"])
    if not math.isfinite(tol) or tol < 0:
        raise v2.EvaluatorRefused("finite non-negative tolerance required")
    if proposal.get("answer") == "law":
        result["fractions"] = [fraction_within(proposal["law"], entry["evaluation"], tol)]
        result["outcome"] = "law_pass" if result["fractions"][0] >= v2.PASS_FRACTION else "law_fail"
    elif proposal.get("answer") == "indistinguishable":
        sigma = float(entry["noise_sigma"])
        if not math.isfinite(sigma) or sigma < 0:
            raise v2.EvaluatorRefused("finite non-negative noise sigma required")
        result["fractions"] = [fraction_within(law, entry["evaluation"], tol) for law in proposal["laws"]]
        result["outcome"] = _pair_outcome(proposal["laws"], entry)
    table = v2.CREDIT.get(result["kind"], {})
    result["credit"] = (min(0.0, table.get("indistinguishable_hit", 0.0))
                        if result["outcome"] == "indistinguishable_unresolved"
                        else float(table.get(result["outcome"], 0.0)))
    return {**result, "benchmark_id": BENCHMARK_ID, "schema": EVALUATOR_SCHEMA,
            "readiness": READINESS}


#: the v0.2 credit table: v0.3 changes the outcome rule, not the credits
CREDIT_DIGEST = v2.CREDIT_DIGEST


def evaluate_campaign(proposals: Mapping[str, Mapping[str, Any]], key: Mapping[str, Any],
                      escrow: Mapping[str, Mapping[str, Any]], *, expected_credit_digest: str) -> dict[str, Any]:
    """The v2 reconciliation contract, scored with this module's rule: VALID only when every kind, outcome, credit and
    fraction agrees with the escrow's v0.3 adjudication. Since escrow_v3 (2026-10-29) the escrow applies the same
    pair/fraction rule text, so agreement independently checks the expression interpreter and the fraction, outcome and
    credit plumbing, not the rule semantics. Any disagreement still fails the run closed."""
    if v2.credit_digest(v2.CREDIT) != expected_credit_digest:
        raise v2.EvaluatorRefused("the evaluator's credit table is not the expected one")
    entries = {e["universe_id"]: e for e in key["universes"]}
    if set(entries) != set(proposals) or set(entries) != set(escrow):
        return {"status": "KEY_MISMATCH", "results": [], "disagreements": [], "benchmark_id": BENCHMARK_ID,
                "detail": "the answer key, the sealed proposals and the escrow adjudications name different universes"}
    results, disagreements = [], []
    for uid in sorted(entries):
        mine = score_universe(proposals[uid], entries[uid])
        theirs = escrow[uid]
        theirs_fr = list(theirs.get("fractions", []))
        agree = (mine["kind"] == theirs["kind"] and mine["outcome"] == theirs["outcome"]
                 and math.isclose(mine["credit"], float(theirs["credit"]), abs_tol=1e-12)
                 and len(theirs_fr) == len(mine["fractions"])
                 and all(math.isclose(a, b, abs_tol=1e-12) for a, b in zip(mine["fractions"], theirs_fr)))
        results.append({**mine, "escrow_outcome": theirs["outcome"], "agree": agree})
        if not agree:
            disagreements.append(uid)
    return {"status": "VALID" if not disagreements else "EVALUATOR_DISAGREEMENT", "results": results,
            "disagreements": disagreements, "schema": EVALUATOR_SCHEMA, "credit_digest": CREDIT_DIGEST,
            "benchmark_id": BENCHMARK_ID, "readiness": READINESS}
