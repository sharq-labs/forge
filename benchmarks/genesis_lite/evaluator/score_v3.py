"""Development scorer for the owner-approved FDA-05 amendment (2026-10-28).

This is NOT a frozen campaign or an independent implementation of v2. It reuses
the v2 interpreter. Exact zero predictions pass zero truths; other zero-truth
predictions fail (no new absolute tolerance). Bracketing alone never recovers
a law. Historical scoring and preregistrations are
unchanged. No campaign evaluator is exposed: escrow reconciliation, statistical
review, isolation and preregistration are prerequisites for a v0.3 campaign.
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
