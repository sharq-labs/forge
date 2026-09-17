"""Batch 11 of the 2026-09-16 core re-audit: goodness of fit where the information is (I-04, R-03 and R-20).

The CORE-001 gate asks one question of one number: does the declared noise explain the TOTAL residual, on
n - p degrees of freedom. It never asks which residuals determine the covariance it is guarding.

* **R-03** -- an observation with a large declared sigma adds almost nothing to A'A, so it does not move the
  covariance, but it adds a degree of freedom. Ten precise points whose residuals are 3x their sigma refuse
  MODEL_MISFIT_BEYOND_DECLARED_NOISE alone (chi-square 72 on 8 dof); with 60 over-declared or 1000 honestly
  low-precision points appended they read SUPPORTED with a covariance identical to 4 digits. The same
  function is the grid route's gate.
* **R-20** -- the p >= alpha branch returns BEFORE the variance-ratio refusal, so chi-square/dof of 6.6 at
  1 dof and 4.57 at 2 dof read SUPPORTED with no reason at all, and nothing records that at one or two
  residual degrees of freedom the gate is more likely to miss a factor-4 misfit than to catch it.

Preregistered in `benchmarks/core_v4_false_confidence/BATCH11_THRESHOLD_PROTOCOL.json`. The fifteen
reproductions here were committed as `xfail(strict=True)` at e33e1be3 and run with `--runxfail` to watch
each fail on its own assertion; the markers came off when I-04 was implemented. One test carries no marker
and never did, because it passed at e33e1be3 and must keep passing: a record written before this batch
carries no leverage statistic and is read back under the pooled test alone.
"""

from __future__ import annotations

import json
import math

import numpy as np
import pytest
from scipy.stats import chi2

import false_confidence_cases as F
import hybrid_synthetic as S
from engcore.hybrid_uq import (
    MultistartPolicy,
    RouteClaim,
    RouteReason,
    local_gaussian_posterior,
)
from engcore.hybrid_uq.local_gaussian import GOODNESS_OF_FIT_ALPHA, MISFIT_REFUSE_VARIANCE_RATIO
from engcore.hybrid_uq.vocabulary import HybridUQError

HALF_ALPHA = GOODNESS_OF_FIT_ALPHA / 2.0


def _local(problem, multistart=None):
    return local_gaussian_posterior(problem.calibrate(), problem.observations, problem.forward,
                                    multistart=multistart if multistart is not None else MultistartPolicy())


def _reason(name):
    """A reason member the batch adds, or None -- read by name so a test fails on its own assertion."""
    return getattr(RouteReason, name, None)


def _helper(name):
    """A private helper the batch adds, or None -- read by name so a test fails on its own assertion."""
    from engcore.hybrid_uq import local_gaussian

    return getattr(local_gaussian, name, None)


def _leverage(post):
    """``(statistic, cumulants)`` as the record carries them, or ``(None, None)`` while the batch is open."""
    d = post.diagnostics
    return getattr(d, "leverage_weighted_chi_square", None), getattr(d, "leverage_null_cumulants", None)


# =====================================================================
# R-03: the statistic that looks where the information is
# =====================================================================
@pytest.mark.parametrize("count,factor", [(60, 1.0e6), (1000, 1.0e3)],
                         ids=["60_over_declared", "1000_honest_low_precision"])
def test_r03_padding_that_carries_no_information_does_not_raise_the_claim(count, factor):
    """The audited record: REFUSED alone, SUPPORTED with the padding, and the same covariance to 4 digits."""
    problem = F.gross_misfit_with_ten_precise_points()
    alone = _local(problem)
    assert alone.claim is RouteClaim.REFUSED and RouteReason.MODEL_MISFIT_BEYOND_DECLARED_NOISE in alone.reasons
    after = _local(F.dilute(problem, count=count, sigma_factor=factor))
    assert RouteReason.MODEL_MISFIT_BEYOND_DECLARED_NOISE in after.reasons, (
        f"{count} observations that carry no information turned {alone.claim.value} into {after.claim.value} "
        f"with reasons {[r.value for r in after.reasons]}")


