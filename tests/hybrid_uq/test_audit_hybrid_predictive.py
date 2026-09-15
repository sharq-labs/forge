"""Audit stream "hybrid": the linearized predictive's linearity check (HUQ-07, HUQ-11).

HUQ-07  the +/-2 sd probes looked along principal axes only: g = 100 + c u1 + K u1 u2 read SUPPORTED with a
        nonlinearity of 5e-12 while its Monte Carlo sd under the same Gaussian was 50 times the reported one;
HUQ-11  deviations were scaled by the TOTAL sd, so a large measurement sigma hid a parameter part that was
        curved enough to put the parameter interval 0.8 sd off.
"""

from __future__ import annotations

import math

import numpy as np

import hybrid_synthetic as S
from engcore.hybrid_uq import MultistartPolicy, RouteClaim, RouteReason, linearized_predictive_uq, local_gaussian_posterior
from engcore.scientific.units.quantity import Quantity
from engcore.uq import PredictiveObservableSpec

UNIT = "dimensionless"


def _frame(problem, multistart=MultistartPolicy()):
    post = local_gaussian_posterior(problem.calibrate(), problem.observations, problem.forward, multistart=multistart)
    cov = np.asarray(post.covariance)
    lam, vec = np.linalg.eigh(cov)
    return post, np.asarray(post.inference_point), vec, np.sqrt(lam)


def _spec(sigma=None):
    return PredictiveObservableSpec("g", UNIT, None if sigma is None else Quantity(sigma, UNIT))


def test_huq07_a_cross_term_between_two_principal_axes_is_not_linear():
    post, z0, vec, s = _frame(S.affine())
    assert post.claim is RouteClaim.SUPPORTED

    def predict(theta):
        dz = np.asarray(theta, dtype=float) - z0
        u1, u2 = float(vec[:, 0] @ dz) / s[0], float(vec[:, 1] @ dz) / s[1]
        return [Quantity(100.0 + u1 + 50.0 * u1 * u2, UNIT)]

    (r,) = linearized_predictive_uq(post, predict, [_spec()])
    assert r.route_claim is RouteClaim.DOWNGRADED
    assert RouteReason.PREDICTIVE_NONLINEAR in r.reasons
    assert r.predictive_nonlinearity > 1.0


def _cubic():
    x = np.linspace(0.0, 1.0, 16)
    return S.Problem("three", lambda t, x: t[0] + t[1] * x + t[2] * x ** 2, x, (1.0, 0.5, -0.3), 0.02,
                     (-10.0, -10.0, -10.0), (10.0, 10.0, 10.0), (0.0, 0.0, 0.0))


def test_huq07_a_three_way_term_is_seen_along_the_predictive_gradient():
    """u1 u2 u3 vanishes on every principal axis and every diagonal between two axes; along Sigma grad g it does not."""
    post, z0, vec, s = _frame(_cubic(), multistart=MultistartPolicy(starts=8))
    assert post.claim is RouteClaim.SUPPORTED, post.reasons

    def predict(theta):
        dz = np.asarray(theta, dtype=float) - z0
        u = [float(vec[:, k] @ dz) / s[k] for k in range(3)]
        return [Quantity(5.0 + (u[0] + u[1] + u[2]) + 3.0 * u[0] * u[1] * u[2], UNIT)]

    (r,) = linearized_predictive_uq(post, predict, [_spec()])
    assert RouteReason.PREDICTIVE_NONLINEAR in r.reasons, (r.reasons, r.predictive_nonlinearity)
    assert r.route_claim is RouteClaim.DOWNGRADED


def test_huq11_a_large_measurement_sigma_does_not_hide_a_curved_parameter_part():
    post, z0, vec, s = _frame(S.affine())

    def predict(theta):
        u1 = float(vec[:, 0] @ (np.asarray(theta, dtype=float) - z0)) / s[0]
        return [Quantity(10.0 + u1 + 0.8 * u1 ** 2, UNIT)]

    (bare,) = linearized_predictive_uq(post, predict, [_spec()])
    (noisy,) = linearized_predictive_uq(post, predict, [_spec(50.0)])
    assert bare.route_claim is RouteClaim.DOWNGRADED and RouteReason.PREDICTIVE_NONLINEAR in bare.reasons
    assert noisy.route_claim is RouteClaim.DOWNGRADED, noisy.predictive_nonlinearity
    assert RouteReason.PREDICTIVE_NONLINEAR in noisy.reasons
    assert math.isclose(noisy.predictive_nonlinearity, bare.predictive_nonlinearity, rel_tol=1e-9)
