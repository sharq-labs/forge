"""Core re-audit 2026-09-16, batch 31: bound domination is diagnosed one side at a time.

Problem R-11 (benchmarks/core_v4_false_confidence/REAUDIT_2026-09-16.json), improvement I-06, under
benchmarks/core_v4_false_confidence/BATCH31_THRESHOLD_PROTOCOL.json. R-11 is also the last open case of
I-15's conformance suite, so I-15 closes with this one.

Recorded as strict xfails in commit <XFAIL-SHA>, each seen failing on its own assertion, before the fix.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

import false_confidence_cases as F
from engcore.hybrid_uq import (
    GridRebuildPolicy,
    MultistartPolicy,
    RouteClaim,
    RouteReason,
    route_uncertainty,
)
from engcore.hybrid_uq import router as router_module


def _rebuilt(problem, **kw):
    return route_uncertainty(
        calibration=problem.calibrate(),
        observations=problem.observations,
        forward=problem.forward,
        rebuild=GridRebuildPolicy(problem.table_builder()),
        multistart=MultistartPolicy(),
        **kw,
    )


def _reasons(result):
    return {reason for reason in getattr(result, "reasons", ())}


# ---------------------------------------------------------------------------
# domination_is_diagnosed_one_side_at_a_time
# ---------------------------------------------------------------------------
@pytest.mark.xfail(strict=True, reason="R-11: there is no per-side distance yet")
def test_r11_the_band_distance_is_derived_from_the_band_and_not_chosen():
    """A Gaussian of sd s is exactly `EDGE_LOG_LIKELIHOOD_DROP` below its peak at sqrt(2 ln 1e6) sd."""
    assert hasattr(router_module, "_GAUSSIAN_BAND_SD"), (
        "engcore.hybrid_uq.router has no _GAUSSIAN_BAND_SD; the rule "
        "'domination_is_diagnosed_one_side_at_a_time' in BATCH31_THRESHOLD_PROTOCOL.json needs it"
    )
    assert router_module._GAUSSIAN_BAND_SD == math.sqrt(
        2.0 * router_module.EDGE_LOG_LIKELIHOOD_DROP
    ), "the distance must be derived from the band it is about, so it cannot drift from it"
    assert router_module._GAUSSIAN_BAND_SD == pytest.approx(5.256521769756932)


@pytest.mark.xfail(strict=True, reason="R-11: one reached declared bound goes to the halving loop")
@pytest.mark.parametrize("bound", (40.0, 60.0, 80.0))
def test_r11_a_posterior_running_to_one_declared_bound_is_passed_over(bound):
    """The audited case: the data rule out every small rate and say nothing about a large one."""
    result = _rebuilt(F.decay_with_upper_bound(bound))
    assert result.claim is not RouteClaim.SUPPORTED, (
        f"with the declared upper bound at {bound:g} the rebuild is {result.claim.value}, and the width it "
        f"reports is the bound's: {np.sqrt(np.asarray(result.covariance, dtype=float)[0][0]):.4g}"
    )
    assert RouteReason.GRID_POSTERIOR_BOUND_DOMINATED in _reasons(result), (
        f"the finding must be named as bound domination, not as an unresolved rebuild; got "
        f"{sorted(r.value for r in _reasons(result))}"
    )


# ---------------------------------------------------------------------------
# the_refusal_names_the_side
# ---------------------------------------------------------------------------
@pytest.mark.xfail(strict=True, reason="R-11: the both-sides rule never names a side")
def test_r11_the_refusal_names_the_parameter_and_which_side_it_ran_to():
    result = _rebuilt(F.decay_with_upper_bound(60.0))
    detail = " ".join(str(value) for value in getattr(result, "details", ()) or ()) + " " + str(result)
    assert "high" in detail, (
        f"the refusal must say WHICH side ran to its bound -- both sides dominated means the declared range "
        f"is too narrow, one side means the data constrain only one direction, and the remedies differ. "
        f"Detail: {detail!r}"
    )


# ---------------------------------------------------------------------------
# a_peak_at_the_bound_still_gets_truncation_refinement
# ---------------------------------------------------------------------------
def test_r11_a_posterior_that_decays_toward_its_bound_still_takes_the_refinement_path():
    """The half that must NOT change: a peak at or near a declared bound decays toward it.

    The distance from such a peak to that bound is about zero, nowhere near the band distance, so the
    per-side rule does not fire and the halving loop runs exactly as it did.
    """
    result = _rebuilt(F.decay_with_upper_bound(13.0))
    assert RouteReason.GRID_POSTERIOR_BOUND_DOMINATED not in _reasons(result), (
        f"a posterior that decays toward its bound is a truncation to refine, not a domination to refuse; "
        f"got {sorted(r.value for r in _reasons(result))}"
    )


# ---------------------------------------------------------------------------
# a_cumulant_that_cannot_be_negative_is_not_computed_negative (I-14, landed early)
# ---------------------------------------------------------------------------
@pytest.mark.xfail(strict=True, reason="the leverage null carries -eps and the self-check refuses it")
def test_r11_the_fixture_is_routable_at_all():
    """The blocker. At the baseline this raises for EVERY declared bound, so I-06 cannot be exercised.

    `a leverage test needs a non-negative statistic and a non-negative null; this record carries
    0.08936059297804337 against (2.8713019073478563e-07, 8.260059303211165e-14, -2.220446049250313e-16)`.
    The third cumulant is exactly -eps: a zero computed with rounding.
    """
    for bound in (13.0, 40.0, 60.0, 80.0):
        _rebuilt(F.decay_with_upper_bound(bound))


def test_r11_a_cumulant_that_cannot_be_negative_is_not_computed_negative():
    """c_k = trace(M^k) for a PSD M, so all three are non-negative as arithmetic, not as modelling."""
    from engcore.hybrid_uq.local_gaussian import _leverage_null_cumulants, _leverage_weights

    # One observation holding all the leverage: I - H annihilates it, so the null is structurally zero and
    # the closed form reaches that zero by cancellation. This is the shape the self-check refused.
    jacobian = np.array([[1.0], [0.0], [0.0]])
    weights, basis = _leverage_weights(jacobian)
    cumulants = _leverage_null_cumulants(weights, basis)
    assert all(c >= 0.0 for c in cumulants), (
        f"a trace of a power of a positive-semidefinite matrix came out negative: {cumulants}"
    )


@pytest.mark.xfail(strict=True, reason="there is no clamp, so there is no floor either")
def test_r11_a_cumulant_far_below_the_round_off_floor_is_refused_and_not_clamped():
    """The clamp must not become a way to accept a real coding error."""
    from engcore.hybrid_uq.local_gaussian import _clamp_leverage_cumulant
    from engcore.hybrid_uq.vocabulary import HybridUQError

    assert _clamp_leverage_cumulant(-1.0e-16, scale=1.0, terms=3, name="c3") == 0.0
    assert _clamp_leverage_cumulant(2.5, scale=1.0, terms=3, name="c3") == 2.5
    with pytest.raises(HybridUQError, match="round-off"):
        _clamp_leverage_cumulant(-0.5, scale=1.0, terms=3, name="c3")


def test_r11_an_equal_weight_null_still_reduces_to_the_pooled_test_exactly():
    """The control, and it is the identity the cumulants' own docstring says makes the null checkable.

    At d = 1 for every observation all three cumulants are n - rank, which is what makes the three-moment
    match reduce to the pooled chi-square test. A clamp must not move that.
    """
    from engcore.hybrid_uq.local_gaussian import _leverage_null_cumulants

    n, rank = 7, 2
    basis = np.zeros((n, rank))
    basis[0, 0] = basis[1, 1] = 1.0
    weights = np.ones(n)
    assert _leverage_null_cumulants(weights, basis) == pytest.approx((n - rank,) * 3)