def test_r03_the_leverage_statistic_is_the_one_that_sees_the_diluted_misfit():
    """The pooled test is blind here by construction: the padding adds dof and no chi-square.

    So the two statistics must disagree, and it is the leverage one whose variance ratio names the misfit.
    """
    problem = F.gross_misfit_with_ten_precise_points()
    diluted = F.dilute(problem, count=1000, sigma_factor=1.0e3)
    post = _local(diluted)
    statistic, cumulants = _leverage(post)
    assert statistic is not None and cumulants, "the record carries the statistic the rule used"
    n, p = post.diagnostics.observations, post.diagnostics.parameters
    pooled = float(post.diagnostics.chi_square_minimum) / (n - p)
    assert pooled < 1.0, f"the pooled ratio is diluted to {pooled:.4g}, which is the defect"
    assert float(chi2.sf(post.diagnostics.chi_square_minimum, n - p)) > HALF_ALPHA, "and the pooled p-value says nothing"
    assert statistic / cumulants[0] > MISFIT_REFUSE_VARIANCE_RATIO, (
        f"the leverage ratio is {statistic / cumulants[0]:.4g}; the ten precise points carry the information "
        f"and their residuals are 3x their declared sigma")


def test_the_leverage_test_is_the_pooled_test_when_every_weight_is_equal():
    """The identity that makes the three-moment null checkable: at d = 1 it reduces to chi-square on n - p.

    c1 = c2 = c3 = n - p, so b = 1, dof_eff = n - p and a = 0.
    """
    cumulants_of, p_value_of = _helper("_leverage_null_cumulants"), _helper("_three_moment_p_value")
    assert cumulants_of is not None and p_value_of is not None, "the batch adds the null the statistic is read against"
    basis, _ = np.linalg.qr(np.column_stack([np.ones(9), np.linspace(0.0, 1.0, 9), np.linspace(0.0, 1.0, 9) ** 2]))
    ones = np.ones(9)
    c1, c2, c3 = cumulants_of(ones, basis)
    assert all(abs(c - 6.0) < 1e-9 for c in (c1, c2, c3)), (c1, c2, c3)
    for statistic in (1.0, 6.0, 20.0):
        assert abs(p_value_of(statistic, c1, c2, c3) - float(chi2.sf(statistic, 6))) < 1e-12, statistic

    # at UNEQUAL weights the match is a SHIFTED, scaled chi-square, and the shift is what makes its mean the
    # statistic's mean. Evaluated at the mean c1, the matched variable must sit at its own dof.
    uneven = np.array([1.0, 0.2, 0.05, 3.0, 0.5, 0.01, 2.0, 0.1, 0.4])
    u1, u2, u3 = cumulants_of(uneven, basis)
    assert abs(u1 * u3 - u2 ** 2) > 1e-6 * u2 ** 2, (
        f"the weights must not be effectively equal, or the shift is zero by construction: {(u1, u2, u3)}")
    dof_effective = u2 ** 3 / u3 ** 2
    assert abs(p_value_of(u1, u1, u2, u3) - float(chi2.sf(dof_effective, dof_effective))) < 1e-12, (
        "the three-moment match reproduces the statistic's mean")


