"""Hybrid UQ at its trust boundaries: what the route must refuse, downgrade or reject rather than believe.

Every test here is adversarial or states the legitimate case its adversary is measured against. Each guard it
exercises is also removed on purpose by a formal mutation in ``tests/mutation_guards.py`` (GUARD 27), and this
module is that mutation's target suite.
"""

from __future__ import annotations

import hashlib

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
