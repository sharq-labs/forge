"""Audit stream "hybrid": the local Gaussian route's own validity checks, attacked (HUQ-01, HUQ-08, HUQ-10).

HUQ-01  a caller could switch the multistart off by asking for one start (or a degenerate span) and still get
        SUPPORTED, with the policy that was actually used recorded nowhere;
HUQ-08  the chi-square probes looked along principal axes only, so a saddle whose descent lies between them
        passed, and a converged refit with a LOWER objective inside the separation radius was SAME_OPTIMUM;
HUQ-10  when every probe was skipped the nonlinearity index stayed at its initial 0.0 and the route emitted a
        DOWNGRADED covariance nobody had checked against the model.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

import hybrid_synthetic as S
from engcore.hybrid_uq import (
    MultistartPolicy,
    RouteClaim,
    RouteDecision,
    RouteReason,
    local_gaussian_posterior,
    route_uncertainty,
)


def _mirror():
    P = S.mirror_mode()
    return P, P.calibrate()


# ---------------------------------------------------------------------------
# HUQ-01: the multistart is a minimum search, not a caller's option
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("policy", [
    MultistartPolicy(starts=1),
    MultistartPolicy(starts=1, interior_fraction=0.01),
    MultistartPolicy(starts=5),
    MultistartPolicy(interior_fraction=0.05),
    MultistartPolicy(mode_separation_quantile=0.999999),
    MultistartPolicy(comparable_fit_quantile=0.01),
], ids=["one_start", "one_start_degenerate_span", "five_starts", "narrow_span", "wide_separation", "narrow_comparable"])
def test_huq01_a_weakened_multistart_can_never_support_the_route(policy):
    P, calibration = _mirror()
    post = local_gaussian_posterior(calibration, P.observations, P.forward, multistart=policy)
    assert post.claim is not RouteClaim.SUPPORTED, (post.diagnostics.uniqueness, post.reasons)
    assert RouteReason.MULTISTART_INCOMPLETE in post.diagnostics.downgrades
    routed = route_uncertainty(calibration=calibration, observations=P.observations, forward=P.forward, multistart=policy)
    assert routed.claim is not RouteClaim.SUPPORTED


def test_huq01_the_one_start_mirror_mode_is_no_longer_supported_and_says_why():
    P, calibration = _mirror()
    post = local_gaussian_posterior(calibration, P.observations, P.forward, multistart=MultistartPolicy(starts=1))
    # the single Halton start sits on the estimate's side: no second mode can be seen, so the search was too small
    assert post.diagnostics.uniqueness == "MULTISTART_BELOW_MINIMUM_SEARCH"
    assert post.claim is RouteClaim.DOWNGRADED
    default = local_gaussian_posterior(calibration, P.observations, P.forward, multistart=MultistartPolicy())
    assert default.claim is RouteClaim.REFUSED and RouteReason.SECOND_MODE_FOUND in default.diagnostics.refusals


def test_huq01_the_policy_actually_used_is_committed_in_the_diagnostics_digest():
    P = S.affine()
    calibration = P.calibrate()
    post = local_gaussian_posterior(calibration, P.observations, P.forward, multistart=MultistartPolicy())
    thresholds = post.diagnostics.thresholds
    policy = MultistartPolicy()
    assert thresholds["multistart_starts"] == policy.starts
    assert thresholds["multistart_interior_fraction"] == policy.interior_fraction
    assert thresholds["multistart_mode_separation_quantile"] == policy.mode_separation_quantile
    assert thresholds["multistart_comparable_fit_quantile"] == policy.comparable_fit_quantile
    assert thresholds["multistart_max_evaluations"] == policy.max_evaluations
    assert thresholds["multistart_maximum_retractions"] == policy.maximum_retractions
    assert thresholds["multistart_minimum_starts"] == 6
    # the same search with a larger evaluation budget finds the same starts and entries; only the policy differs
    richer = local_gaussian_posterior(calibration, P.observations, P.forward, multistart=MultistartPolicy(max_evaluations=4000))
    assert richer.claim is post.claim is RouteClaim.SUPPORTED
    assert richer.diagnostics.digest != post.diagnostics.digest


def _cubic():
    x = np.linspace(0.0, 1.0, 16)
    return S.Problem("three", lambda t, x: t[0] + t[1] * x + t[2] * x ** 2, x, (1.0, 0.5, -0.3), 0.02,
                     (-10.0, -10.0, -10.0), (10.0, 10.0, 10.0), (0.0, 0.0, 0.0))


def test_huq01_the_minimum_search_grows_with_the_dimension():
    P = _cubic()
    calibration = P.calibrate()
    six = local_gaussian_posterior(calibration, P.observations, P.forward, multistart=MultistartPolicy())
    assert six.diagnostics.thresholds["multistart_minimum_starts"] == 8
    assert six.claim is RouteClaim.DOWNGRADED and six.diagnostics.downgrades == (RouteReason.MULTISTART_INCOMPLETE,)
    eight = local_gaussian_posterior(calibration, P.observations, P.forward, multistart=MultistartPolicy(starts=8))
    assert eight.claim is RouteClaim.SUPPORTED, eight.reasons


# ---------------------------------------------------------------------------
# HUQ-08: a saddle, a cross term, and a better optimum next to the estimate
# ---------------------------------------------------------------------------
def _principal_frame(P):
    calibration = P.calibrate()
    base = local_gaussian_posterior(calibration, P.observations, P.forward, multistart=None)
    cov = np.asarray(base._design_covariance)
    z0 = np.asarray(base.inference_point)
    lam, vec = np.linalg.eigh(cov)
    return calibration, z0, vec[:, 0], vec[:, 1], math.sqrt(lam[0]), math.sqrt(lam[1])


def test_huq08_a_saddle_whose_descent_lies_between_the_principal_axes_is_refused():
    A = S.affine()
    calibration, z0, v1, v2, s1, s2 = _principal_frame(A)
    residual = A.observed - (z0[0] + z0[1] * A.x)

    def model(t, x):
        dz = np.asarray(t, dtype=float) - z0
        u1, u2 = float(v1 @ dz) / s1, float(v2 @ dz) / s2
        return t[0] + t[1] * x + 0.5 * u1 * u2 * residual   # prediction moves toward the data where u1*u2 > 0

    B = S.Problem("affine", model, A.x, (1.0, 2.0), 0.05, (-10.0, -10.0), (10.0, 10.0), (0.0, 0.0), observed=A.observed)
    for multistart in (None, MultistartPolicy()):
        post = local_gaussian_posterior(calibration, B.observations, B.forward, multistart=multistart)
        assert post.claim is RouteClaim.REFUSED, (multistart, post.reasons)
        assert RouteReason.NOT_A_LOCAL_MINIMUM in post.diagnostics.refusals
        assert post.covariance is None


def test_huq08_a_cross_term_invisible_along_the_principal_axes_is_measured():
    A = S.affine()
    calibration, z0, v1, v2, s1, s2 = _principal_frame(A)
    J = np.column_stack([np.ones_like(A.x), A.x])
    residual = A.observed - (z0[0] + z0[1] * A.x)
    q, _ = np.linalg.qr(np.column_stack([J, residual, A.x ** 2]))
    direction = q[:, 3] * A.sigma

    def model(t, x):
        dz = np.asarray(t, dtype=float) - z0
        return t[0] + t[1] * x + 30.0 * (float(v1 @ dz) / s1) * (float(v2 @ dz) / s2) * direction

    B = S.Problem("affine", model, A.x, (1.0, 2.0), 0.05, (-10.0, -10.0), (10.0, 10.0), (0.0, 0.0), observed=A.observed)
    post = local_gaussian_posterior(calibration, B.observations, B.forward, multistart=MultistartPolicy())
    assert post.claim is RouteClaim.REFUSED
    assert RouteReason.NONLINEAR_BEYOND_LOCAL_GAUSSIAN in post.diagnostics.refusals
    assert post.diagnostics.nonlinearity_index > 100.0


def _nearby_well():
    """A one-parameter linear fit plus a narrow well 3 sd from the estimate, deeper than the estimate's chi-square.

    The +/-2 sd probes cannot see the well; the first Halton start sits at its centre. The refit converges there,
    inside the mode-separation radius, with a LOWER objective: the estimate is not the optimum of its own basin.
    """
    x = np.linspace(0.1, 1.0, 12)
    plain = S.Problem("well", lambda t, xx: t[0] * xx, x, (2.0,), 0.05, (-10.0,), (10.0,), (1.0,), seed=2)
    t0 = float(plain.calibrate().estimate_vector[0])
    sd = 0.05 / math.sqrt(float(np.sum(x * x)))
    r0 = plain.observed - t0 * x
    assert float(np.sum((r0 / 0.05) ** 2)) > 10.5, "the well must be deeper than the estimate's chi-square"

    def model(t, xx):
        u = (t[0] - t0) / sd
        return t[0] * xx + math.exp(-((u - 3.0) / 0.3) ** 2) * r0

    return S.Problem("well", model, x, (2.0,), 0.05, (t0 - 7.0 * sd,), (t0 + 13.0 * sd,), (t0 - sd,), observed=plain.observed)


def test_huq08_a_converged_refit_below_the_estimate_is_never_the_same_optimum():
    P = _nearby_well()
    calibration = P.calibrate()
    post = local_gaussian_posterior(calibration, P.observations, P.forward, multistart=MultistartPolicy())
    lower = [m for m in post.diagnostics.multistart if m.get("status") == "CALIBRATION_CONVERGED"
             and m["chi_square"] < calibration.objective_value - 1.0]
    assert lower, "the refit from the well's centre must converge below the estimate"
    assert all(m["classification"] != "SAME_OPTIMUM" for m in lower)
    assert post.claim is RouteClaim.REFUSED
    assert RouteReason.NOT_A_LOCAL_MINIMUM in post.diagnostics.refusals


# ---------------------------------------------------------------------------
# HUQ-10: probes that were not evaluated are not evidence of linearity
# ---------------------------------------------------------------------------
def _tight_nonlinear():
    model = lambda t, x: t[1] * np.exp(-t[0] * x)  # noqa: E731
    x = np.linspace(0.0, 1.0, 8)
    truth = np.array([3.0, 2.0])
    wide = S.Problem("wide", model, x, truth, 0.35, (0.01, 0.01), (20.0, 10.0), truth, observed=model(truth, x))
    sd = np.sqrt(np.diag(np.asarray(local_gaussian_posterior(wide.calibrate(), wide.observations, wide.forward,
                                                             multistart=None)._design_covariance)))
    return S.Problem("tight", model, x, truth, 0.35, truth - 1.5 * sd, truth + 1.5 * sd, truth, observed=model(truth, x))


def test_huq10_a_route_whose_probes_all_left_the_bounds_emits_no_covariance():
    P = _tight_nonlinear()
    calibration = P.calibrate()
    post = local_gaussian_posterior(calibration, P.observations, P.forward, multistart=MultistartPolicy())
    assert post.diagnostics.minimum_chi_square_rise == math.inf, "every probe leaves the +/-1.5 sd box"
    assert math.isnan(post.diagnostics.nonlinearity_index)
    assert post.claim is RouteClaim.REFUSED and post.covariance is None
    assert RouteReason.NONLINEAR_BEYOND_LOCAL_GAUSSIAN in post.diagnostics.refusals
    routed = route_uncertainty(calibration=calibration, observations=P.observations, forward=P.forward,
                               multistart=MultistartPolicy())
    assert routed.decision is RouteDecision.REFUSED and routed.covariance is None