def test_the_leverage_weights_are_the_hat_diagonal():
    """Each weight is in [0, 1] and they sum to p: every weight is a share of the information."""
    from engcore.hybrid_uq.sensitivity import reconstruct_local_sensitivity

    weights_of = _helper("_leverage_weights")
    assert weights_of is not None, "the batch adds the weights the statistic is built from"
    problem = F.dilute(F.gross_misfit_with_ten_precise_points(), count=60, sigma_factor=1.0e6)
    sensitivity = reconstruct_local_sensitivity(problem.calibrate(), problem.observations, problem.forward)
    weights, _basis = weights_of(sensitivity.weighted_jacobian)
    assert abs(float(np.sum(weights)) - 2.0) < 1e-9, float(np.sum(weights))
    assert np.all(weights >= -1e-12) and np.all(weights <= 1.0 + 1e-12)
    assert float(np.sum(weights[:10])) > 0.999 * 2.0, (
        "the ten precise points hold essentially all of the information, which is the whole point")
    # and the weights sum to the RANK, not to the column count: a direction the design does not resolve
    # carries no information and must not be given a share of it
    collinear = np.column_stack([np.ones(6), np.ones(6) * 2.0])
    deficient, basis = weights_of(collinear)
    assert abs(float(np.sum(deficient)) - 1.0) < 1e-9, float(np.sum(deficient))
    assert basis.shape == (6, 1), basis.shape


def test_the_record_carries_the_statistic_and_the_cumulants_it_was_judged_on():
    post = _local(S.affine())
    statistic, cumulants = _leverage(post)
    assert isinstance(statistic, float) and math.isfinite(statistic) and statistic >= 0.0, statistic
    assert cumulants is not None and len(tuple(cumulants)) == 3, cumulants
    assert all(isinstance(c, float) and math.isfinite(c) and c > 0.0 for c in cumulants), cumulants
    payload = json.loads(json.dumps(post.to_dict()))
    assert "leverage_weighted_chi_square" in payload["diagnostics"], sorted(payload["diagnostics"])
    assert "leverage_null_cumulants" in payload["diagnostics"], sorted(payload["diagnostics"])


def test_the_read_back_re_derives_the_leverage_verdict():
    """A record cannot state a goodness-of-fit verdict its own leverage numbers do not imply."""
    from engcore.hybrid_uq.local_gaussian import LocalGaussianPosterior

    # a record whose refusal follows from the LEVERAGE half alone: the pooled p-value says nothing here
    diluted = _local(F.dilute(F.gross_misfit_with_ten_precise_points(), count=1000, sigma_factor=1.0e3))
    assert RouteReason.MODEL_MISFIT_BEYOND_DECLARED_NOISE in diluted.reasons, [r.value for r in diluted.reasons]
    payload = json.loads(json.dumps(diluted.to_dict()))
    n, p = payload["diagnostics"]["observations"], payload["diagnostics"]["parameters"]
    assert float(chi2.sf(payload["diagnostics"]["chi_square_minimum"], n - p)) > HALF_ALPHA
    LocalGaussianPosterior.from_dict(json.loads(json.dumps(payload)))  # it reads back as written

    # and lowering the statistic to something the leverage test cannot name refuses it: the record then
    # states a refusal neither of its two numbers implies
    cumulants = payload["diagnostics"].get("leverage_null_cumulants")
    assert cumulants, "the record carries the cumulants the verdict is re-derived against"
    payload["diagnostics"]["leverage_weighted_chi_square"] = 0.5 * float(cumulants[0])
    with pytest.raises(HybridUQError):
        LocalGaussianPosterior.from_dict(payload)


def test_the_read_back_accepts_a_record_with_no_leverage_statistic():
    """A record written before this batch carries neither key and is held to the pooled test alone."""
    from engcore.hybrid_uq.local_gaussian import LocalGaussianPosterior

    post = _local(S.affine())
    payload = json.loads(json.dumps(post.to_dict()))
    payload["diagnostics"].pop("leverage_weighted_chi_square", None)
    payload["diagnostics"].pop("leverage_null_cumulants", None)
    back = LocalGaussianPosterior.from_dict(payload)
    assert back.claim is post.claim


