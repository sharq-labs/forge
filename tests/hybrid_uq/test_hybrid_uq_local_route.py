"""LOCAL_GAUSSIAN_APPROXIMATION: exact where it should be, and refused or downgraded wherever an assumption fails."""

from __future__ import annotations

import math

import numpy as np
import pytest

import hybrid_synthetic as S
from engcore.hybrid_uq import (
    ApproximationClass,
    HybridUQError,
    LocalSensitivity,
    MultistartPolicy,
    RouteClaim,
    RouteReason,
    RouteRefusedError,
    assess_routed_identifiability,
    local_gaussian_posterior,
    reconstruct_local_sensitivity,
)
from engcore.inference import CalibrationStatus, IdentifiabilityStatus


def _route(problem, multistart=MultistartPolicy()):
    calibration = problem.calibrate()
    assert calibration.status is CalibrationStatus.CONVERGED, calibration.termination_reason
    return calibration, local_gaussian_posterior(calibration, problem.observations, problem.forward, multistart=multistart)


# ---------------------------------------------------------------------------
# where the approximation is exact
# ---------------------------------------------------------------------------
def test_an_affine_model_far_from_its_bounds_gives_the_exact_gaussian():
    P = S.affine()
    _, post = _route(P)
    mu, cov = S.gaussian_truth(P)
    assert post.claim is RouteClaim.SUPPORTED and post.reasons == ()
    assert post.approximation_class is ApproximationClass.LOCAL_GAUSSIAN_APPROXIMATION and post.exact_posterior is False
    assert np.allclose(post.inference_point, mu, rtol=0, atol=1e-8)
    assert np.allclose(np.asarray(post.covariance), cov, rtol=1e-6)
    assert post.diagnostics.uniqueness == "MULTISTART_NO_SECOND_MODE"
    assert post.diagnostics.nonlinearity_index < 1e-6


def test_the_cost_is_order_p_plus_multistart():
    P = S.affine()
    calibration, post = _route(P, multistart=None)
    # 4p + 1 Jacobian calls (a step and its half per column, to show the derivative converged), 2p principal-axis
    # probes and 2p(p - 1) diagonal probes between two axes: 4p + 1 + 2p^2. This pinned 6p + 1 before audit HUQ-08,
    # when the probes looked along the principal axes only and a cross term between two of them went unseen.
    p = 2
    # + 4p tail probes at 3 and 6 sd along the principal axes (CORE-003); all inside the declared bounds here
    assert post.diagnostics.evaluation_count == 4 * p + 1 + 2 * p * p + 4 * p


def test_intervals_are_labelled_and_mapped_back_through_a_log_transform():
    P = S.Problem("loglinear", lambda t, x: t[0] * x, np.linspace(0.5, 2.0, 12), (3.0,), 0.01, (0.1,), (50.0,), (1.0,),
                  transforms=("log",))
    calibration = P.calibrate()
    post = local_gaussian_posterior(calibration, P.observations, P.forward, multistart=MultistartPolicy())
    assert post.claim is not RouteClaim.REFUSED, post.reasons
    (interval,) = post.intervals()
    assert interval.approximation_class is ApproximationClass.LOCAL_GAUSSIAN_APPROXIMATION
    assert interval.inference_transform == "log"
    z, sd = post.inference_point[0], post.standard_deviations[0]
    assert math.isclose(interval.lower, math.exp(z - 1.959963984540054 * sd), rel_tol=1e-12)
    assert math.isclose(interval.upper, math.exp(z + 1.959963984540054 * sd), rel_tol=1e-12)
    assert interval.lower < interval.estimate < interval.upper


def test_a_log_declared_parameter_is_differentiated_in_log_space():
    P = S.Problem("loglinear", lambda t, x: t[0] * x, np.linspace(0.5, 2.0, 12), (3.0,), 0.01, (0.1,), (50.0,), (1.0,),
                  transforms=("log",))
    calibration = P.calibrate()
    sensitivity = reconstruct_local_sensitivity(calibration, P.observations, P.forward)
    k = calibration.estimate_vector[0]
    # d(k x)/d(ln k) = k x
    assert np.allclose(np.asarray(sensitivity.jacobian)[:, 0], k * P.x, rtol=1e-6)
    assert sensitivity.inference_transforms == ("log",)


# ---------------------------------------------------------------------------
# the failure cases: refuse or downgrade, never precise uncertainty anyway
# ---------------------------------------------------------------------------
def test_strong_nonlinearity_is_refused():
    _, post = _route(S.strong_nonlinearity())
    assert post.claim is RouteClaim.REFUSED
    assert RouteReason.NONLINEAR_BEYOND_LOCAL_GAUSSIAN in post.diagnostics.refusals
    assert post.covariance is None
    with pytest.raises(RouteRefusedError):
        post.intervals()
    with pytest.raises(RouteRefusedError):
        assess_routed_identifiability(post)


def test_a_parameter_at_its_bound_is_refused():
    _, post = _route(S.at_bound())
    assert RouteReason.PARAMETER_AT_BOUND in post.diagnostics.refusals
    assert post.claim is RouteClaim.REFUSED and post.covariance is None
    assert "theta2" in post.diagnostics.at_bound


