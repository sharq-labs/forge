"""The claim-level verdict rule and the comparison it applies. Pure; no system runs."""

from __future__ import annotations

import itertools

import pytest

from claims_support import band_claim, claim
from engcore.claims import (
    ClaimTarget,
    ClaimVerdict,
    ComparisonOutcome,
    DecisionRule,
    UncertaintyDemand,
    VerdictBasis,
    admissible,
    compare,
    derive_claim_verdict,
)
from engcore.scientific.results.uncertainty import Uncertainty, UncertaintyKind, UncertaintySource
from engcore.scientific.units.quantity import Quantity
from engcore.sria.uncertainty import UncertaintyChannel

K = "kelvin"
NUM = UncertaintyChannel.NUMERICAL
FORM = UncertaintyChannel.MODEL_FORM


def _std(u: float, source: UncertaintySource = UncertaintySource.NUMERICAL) -> Uncertainty:
    return Uncertainty(kind=UncertaintyKind.STANDARD, standard_uncertainty=Quantity(u, K), method="refinement study", source_kind=source)


def _interval(lo: float, hi: float, source: UncertaintySource = UncertaintySource.NUMERICAL) -> Uncertainty:
    return Uncertainty(kind=UncertaintyKind.INTERVAL, lower=Quantity(lo, K), upper=Quantity(hi, K), method="bounds", source_kind=source)


def _demand(*channels, k=2.0):
    return UncertaintyDemand(frozenset(channels), k, False)


BOUND = Quantity(353.15, K)


# ---------------------------------------------------------------------------
# Point comparison
# ---------------------------------------------------------------------------


def test_without_a_demanded_channel_the_comparison_is_a_point_check_and_ignores_known_uncertainty() -> None:
    made = claim()
    satisfied = compare(made, Quantity(350.0, K), BOUND, {NUM: _std(10.0)})
    assert satisfied.rule is DecisionRule.POINT and satisfied.outcome is ComparisonOutcome.SATISFIED
    # Known uncertainty that would straddle the bound is not used, so missing
    # uncertainty can never give a firmer answer than known uncertainty.
    assert compare(made, Quantity(350.0, K), BOUND, {}).outcome is satisfied.outcome
    assert compare(made, Quantity(360.0, K), BOUND, {}).outcome is ComparisonOutcome.VIOLATED


def test_a_strict_bound_fails_at_equality() -> None:
    assert compare(claim(), BOUND, BOUND, {}).outcome is ComparisonOutcome.VIOLATED


def test_an_offset_scale_target_is_compared_as_the_core_compares_it() -> None:
    made = claim(target=ClaimTarget(value=Quantity(80.0, "degree_Celsius")))
    assert compare(made, Quantity(350.0, K), Quantity(80.0, "degree_Celsius"), {}).outcome is ComparisonOutcome.SATISFIED
    assert compare(made, Quantity(354.0, K), Quantity(80.0, "degree_Celsius"), {}).outcome is ComparisonOutcome.VIOLATED


# ---------------------------------------------------------------------------
# Guard band
# ---------------------------------------------------------------------------


def test_a_standard_uncertainty_is_widened_by_the_declared_coverage_factor() -> None:
    made = claim(uncertainty=_demand(NUM, k=2.0))
    ok = compare(made, Quantity(340.0, K), BOUND, {NUM: _std(5.0)})
    assert ok.rule is DecisionRule.GUARD_BAND and ok.outcome is ComparisonOutcome.SATISFIED
    assert ok.band_upper == Quantity(350.0, K)
    straddle = compare(made, Quantity(350.0, K), BOUND, {NUM: _std(5.0)})
    assert straddle.point_satisfied and straddle.outcome is ComparisonOutcome.UNDECIDED
    fail = compare(made, Quantity(370.0, K), BOUND, {NUM: _std(5.0)})
    assert fail.outcome is ComparisonOutcome.VIOLATED


def test_no_coverage_factor_means_no_band_never_a_borrowed_two() -> None:
    made = claim(uncertainty=UncertaintyDemand(frozenset({NUM}), None, False))
    result = compare(made, Quantity(300.0, K), BOUND, {NUM: _std(1.0)})
    assert result.outcome is ComparisonOutcome.NOT_EVALUATED
    assert "coverage factor" in result.channels[0].reason