def test_r03_a_supplied_grid_runs_the_same_rule():
    """`grid_goodness_of_fit` is the same function's other caller, so the dilution reaches it too."""
    import inspect

    from engcore.hybrid_uq._grid_evidence import grid_goodness_of_fit

    taken = set(inspect.signature(grid_goodness_of_fit).parameters)
    assert {"calibration", "forward"} <= taken, (
        f"the grid gate needs the evidence to run the same rule; it takes {sorted(taken)}")
    problem = F.dilute(F.gross_misfit_with_ten_precise_points(), count=60, sigma_factor=1.0e6)
    calibration = problem.calibrate()
    estimate = np.asarray(calibration.estimate_vector, dtype=float)
    axes = [np.linspace(v - 0.05, v + 0.05, 9) for v in estimate]
    grid = problem.grid(axes)
    problem_found = grid_goodness_of_fit(grid, problem.observations, calibration=calibration, forward=problem.forward)
    assert problem_found is not None, "a grid over a diluted misfit is not a grid the route may stand behind"
    assert problem_found[0] is RouteReason.MODEL_MISFIT_BEYOND_DECLARED_NOISE, problem_found


# =====================================================================
# R-20: the ratio is unconditional, and a tiny sample says so
# =====================================================================
@pytest.mark.parametrize("chi_square,points", [(6.6, 3), (9.15, 4)], ids=["dof_1", "dof_2"])
def test_r20_a_variance_ratio_above_four_refuses_whatever_the_p_value(chi_square, points):
    """The audited record: p = 0.0102 at dof 1 and 0.0103 at dof 2, so the gate returned before the ratio."""
    dof = points - 2
    assert chi_square / dof > MISFIT_REFUSE_VARIANCE_RATIO, "the case must exceed the ratio the refusal names"
    assert float(chi2.sf(chi_square, dof)) >= HALF_ALPHA, "and its p-value must not reach the test's level"
    post = _local(F.small_dof_variance_ratio(chi_square, points))
    assert RouteReason.MODEL_MISFIT_BEYOND_DECLARED_NOISE in post.reasons, (
        f"chi-square {chi_square} on {dof} degrees of freedom is a scatter "
        f"{math.sqrt(chi_square / dof):.3g}x the declared sigma; the claim is {post.claim.value} with "
        f"{[r.value for r in post.reasons]}")


@pytest.mark.parametrize("points", [3, 4], ids=["dof_1", "dof_2"])
def test_r20_one_or_two_residual_degrees_of_freedom_is_underpowered(points):
    """A fit that agrees with its declared noise is still at most DOWNGRADED at one or two residual dof."""
    underpowered = _reason("GOODNESS_OF_FIT_UNDERPOWERED")
    assert underpowered is not None, "the batch adds the reason that records an untestable noise model"
    post = _local(F.small_dof_variance_ratio(0.5, points))
    assert underpowered in post.diagnostics.downgrades, (
        f"{points - 2} residual degrees of freedom, claim {post.claim.value}, "
        f"reasons {[r.value for r in post.reasons]}")
    assert post.claim is RouteClaim.DOWNGRADED, post.claim


def test_three_residual_degrees_of_freedom_is_not_flagged_underpowered():
    """The declared limit is 2, and this is the guard that it is not silently something else.

    The even-odds criterion in the protocol would reach 4: dof 3 misses a true factor-4 misfit with
    probability 0.608 and dof 4 with 0.554. That the owner's limit leaves them unflagged is a recorded
    residual, and this test is what would fail if the limit moved without the residual being revisited.
    """
    underpowered = _reason("GOODNESS_OF_FIT_UNDERPOWERED")
    assert underpowered is not None, "the batch adds the reason that records an untestable noise model"
    post = _local(F.small_dof_variance_ratio(1.0, 5))
    assert post.diagnostics.observations - post.diagnostics.parameters == 3
    assert underpowered not in post.reasons, [r.value for r in post.reasons]
    assert post.claim is RouteClaim.SUPPORTED, [r.value for r in post.reasons]