def test_a_nearly_singular_jacobian_is_refused():
    _, post = _route(S.nearly_singular())
    assert post.diagnostics.refusals == (RouteReason.NUMERICALLY_SINGULAR_JACOBIAN,)
    assert post.diagnostics.jacobian_condition > 1e8


def test_a_mirror_mode_is_refused_with_multistart_and_downgraded_without():
    _, with_starts = _route(S.mirror_mode())
    assert RouteReason.SECOND_MODE_FOUND in with_starts.diagnostics.refusals
    assert with_starts.diagnostics.uniqueness == "SECOND_MODE_FOUND"
    modes = [m for m in with_starts.diagnostics.multistart if m.get("classification") == "SECOND_MODE"]
    assert modes and all(m["estimate"][0] < 0.0 for m in modes)
    _, without = _route(S.mirror_mode(), multistart=None)
    assert without.claim is RouteClaim.DOWNGRADED
    assert without.diagnostics.downgrades == (RouteReason.GLOBAL_UNIQUENESS_NOT_ASSESSED,)


def test_a_two_parameter_multimodal_posterior_is_refused():
    _, post = _route(S.bimodal_two_parameter())
    assert RouteReason.SECOND_MODE_FOUND in post.diagnostics.refusals


def test_a_better_optimum_than_the_estimate_is_refused():
    """An asymmetric double well: calibrated from the wrong side, the estimate is a worse local optimum."""
    P = S.Problem("better_optimum", lambda t, x: t[0] ** 2 * x + 0.05 * t[0], np.linspace(1.0, 2.0, 8), (1.5,), 0.01,
                  (-3.0,), (3.0,), (-1.9,))
    calibration = P.calibrate()
    assert calibration.estimate_vector[0] < 0.0
    post = local_gaussian_posterior(calibration, P.observations, P.forward, multistart=MultistartPolicy())
    assert RouteReason.BETTER_OPTIMUM_FOUND in post.diagnostics.refusals
    assert post.diagnostics.uniqueness == "BETTER_OPTIMUM_FOUND"


def test_the_log_parameterization_of_a_linear_model_is_refused_as_nonlinear():
    _, linear = _route(S.log_parameterization("identity"))
    _, logged = _route(S.log_parameterization("log"))
    assert RouteReason.NONLINEAR_BEYOND_LOCAL_GAUSSIAN not in linear.reasons
    assert RouteReason.NONLINEAR_BEYOND_LOCAL_GAUSSIAN in logged.diagnostics.refusals


def test_weak_identification_is_a_valid_route_with_a_not_identifiable_verdict():
    """Route validity and identifiability are two verdicts, never merged."""
    P = S.weak_identification()
    _, post = _route(P)
    assert post.claim is RouteClaim.SUPPORTED
    ident = assess_routed_identifiability(post)
    assert ident.status is IdentifiabilityStatus.NOT_IDENTIFIABLE
    assert ident.route_claim is RouteClaim.SUPPORTED
    mu, cov = S.gaussian_truth(P)
    assert np.allclose(np.asarray(post.covariance), cov, rtol=1e-5)


def test_a_thin_correlated_ridge_is_exact_where_a_coarse_bounds_grid_aliases():
    P = S.thin_ridge()
    _, post = _route(P)
    mu, cov = S.gaussian_truth(P)
    assert abs(post.correlation[0, 1]) > 0.999
    sd = np.sqrt(np.diag(cov))
    # SciPy may stop at slightly different points across versions. Judge the
    # affine-Gaussian centre in its natural statistical scale, not raw units.
    # 1e-4 sigma is still 500x tighter than the route's 0.05-sigma stationarity contract.
    assert np.all(np.abs(np.asarray(post.inference_point) - mu) / sd < 1e-4)


def test_a_poorly_scaled_parameterization_is_downgraded_not_silently_trusted():
    P = S.Problem("poorly_scaled", lambda t, x: t[0] * 1e-9 + t[1] * 1e4 * x, np.linspace(0.0, 1.0, 12), (2e9, 1e-4), 0.05,
                  (0.0, -1.0), (1e10, 1.0), (1e9, 0.0))
    _, post = _route(P, multistart=None)
    assert post.diagnostics.raw_jacobian_condition > post.diagnostics.jacobian_condition * 1e6
    assert RouteReason.POORLY_SCALED_PARAMETERIZATION in post.diagnostics.downgrades


def test_no_residual_degrees_of_freedom_is_refused():
    P = S.Problem("exactly_determined", lambda t, x: t[0] + t[1] * x, np.asarray([0.0, 1.0]), (1.0, 2.0), 0.1,
                  (-10.0, -10.0), (10.0, 10.0), (0.0, 0.0))
    _, post = _route(P, multistart=None)
    assert post.diagnostics.refusals == (RouteReason.NO_RESIDUAL_DEGREES_OF_FREEDOM,)


