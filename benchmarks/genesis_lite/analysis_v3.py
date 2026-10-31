"""Conservative paired inference for development of Genesis-lite v0.3.

Hoeffding (1963), Theorem 2: https://doi.org/10.1080/01621459.1963.10500830
Independent physical units are equally weighted. Repeated seeds/presentations
within each unit are averaged BEFORE inference; their dependence is unrestricted.
Scores are bounded a priori by the six-kind credit table (-6 to +6); differences
therefore lie in [-12,12]. No estimated variance or bootstrap tail is a p-value.
All frozen baselines are tested with Holm, never just a post-selected winner.

This module cannot authenticate independence, preregistration or data custody.
It reports conditional statistical results, never formal scientific lift.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
import statistics
from typing import Mapping, Sequence

SCHEMA = "forge.genesis_lite.paired_analysis/3"
SCORE_BOUND = 6.0


def lift_decision(records, candidate, *, grid=None):
    """Compatibility diagnostic: frozen v0.2 results cannot authorize v0.3 lift.

    Kept outside the hash-pinned historical module so old replay still works.
    The new statistical entry point is compare_paired_scores, with explicit
    independent-unit and repeated-setting identities.
    """
    from .analysis import lift_decision as historical_decision
    report = historical_decision(records, candidate, grid=grid)
    report["historical_rule_would_claim"] = report["lift_claimed"]
    report["historical_holm_significant"] = report.pop("holm_significant")
    report["holm_significant"] = {key: False for key in report["historical_holm_significant"]}
    report["lift_claimed"] = False
    report["schema"] = SCHEMA
    report["statistical_status"] = "UNQUALIFIED_LEGACY_BOOTSTRAP_TAIL"
    return report


def bounded_paired_test(differences: Sequence[float], *, alpha: float = .05) -> dict:
    """Test H0: mean paired score difference <= 0 for independent units.

    An upper bound on the one-sided tail is a conservative p-value. The
    one-sided lower confidence bound is separate from significance.
    """
    values = tuple(float(x) for x in differences)
    if not values or any(not math.isfinite(x) or abs(x) > 2 * SCORE_BOUND for x in values):
        raise ValueError("non-empty finite paired differences in [-12,12] required")
    if not math.isfinite(alpha) or not 0 < alpha < 1:
        raise ValueError("alpha must be finite and strictly between zero and one")
    n, mean, width = len(values), statistics.fmean(values), 4 * SCORE_BOUND
    log_p = -2 * n * max(mean, 0.0) ** 2 / width ** 2
    # Do not report an exact zero probability due to floating-point underflow.
    p = max(math.nextafter(0.0, 1.0), math.exp(log_p))
    lower = max(-2 * SCORE_BOUND, mean - width * math.sqrt(math.log(1 / alpha) / (2 * n)))
    return {"independent_units": n, "mean_difference": mean, "p_value_upper_bound": p,
            "lower_confidence_bound": lower, "one_sided_alpha": alpha,
            "method": "hoeffding_bounded_independent_unit_means"}


@dataclass(frozen=True)
class PairedComparisonPlan:
    candidate: str
    baselines: tuple[str, ...]
    unit_ids: tuple[str, ...]
    replicate_ids: tuple[str, ...]
    alpha: float = .05

    def __post_init__(self):
        if type(self.candidate) is not str or not self.candidate.strip():
            raise ValueError("candidate identity required")
        for field in ("baselines", "unit_ids", "replicate_ids"):
            values = tuple(getattr(self, field))
            if (not values or any(type(x) is not str or not x.strip() for x in values)
                    or len(set(values)) != len(values)):
                raise ValueError(f"{field} must be non-empty unique string identities")
            object.__setattr__(self, field, tuple(sorted(values)))
        if self.candidate in self.baselines:
            raise ValueError("candidate cannot be a baseline")
        if not math.isfinite(self.alpha) or not 0 < self.alpha < 1:
            raise ValueError("alpha must lie strictly between zero and one")

    @property
    def fingerprint(self):
        return hashlib.sha256(json.dumps({"schema": SCHEMA, **asdict(self)},
            sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def compare_paired_scores(plan: PairedComparisonPlan,
                         scores: Mapping[str, Mapping[str, Mapping[str, float]]]) -> dict:
    """Compare every predeclared baseline on the complete paired grid.

    Input shape: arm -> independent physical unit -> repeated setting -> score.
    Missing arms/units/settings, extra records and nonfinite scores refuse; no
    outcome-dependent row dropping or comparator selection is allowed here.
    """
    if not isinstance(plan, PairedComparisonPlan):
        raise ValueError("typed frozen comparison plan required")
    if set(scores) != {plan.candidate, *plan.baselines}:
        raise ValueError("scores do not match the complete frozen arm set")
    means = {}
    for arm, units in scores.items():
        if set(units) != set(plan.unit_ids):
            raise ValueError("missing or extra independent units")
        means[arm] = {}
        for unit, repeats in units.items():
            if set(repeats) != set(plan.replicate_ids):
                raise ValueError("missing or extra repeated settings")
            values = tuple(float(repeats[r]) for r in plan.replicate_ids)
            if any(not math.isfinite(v) or abs(v) > SCORE_BOUND for v in values):
                raise ValueError("finite six-kind total scores in [-6,6] required")
            means[arm][unit] = statistics.fmean(values)
    tests = {arm: bounded_paired_test(
        [means[plan.candidate][u] - means[arm][u] for u in plan.unit_ids],
        alpha=plan.alpha / len(plan.baselines)) for arm in plan.baselines}
    order = sorted(tests, key=lambda arm: tests[arm]["p_value_upper_bound"])
    still = True
    for i, arm in enumerate(order):
        still = still and tests[arm]["p_value_upper_bound"] <= plan.alpha / (len(order) - i)
        tests[arm]["holm_reject_null"] = still
    return {"schema": SCHEMA, "plan_digest": plan.fingerprint, "tests": tests,
            "statistical_superiority_to_all_baselines": all(t["holm_reject_null"] for t in tests.values()),
            "simultaneous_confidence": 1 - plan.alpha,
            "lift_claimed": False, "readiness": "DEVELOPMENT_ONLY",
            "limitations": ["independent units and frozen plan require external provenance",
                            "formal campaign qualification, per-kind noninferiority and independent evaluation remain separate"]}
