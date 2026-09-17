"""Core re-audit 2026-09-16, batch 31: bound domination is diagnosed one side at a time.

Problem R-11 (benchmarks/core_v4_false_confidence/REAUDIT_2026-09-16.json), improvement I-06, under
benchmarks/core_v4_false_confidence/BATCH31_THRESHOLD_PROTOCOL.json. R-11 is also the last open case of
I-15's conformance suite, so I-15 closes with this one.

Recorded as strict xfails in commit 28e4c116, each seen failing on its own assertion, before the fix.
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


def _rebuild_entry(result):
    """The rebuild route's own row of `considered`, which is where its reason and detail live."""
    rows = [row for row in result.considered if str(row.get("route", "")).startswith("GRID_REBUILT")]
    assert rows, f"no rebuild route was considered at all: {result.considered}"
    return rows[0]


def _reasons(result):
    entry = _rebuild_entry(result)
    return {RouteReason(name) for name in str(entry.get("reason", "")).split(",") if name}


def _sd(result, index=0):
    return float(np.sqrt(np.asarray(result.covariance, dtype=float)[index][index]))


# ---------------------------------------------------------------------------
# domination_is_diagnosed_one_side_at_a_time
# ---------------------------------------------------------------------------
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


@pytest.mark.parametrize("bound", (40.0, 60.0, 80.0))
def test_r11_a_posterior_running_to_one_declared_bound_is_passed_over(bound):
    """The audited signature: the data rule out every small rate and say nothing about a large one.

    At the baseline this is SUPPORTED with a rate sd of 2.372, 2.788 and 3.522 for a declared upper bound of
    40, 60 and 80 -- a factor of 1.485 across the range, for one set of data.
    """
    result = _rebuilt(F.one_sided_declared_bound(bound))
    assert result.claim is not RouteClaim.SUPPORTED, (
        f"with the declared upper bound at {bound:g} the rebuild is {result.claim.value} and the width it "
        f"reports is the bound's: {_sd(result):.4g}"
    )
    assert RouteReason.GRID_POSTERIOR_BOUND_DOMINATED in _reasons(result), (
        f"the finding must be named as bound domination, not as an unresolved rebuild; got "
        f"{sorted(r.value for r in _reasons(result))}"
    )


def test_r11_a_contained_posterior_is_still_supported_and_its_width_is_the_data_s():
    """The control, and the discriminator: at a rate of 8 the posterior is contained on both sides.

    Its sd is 1.201 at every one of the three declared bounds -- the data's width, not the bound's -- so the
    rule must leave it alone. Without this the refusal above could be a blanket one.
    """
    widths = {}
    for bound in (40.0, 60.0, 80.0):
        result = _rebuilt(F.one_sided_declared_bound(bound, rate=8.0))
        assert result.claim is RouteClaim.SUPPORTED, (
            f"a posterior the data bound on both sides is {result.claim.value} at bound {bound:g}: "
            f"{sorted(r.value for r in _reasons(result))}"
        )
        widths[bound] = _sd(result)
    spread = max(widths.values()) / min(widths.values())
    assert spread == pytest.approx(1.0, abs=1e-9), (
        f"a SUPPORTED width moved by a factor {spread:.6g} when only the declared bound moved: {widths}"
    )


# ---------------------------------------------------------------------------
# the_refusal_names_the_side
# ---------------------------------------------------------------------------
def test_r11_the_refusal_names_the_parameter_and_which_side_it_ran_to():
    result = _rebuilt(F.one_sided_declared_bound(60.0))
    detail = str(_rebuild_entry(result).get("detail", ""))
    # The leading SENTENCE, not merely the word somewhere in the line: the detail also ends with a
    # `dominated side(s)` list, so `"high" in detail` passes even when the sentence stops naming a side.
    # Found by mutation B31f, which survived that weaker assertion.
    assert "the high declared bound of 'theta1'" in detail, (
        f"the refusal must say WHICH side ran to its bound -- both sides dominated means the declared range "
        f"is too narrow, one side means the data constrain only one direction, and the remedies differ. "
        f"Detail: {detail!r}"
    )


# ---------------------------------------------------------------------------
# a_peak_at_the_bound_still_gets_truncation_refinement
# ---------------------------------------------------------------------------
def test_r11_a_truncated_posterior_that_decays_toward_its_bound_still_takes_the_refinement_path():
    """The half that must NOT change, and it has to be a case that really is TRUNCATED.

    Repointed while running this batch's mutations: the first version used the contained case, where no
    face reaches its bound at all, so the per-side branch is never entered and mutations B31d and B31e --
    which corrupt the distance INSIDE that branch -- both survived. At a declared bound of 14 the posterior
    does reach it, the route halves the steps twice and reports SUPPORTED, which is the halving loop the
    audit says to keep: 'keep truncation refinement for posteriors that actually decay toward the bound'.
    """
    result = _rebuilt(F.one_sided_declared_bound(14.0))
    assert RouteReason.GRID_POSTERIOR_BOUND_DOMINATED not in _reasons(result), (
        f"a posterior that decays toward its bound is a truncation to refine, not a domination to refuse; "
        f"got {sorted(r.value for r in _reasons(result))}"
    )
    assert result.claim is RouteClaim.SUPPORTED, result.claim.value
    detail = str(_rebuild_entry(result).get("detail", ""))
    assert "truncation halving(s) on axes [0]" in detail, (
        f"the case must reach the halving loop, or it says nothing about the half being guarded: {detail!r}"
    )


# ---------------------------------------------------------------------------
# a_cumulant_that_cannot_be_negative_is_not_computed_negative (I-14, landed early)
# ---------------------------------------------------------------------------
def test_r11_the_fixture_is_routable_at_all():
    """The blocker. At the baseline this raises for EVERY declared bound, so I-06 cannot be exercised.

    `a leverage test needs a non-negative statistic and a non-negative null; this record carries
    0.08936059297804337 against (2.8713019073478563e-07, 8.260059303211165e-14, -2.220446049250313e-16)`.
    The third cumulant is exactly -eps: a zero computed with rounding.
    """
    for bound in (13.0, 40.0, 60.0, 80.0):
        _rebuilt(F.decay_with_upper_bound(bound))
    for bound in (40.0, 60.0, 80.0):
        _rebuilt(F.one_sided_declared_bound(bound))


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
