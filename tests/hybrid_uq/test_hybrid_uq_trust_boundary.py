"""Hybrid UQ at its trust boundaries: what the route must refuse, downgrade or reject rather than believe.

Every test here is adversarial or states the legitimate case its adversary is measured against. Each guard it
exercises is also removed on purpose by a formal mutation in ``tests/mutation_guards.py`` (GUARD 27), and this
module is that mutation's target suite.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import math

import numpy as np
import pytest

import hybrid_synthetic as S
from engcore.hybrid_uq import (
    HybridUQError,
    RouteClaim,
    RouteDecision,
    RouteRefusedError,
    local_gaussian_posterior,
    reconstruct_local_sensitivity,
    route_uncertainty,
)
from engcore.hybrid_uq.sensitivity import DEFAULT_RELATIVE_STEP, DERIVATIVE_RELATIVE_TOLERANCE, inference_bounds, to_inference
from engcore.scientific.units.quantity import Quantity

UNIT = "dimensionless"


# ---------------------------------------------------------------------------
# finite-difference derivatives must be shown to converge
# ---------------------------------------------------------------------------
def _weighted_relative_error(sensitivity, analytic):
    J = np.asarray(sensitivity.jacobian)
    sigma = np.asarray(sensitivity.sigma)[:, None]
    return np.linalg.norm((J - analytic) / sigma, axis=0) / np.linalg.norm(analytic / sigma, axis=0)


def test_q_a_wide_bound_range_no_longer_biases_the_derivative():
    """The starting step is 1e-5 of the range; over [0.01, 1e5] that is a whole unit of a decay rate near 3."""
    x = np.linspace(0.0, 1.0, 8)
    P = S.Problem("wide_decay", lambda t, x: t[1] * np.exp(-t[0] * x), x, (3.0, 2.0), 0.01, (0.01, 0.01), (1.0e5, 10.0),
                  (2.5, 1.5))
    calibration = P.calibrate()
    theta = np.asarray(calibration.estimate_vector)
    analytic = np.column_stack([-theta[1] * x * np.exp(-theta[0] * x), np.exp(-theta[0] * x)])
    # what a single step at the starting size gives: materially biased
    h0 = DEFAULT_RELATIVE_STEP * (1.0e5 - 0.01)
    single = (P.model(theta + [h0, 0.0], x) - P.model(theta - [h0, 0.0], x)) / (2.0 * h0)
    sigma = np.asarray(P.sigma)
    assert np.linalg.norm((single - analytic[:, 0]) / sigma) / np.linalg.norm(analytic[:, 0] / sigma) > 0.05
    sensitivity = reconstruct_local_sensitivity(calibration, P.observations, P.forward)
    assert np.all(_weighted_relative_error(sensitivity, analytic) < 2 * DERIVATIVE_RELATIVE_TOLERANCE)
    assert sensitivity.steps[0] < h0


def test_r_an_affine_model_matches_its_analytic_jacobian():
    P = S.affine()
    sensitivity = reconstruct_local_sensitivity(P.calibrate(), P.observations, P.forward)
    analytic = np.column_stack([np.ones_like(P.x), P.x])
    assert np.allclose(sensitivity.jacobian, analytic, rtol=0.0, atol=1e-8)
    assert sensitivity.steps == tuple(DEFAULT_RELATIVE_STEP * (hi - lo) for lo, hi in zip(*inference_bounds(P.parameters)))


def test_s_a_log_transformed_derivative_is_taken_in_log_space():
    x = np.linspace(0.1, 1.0, 8)
    P = S.Problem("log_k", lambda t, x: t[0] * x, x, (0.2,), 0.01, (1e-6,), (5.0,), (1.0,), transforms=("log",))
    calibration = P.calibrate()
    k = float(calibration.estimate_vector[0])
    sensitivity = reconstruct_local_sensitivity(calibration, P.observations, P.forward)
    # d(k x)/d(ln k) = k x
    assert np.allclose(np.asarray(sensitivity.jacobian)[:, 0], k * x, rtol=2 * DERIVATIVE_RELATIVE_TOLERANCE, atol=0.0)
    assert sensitivity.inference_transforms == ("log",)


def test_t_a_one_sided_derivative_at_a_bound_is_refined_until_it_converges():
    x = np.linspace(0.0, 1.0, 10)
    P = S.Problem("curved_at_bound", lambda t, x: t[0] * np.exp(t[1] * x), x, (1.0, -0.05), 0.02, (0.1, 0.0), (5.0, 2000.0),
                  (0.5, 0.5))
    calibration = P.calibrate()
    theta = np.asarray(calibration.estimate_vector)
    lower, upper = inference_bounds(P.parameters)
    z0 = to_inference(theta, ("identity", "identity"))
    h0 = DEFAULT_RELATIVE_STEP * (upper[1] - lower[1])
    assert z0[1] - h0 < lower[1], "the estimate sits within one starting step of its lower bound"
    sensitivity = reconstruct_local_sensitivity(calibration, P.observations, P.forward)
    assert sensitivity.one_sided[1] is True
    assert sensitivity.steps[1] < h0
    analytic = np.column_stack([np.exp(theta[1] * x), theta[0] * x * np.exp(theta[1] * x)])
    assert np.all(_weighted_relative_error(sensitivity, analytic) < 4 * DERIVATIVE_RELATIVE_TOLERANCE)


def _dithered(P, amplitude):
    """The same model plus a deterministic dither with no derivative at any resolvable scale.

    The offset is a hash of the parameters' exact float bits, so it jumps to an unrelated value from one
    representable point to the next and no step size makes two difference quotients agree. The amplitude is far
    below sigma: the +/-2 sd probes cannot see it, and without the convergence check it went straight into the
    Jacobian as a derivative of order amplitude / step.
    """
    def forward(theta):
        bits = hashlib.sha256(np.asarray(theta, dtype="<f8").tobytes()).digest()
        offset = int.from_bytes(bits[:8], "little") / 2.0 ** 64 - 0.5
        values = P.model(np.asarray(theta, dtype=float), P.x) + amplitude * offset
        return [Quantity(float(v), UNIT) for v in values]
    return forward


def test_u_a_derivative_that_never_stabilizes_produces_no_covariance():
    P = S.affine()
    calibration = P.calibrate()
    forward = _dithered(P, 1.0e-4)
    with pytest.raises(RouteRefusedError, match="did not stabilize"):
        reconstruct_local_sensitivity(calibration, P.observations, forward)
    with pytest.raises(RouteRefusedError, match="did not stabilize"):
        local_gaussian_posterior(calibration, P.observations, forward, multistart=None)
    result = route_uncertainty(calibration=calibration, observations=P.observations, forward=forward)
    assert result.decision is RouteDecision.REFUSED and result.claim is RouteClaim.REFUSED
    assert result.mean is None and result.covariance is None and result.local_posterior is None
    local = [c for c in result.considered if c["route"] == "LOCAL_GAUSSIAN"]
    assert local and local[0]["outcome"] == "REFUSED" and "did not stabilize" in local[0]["detail"]
    assert result.parameter_names == P.parameters.names


# ---------------------------------------------------------------------------
# a supplied LocalSensitivity is a trust boundary
# ---------------------------------------------------------------------------
def _honest_supplied():
    P = S.affine()
    calibration = P.calibrate()
    reconstructed = reconstruct_local_sensitivity(calibration, P.observations, P.forward)
    return P, calibration, dataclasses.replace(reconstructed, method="supplied", evaluation_count=0)


def _route_with(P, calibration, sensitivity):
    return local_gaussian_posterior(calibration, P.observations, P.forward, multistart=None, sensitivity=sensitivity)


@pytest.mark.parametrize("field,tamper,message", [
    ("sigma", lambda s: tuple(v * 1.5 for v in s.sigma), "observation sigmas"),                        # A
    ("observed", lambda s: tuple(v + 0.01 for v in s.observed), "observed values"),                   # B
    ("observation_units", lambda s: ("volt",) * len(s.observation_units), "observation units"),        # C
    ("inference_transforms", lambda s: ("identity", "log"), "inference transforms"),                  # D
    ("parameter_names", lambda s: tuple(reversed(s.parameter_names)), "parameter names"),
], ids=["A_sigma", "B_observed", "C_units", "D_transforms", "names"])
def test_a_to_d_a_record_with_the_same_ids_and_estimate_but_other_material_state_is_rejected(field, tamper, message):
    P, calibration, supplied = _honest_supplied()
    tampered = dataclasses.replace(supplied, **{field: tamper(supplied)})
    assert tampered.parameter_set_digest == supplied.parameter_set_digest and tampered.estimate == supplied.estimate
    assert tampered.observation_keys == supplied.observation_keys and tampered.dataset_id == supplied.dataset_id
    with pytest.raises(HybridUQError, match=message):
        _route_with(P, calibration, tampered)


@pytest.mark.parametrize("field,tamper", [
    ("predicted", lambda s: (math.nan,) + s.predicted[1:]),                                           # E
    ("jacobian", lambda s: ((math.inf, s.jacobian[0][1]),) + s.jacobian[1:]),                        # F
    ("steps", lambda s: (0.0,) + s.steps[1:]),                                                        # G
    ("steps", lambda s: (-1e-4,) + s.steps[1:]),
    ("steps", lambda s: (math.inf,) + s.steps[1:]),
], ids=["E_predicted_nan", "F_jacobian_inf", "G_step_zero", "G_step_negative", "G_step_inf"])
def test_e_to_g_a_record_with_non_finite_numbers_or_an_impossible_step_is_not_a_record(field, tamper):
    _P, _calibration, supplied = _honest_supplied()
    with pytest.raises(HybridUQError, match="finite"):
        dataclasses.replace(supplied, **{field: tamper(supplied)})


def test_h_predictions_or_a_jacobian_that_disagree_with_the_forward_evaluator_are_rejected():
    P, calibration, supplied = _honest_supplied()
    shifted = dataclasses.replace(supplied, predicted=tuple(v + 0.5 * s for v, s in zip(supplied.predicted, supplied.sigma)))
    with pytest.raises(HybridUQError, match="prediction at the estimate"):
        _route_with(P, calibration, shifted)
    # a Jacobian whose slope column is 20% too large: the covariance it implies is materially too narrow
    scaled = dataclasses.replace(supplied, jacobian=tuple((row[0], 1.2 * row[1]) for row in supplied.jacobian))
    with pytest.raises(HybridUQError, match="Jacobian column for 'theta2'"):
        _route_with(P, calibration, scaled)


def test_i_an_honest_supplied_sensitivity_is_still_used_and_gives_the_reconstructed_posterior():
    P, calibration, supplied = _honest_supplied()
    from_supplied = _route_with(P, calibration, supplied)
    reconstructed = local_gaussian_posterior(calibration, P.observations, P.forward, multistart=None)
    assert from_supplied.sensitivity_digest == supplied.digest
    assert from_supplied.claim is reconstructed.claim
    assert np.array_equal(np.asarray(from_supplied.covariance), np.asarray(reconstructed.covariance))
    # a supplied analytic Jacobian, exact rather than finite-difference, is within the agreement and is the one used
    analytic = dataclasses.replace(supplied, jacobian=tuple((1.0, float(x)) for x in P.x))
    assert _route_with(P, calibration, analytic).sensitivity_digest == analytic.digest


# ---------------------------------------------------------------------------
# a covariance must be a covariance, not a symmetric matrix with a positive diagonal
# ---------------------------------------------------------------------------
def _supported_posterior():
    P = S.affine()
    post = local_gaussian_posterior(P.calibrate(), P.observations, P.forward, multistart=None)
    assert post.covariance is not None
    return P, post


def test_j_an_indefinite_covariance_is_rejected_constructed_or_read_back():
    _P, post = _supported_posterior()
    indefinite = ((1.0, 2.0), (2.0, 1.0))
    assert np.all(np.diag(indefinite) > 0) and np.min(np.linalg.eigvalsh(indefinite)) == pytest.approx(-1.0)
    with pytest.raises(HybridUQError, match="not positive semidefinite"):
        dataclasses.replace(post, covariance=indefinite)
    payload = post.to_dict()
    payload["covariance"] = [list(row) for row in indefinite]
    with pytest.raises(HybridUQError, match="not positive semidefinite"):
        type(post).from_dict(payload)


def test_j_an_indefinite_direction_is_found_whatever_the_parameter_scales():
    """A tolerance on raw eigenvalues relative to the largest would pass this: the negative eigenvalue is -1e-15 of
    it. In correlation units the two parameters are correlated at 1 + 1e-7, which no covariance can be."""
    _P, post = _supported_posterior()
    big, small, rho = 1.0e8, 1.0e-8, 1.0 + 1.0e-7
    scaled = ((big, rho * math.sqrt(big * small)), (rho * math.sqrt(big * small), small))
    assert np.min(np.linalg.eigvalsh(scaled)) > -1e-14 * big
    with pytest.raises(HybridUQError, match="not positive semidefinite"):
        dataclasses.replace(post, covariance=scaled)


def test_k_a_covariance_singular_only_within_roundoff_is_accepted():
    _P, post = _supported_posterior()
    rho = 1.0 + 2.0 * np.finfo(float).eps
    roundoff = ((1.0, rho), (rho, 1.0))
    assert np.min(np.linalg.eigvalsh(roundoff)) < 0.0
    assert dataclasses.replace(post, covariance=roundoff).covariance == roundoff


def test_l_a_negative_predictive_variance_raises_instead_of_becoming_zero():
    from engcore.hybrid_uq import linearized_predictive_uq
    from engcore.uq import PredictiveObservableSpec

    _P, post = _supported_posterior()
    # A record the constructor would refuse, forced past it, as a corrupted in-memory object would be.
    object.__setattr__(post, "covariance", ((1.0, 2.0), (2.0, 1.0)))
    spec = PredictiveObservableSpec("difference", UNIT, Quantity(0.05, UNIT))
    with pytest.raises(HybridUQError, match="negative beyond roundoff"):
        linearized_predictive_uq(post, lambda t: [Quantity(t[0] - t[1], UNIT)], [spec])


def test_m_a_valid_covariance_still_round_trips_byte_identically():
    from engcore.hybrid_uq._records import canonical_bytes

    P, post = _supported_posterior()
    again = type(post).from_dict(json.loads(canonical_bytes(post.to_dict())))
    assert canonical_bytes(again.to_dict()) == canonical_bytes(post.to_dict()) and again.digest == post.digest
    result = route_uncertainty(calibration=P.calibrate(), observations=P.observations, forward=P.forward)
    restored = type(result).from_dict(json.loads(canonical_bytes(result.to_dict())))
    assert canonical_bytes(restored.to_dict()) == canonical_bytes(result.to_dict()) and restored.digest == result.digest