def test_an_interval_contributes_its_own_bounds_and_must_contain_the_value() -> None:
    made = claim(uncertainty=_demand(NUM))
    assert compare(made, Quantity(340.0, K), BOUND, {NUM: _interval(338.0, 345.0)}).outcome is ComparisonOutcome.SATISFIED
    assert compare(made, Quantity(350.0, K), BOUND, {NUM: _interval(345.0, 356.0)}).outcome is ComparisonOutcome.UNDECIDED
    outside = compare(made, Quantity(340.0, K), BOUND, {NUM: _interval(341.0, 345.0)})
    assert outside.outcome is ComparisonOutcome.NOT_EVALUATED


def test_several_channels_are_summed_linearly_with_no_independence_assumed() -> None:
    made = claim(uncertainty=_demand(NUM, FORM, k=1.0))
    records = {NUM: _std(3.0), FORM: _std(4.0, UncertaintySource.MODEL_FORM)}
    result = compare(made, Quantity(340.0, K), BOUND, records)
    assert result.band_upper == Quantity(347.0, K)  # 3 + 4, not sqrt(9 + 16)


@pytest.mark.parametrize(
    "record, fragment",
    [
        (None, "UNKNOWN"),
        (Uncertainty.unknown("never evaluated"), "UNKNOWN"),
        (_std(1.0, UncertaintySource.COMBINED), "COMBINED"),
        (_std(1.0, UncertaintySource.UNSPECIFIED), "does not attribute"),
        (_std(1.0, UncertaintySource.PARAMETER), "does not attribute"),
    ],
    ids=["absent", "unknown", "combined", "unspecified", "wrong_source"],
)
def test_an_unusable_channel_decides_nothing(record, fragment) -> None:
    made = claim(uncertainty=_demand(NUM))
    result = compare(made, Quantity(300.0, K), BOUND, {} if record is None else {NUM: record})
    assert result.outcome is ComparisonOutcome.NOT_EVALUATED
    assert fragment in result.channels[0].reason


def test_numerical_uncertainty_cannot_stand_for_model_form() -> None:
    made = claim(uncertainty=_demand(FORM))
    result = compare(made, Quantity(300.0, K), BOUND, {FORM: _std(1.0, UncertaintySource.NUMERICAL)})
    assert result.outcome is ComparisonOutcome.NOT_EVALUATED


def test_a_tolerance_band_is_decided_only_when_the_band_is_inside_or_wholly_outside() -> None:
    made = band_claim(uncertainty=_demand(NUM, k=1.0))  # 309.75 +/- 0.5 K
    target = Quantity(309.75, K)
    assert compare(made, Quantity(309.8, K), target, {NUM: _std(0.1)}).outcome is ComparisonOutcome.SATISFIED
    assert compare(made, Quantity(310.1, K), target, {NUM: _std(0.3)}).outcome is ComparisonOutcome.UNDECIDED
    assert compare(made, Quantity(311.0, K), target, {NUM: _std(0.1)}).outcome is ComparisonOutcome.VIOLATED
    # Both ends fail on OPPOSITE sides: the band covers the tolerance band, so nothing is decided.
    wide = compare(made, Quantity(309.75, K), target, {NUM: _std(2.0)})
    assert wide.outcome is ComparisonOutcome.UNDECIDED


# ---------------------------------------------------------------------------
# The verdict
# ---------------------------------------------------------------------------

_FIELDS = dict(
    ready=(True, False),
    executed=(True, False),
    bound=(True, False),
    credibility=("supported", "insufficient_evidence", "not_supported", None),
    assurance=("valid", "inconclusive", "invalid", "not_assessed", None),
    discrepancy_supported=(None, True, False),
    comparison=tuple(ComparisonOutcome) + (None,),
)


def test_support_and_contradiction_require_every_admissibility_condition_exhaustively() -> None:
    for values in itertools.product(*_FIELDS.values()):
        basis = VerdictBasis(**dict(zip(_FIELDS, values)))
        verdict = derive_claim_verdict(basis)
        clean = (
            basis.ready and basis.executed and basis.bound and basis.credibility == "supported"
            and basis.assurance == "valid" and basis.discrepancy_supported is not False
        )
        assert admissible(basis) == clean
        if verdict is ClaimVerdict.SUPPORTED:
            assert clean and basis.comparison is ComparisonOutcome.SATISFIED
        elif verdict is ClaimVerdict.CONTRADICTED:
            assert clean and basis.comparison is ComparisonOutcome.VIOLATED
        else:
            assert not clean or basis.comparison not in (ComparisonOutcome.SATISFIED, ComparisonOutcome.VIOLATED)


def test_a_not_supported_run_is_never_a_contradiction() -> None:
    for comparison in ComparisonOutcome:
        basis = VerdictBasis(True, True, True, "not_supported", "valid", None, comparison)
        assert derive_claim_verdict(basis) is ClaimVerdict.INSUFFICIENT_EVIDENCE