def test_each_test_runs_at_half_the_declared_alpha():
    """Two tests on the same residuals at alpha each would double the declared false-refusal rate."""
    from engcore.hybrid_uq.local_gaussian import _goodness_of_fit

    dof, n_p = 10, (12, 2)
    inside = float(chi2.ppf(1.0 - 0.007, dof))          # p = 0.007: below alpha, at or above alpha / 2
    beyond = float(chi2.ppf(1.0 - 0.004, dof))          # p = 0.004: below alpha / 2
    assert inside / dof <= MISFIT_REFUSE_VARIANCE_RATIO and beyond / dof <= MISFIT_REFUSE_VARIANCE_RATIO
    assert _goodness_of_fit(inside, *n_p) == (set(), set()), (
        "a pooled p-value of 0.007 is above alpha / 2, so the pooled half of the rule says nothing")
    assert _goodness_of_fit(beyond, *n_p) == (set(), {RouteReason.RESIDUALS_EXCEED_DECLARED_NOISE})


def test_a_well_fitting_supplied_grid_is_still_used():
    """The two tests run at the node the chi-square MINIMUM comes from, not at the first admissible one.

    A grid's first node is a corner of its box, where the fit is as bad as the box is wide. Reading the
    statistics there would refuse every grid that contains its posterior, which is every grid the route wants.
    """
    from engcore.hybrid_uq._grid_evidence import grid_goodness_of_fit

    problem = S.affine()
    calibration = problem.calibrate()
    grid = problem.grid([np.linspace(0.6, 1.3, 61), np.linspace(1.4, 2.7, 61)])
    assert grid_goodness_of_fit(grid, problem.observations, calibration=calibration,
                                forward=problem.forward) is None


def test_a_supplied_grid_over_one_residual_degree_of_freedom_is_still_used():
    """GOODNESS_OF_FIT_UNDERPOWERED says the noise model was untestable, not that the residuals contradict it.

    A grid claim is SUPPORTED or absent, so it has no way to carry that downgrade -- and passing every small
    grid over instead would refuse on a statement about the test's power rather than about the fit.
    """
    from engcore.hybrid_uq._grid_evidence import grid_goodness_of_fit

    problem = F.small_dof_variance_ratio(0.5, 3)
    calibration = problem.calibrate()
    estimate = np.asarray(calibration.estimate_vector, dtype=float)
    local = _local(problem)
    assert _reason("GOODNESS_OF_FIT_UNDERPOWERED") in local.diagnostics.downgrades, "the local route DOES carry it"
    sd = np.sqrt(np.diag(np.asarray(local.covariance)))
    grid = problem.grid([np.linspace(estimate[i] - 8.0 * sd[i], estimate[i] + 8.0 * sd[i], 41) for i in range(2)])
    assert grid_goodness_of_fit(grid, problem.observations, calibration=calibration,
                                forward=problem.forward) is None


def test_a_grid_whose_best_node_has_no_curvature_is_passed_over():
    """A grid whose fit cannot be tested where the information is cannot be the one the route stands behind."""
    import inspect

    from engcore.hybrid_uq._grid_evidence import grid_goodness_of_fit

    not_measurable = _reason("GOODNESS_OF_FIT_NOT_MEASURABLE")
    assert not_measurable is not None, "the batch adds the refusal for a fit that cannot be tested"
    assert {"calibration", "forward"} <= set(inspect.signature(grid_goodness_of_fit).parameters)

    problem = S.affine()
    calibration = problem.calibrate()
    estimate = np.asarray(calibration.estimate_vector, dtype=float)
    grid = problem.grid([np.linspace(v - 0.05, v + 0.05, 9) for v in estimate])
    base = problem.forward

    def refuses_every_step(theta):
        return base(theta) if np.allclose(np.asarray(theta, dtype=float), estimate) else None

    found = grid_goodness_of_fit(grid, problem.observations, calibration=calibration, forward=refuses_every_step)
    assert found is not None and found[0] is not_measurable, found