def test_an_inadmissible_forward_point_near_the_estimate_is_refused():
    P = S.affine()
    calibration = P.calibrate()
    estimate = calibration.estimate_vector

    def refusing(theta):
        if abs(theta[0] - estimate[0]) > 0.0:
            return None
        return P.forward(theta)

    post = local_gaussian_posterior(calibration, P.observations, refusing, multistart=None)
    assert post.diagnostics.refusals == (RouteReason.FORWARD_INADMISSIBLE_NEAR_ESTIMATE,)


def test_a_failed_calibration_is_refused():
    P = S.affine()
    calibration = P.calibrate()
    import dataclasses

    failed = dataclasses.replace(calibration, status=CalibrationStatus.FAILED, estimates=(), residuals=())
    post = local_gaussian_posterior(failed, P.observations, P.forward, multistart=MultistartPolicy())
    assert post.diagnostics.refusals == (RouteReason.CALIBRATION_NOT_CONVERGED,)


# ---------------------------------------------------------------------------
# multistart policy and sensitivity retention
# ---------------------------------------------------------------------------
def test_the_multistart_is_deterministic_and_inside_the_bounds():
    P = S.weak_identification()
    first = MultistartPolicy().start_points(P.parameters)
    second = MultistartPolicy().start_points(P.parameters)
    assert first == second and len(first) == 6
    for start in first:
        assert -40.0 <= start[0] <= 40.0 and -4.0 <= start[1] <= 4.0
    assert len(set(first)) == 6


def test_a_supplied_sensitivity_is_used_and_must_belong_to_the_calibration():
    P = S.affine()
    calibration = P.calibrate()
    reconstructed = reconstruct_local_sensitivity(calibration, P.observations, P.forward)
    import dataclasses

    supplied = dataclasses.replace(reconstructed, method="supplied", evaluation_count=0)
    post = local_gaussian_posterior(calibration, P.observations, P.forward, multistart=None, sensitivity=supplied)
    assert post.sensitivity_digest == supplied.digest
    wrong = dataclasses.replace(reconstructed, estimate=(0.0, 0.0))
    with pytest.raises(HybridUQError, match="not this calibration's"):
        local_gaussian_posterior(calibration, P.observations, P.forward, multistart=None, sensitivity=wrong)


def test_multistart_is_a_required_decision():
    P = S.affine()
    calibration = P.calibrate()
    with pytest.raises(TypeError):
        local_gaussian_posterior(calibration, P.observations, P.forward)  # type: ignore[call-arg]


def test_a_refused_posterior_cannot_be_constructed_with_numbers():
    _, post = _route(S.strong_nonlinearity())
    import dataclasses

    with pytest.raises(HybridUQError, match="emits no covariance"):
        dataclasses.replace(post, covariance=((1.0, 0.0), (0.0, 1.0)))


def test_the_claim_must_follow_from_the_reasons():
    _, post = _route(S.affine())
    import dataclasses

    with pytest.raises(HybridUQError, match="does not follow"):
        dataclasses.replace(post.diagnostics, claim=RouteClaim.SUPPORTED, downgrades=(RouteReason.BOUND_WITHIN_3_SD,))
    assert math.isfinite(post.diagnostics.minimum_bound_distance_sd)


def test_an_inadmissible_multistart_start_is_replaced_by_another_halton_point_and_recorded():
    """A bounds box is not an admissible region: here only theta1 > theta2 is admissible.

    I-02 (batch 10) replaced retraction toward the estimate with replacement by the next unused point of the
    same Halton sequence, so the recorded count is `replacements` and the used start is a full-span point.
    """
    P = S.affine()
    base = P.forward

    def ordered(theta):
        return None if theta[0] >= theta[1] else base(theta)

    calibration = P.calibrate()
    post = local_gaussian_posterior(calibration, P.observations, ordered, multistart=MultistartPolicy())
    replaced = [m for m in post.diagnostics.multistart if m.get("replacements", 0) > 0]
    assert replaced, "the Halton starts include inadmissible points; at least one must be replaced"
    assert all("retractions" not in m for m in post.diagnostics.multistart), "nothing retracts any more"
    assert all(tuple(m["start"]) != tuple(m["proposed_start"]) for m in replaced), \
        "a replaced start is a different point from the one the model refused"
    assert all(m["status"] == "CALIBRATION_CONVERGED" for m in post.diagnostics.multistart)
    assert post.diagnostics.uniqueness == "MULTISTART_NO_SECOND_MODE"
    assert post.claim is RouteClaim.SUPPORTED


def test_the_admission_boundary_error_is_a_refusal_of_the_point_not_a_crash():
    from engcore.inference import InferenceAdmissibilityError

    P = S.affine()
    calibration = P.calibrate()
    estimate = calibration.estimate_vector

    def raising(theta):
        if abs(theta[1] - estimate[1]) > 0.0:
            raise InferenceAdmissibilityError("not admissible here")
        return P.forward(theta)

    post = local_gaussian_posterior(calibration, P.observations, raising, multistart=None)
    assert post.diagnostics.refusals == (RouteReason.FORWARD_INADMISSIBLE_NEAR_ESTIMATE,)

    def broken(theta):
        raise RuntimeError("a defect, not a refusal")

    with pytest.raises(RuntimeError):
        local_gaussian_posterior(calibration, P.observations, broken, multistart=None)
