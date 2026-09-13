"""The hybrid router: deterministic, never looser than V1 on grids, and explicit about every route it passed over."""

from __future__ import annotations

import numpy as np
import pytest

import hybrid_synthetic as S
from engcore.hybrid_uq import (
    GRID_ROUTE_MAXIMUM_PARAMETERS,
    ApproximationClass,
    GridRebuildPolicy,
    HybridUQError,
    MultistartPolicy,
    RouteClaim,
    RouteDecision,
    RouteReason,
    RouteRefusedError,
    route_uncertainty,
    routed_predictive_uncertainty,
)
from engcore.scientific.units.quantity import Quantity
from engcore.uq import PredictiveObservableSpec

UNIT = "dimensionless"


def _inputs(problem):
    return dict(calibration=problem.calibrate(), observations=problem.observations, forward=problem.forward,
                multistart=MultistartPolicy())


def _reference(problem, axes):
    grid = problem.grid(axes)
    return np.asarray(grid.mean), np.sqrt(np.diag(grid.covariance))


def test_a_resolved_grid_is_used_as_supplied():
    P = S.affine()
    grid = P.grid([np.linspace(0.6, 1.3, 61), np.linspace(1.4, 2.7, 61)])
    result = route_uncertainty(grid=grid, **_inputs(P))
    assert result.decision is RouteDecision.GRID_AS_SUPPLIED
    assert result.approximation_class is ApproximationClass.POSTERIOR_GRID and result.claim is RouteClaim.SUPPORTED
    assert result.local_posterior is None and result.coordinates == "natural"
    assert np.allclose(result.mean, grid.mean)
    assert result.considered[0]["outcome"] == "USED"


def test_an_unresolved_grid_is_never_trusted():
    """F5 over its declared bounds: V1 refuses the aliased grid, so the router must too."""
    P = S.weak_identification()
    aliased = P.grid([np.linspace(-50, 50, 401), np.linspace(-5, 5, 401)])
    result = route_uncertainty(grid=aliased, **_inputs(P))
    assert result.considered[0]["outcome"] == "REFUSED_BY_V1"
    assert result.considered[0]["reason"] == RouteReason.GRID_UNRESOLVED.value
    assert result.decision is RouteDecision.LOCAL_GAUSSIAN
    mu, cov = S.gaussian_truth(P)
    assert np.allclose(result.mean, mu, atol=1e-6 * np.sqrt(np.diag(cov)).max())
    assert not np.allclose(result.mean, aliased.mean, atol=0.1 * np.sqrt(np.diag(cov)).max())


def test_an_unresolved_grid_alone_is_a_refusal_with_no_numbers():
    P = S.weak_identification()
    aliased = P.grid([np.linspace(-50, 50, 401), np.linspace(-5, 5, 401)])
    result = route_uncertainty(grid=aliased)
    assert result.decision is RouteDecision.REFUSED and result.claim is RouteClaim.REFUSED
    assert result.mean is None and result.covariance is None and result.identifiability is None
    with pytest.raises(RouteRefusedError):
        routed_predictive_uncertainty(result, [PredictiveObservableSpec("y", UNIT)], predict=lambda t: [Quantity(0.0, UNIT)])


def test_a_grid_beyond_the_validated_dimension_is_passed_over():
    x = np.linspace(0.0, 1.0, 20)
    P = S.Problem("six", lambda t, x: t[0] + t[1] * x + t[2] * x ** 2 + t[3] * x ** 3 + t[4] * x ** 4 + t[5] * x ** 5, x,
                  (1, 0.5, 0.2, 0.1, 0.05, 0.02), 0.01, (-10,) * 6, (10,) * 6, (0,) * 6)
    grid = P.grid([np.linspace(-1.0, 1.0, 3)] * 6)
    result = route_uncertainty(grid=grid)
    assert result.considered[0]["reason"] == RouteReason.GRID_BEYOND_VALIDATED_DIMENSION.value
    with pytest.raises(HybridUQError):
        route_uncertainty(grid=grid, maximum_grid_parameters=GRID_ROUTE_MAXIMUM_PARAMETERS + 1)


def test_a_supported_local_route_is_used_when_no_grid_is_supplied():
    result = route_uncertainty(**_inputs(S.affine()))
    assert result.decision is RouteDecision.LOCAL_GAUSSIAN and result.claim is RouteClaim.SUPPORTED
    assert result.approximation_class is ApproximationClass.LOCAL_GAUSSIAN_APPROXIMATION
    assert result.coordinates == "inference" and result.identifiability is not None


@pytest.mark.parametrize("make,axes", [
    (S.strong_nonlinearity, [np.linspace(0.01, 20.0, 481), np.linspace(0.01, 10.0, 481)]),
    (S.at_bound, [np.linspace(0.8, 1.2, 401), np.linspace(0.0, 0.3, 401)]),
    (S.mirror_mode, [np.linspace(-3.0, 3.0, 6001)]),
    (S.bimodal_two_parameter, [np.linspace(-3.0, 3.0, 1201), np.linspace(-2.0, 2.0, 801)]),
], ids=["F1_nonlinear", "F2_at_bound", "F4_mirror", "bimodal"])
def test_a_refused_local_route_is_replaced_by_a_verified_rebuilt_grid_that_matches_a_dense_reference(make, axes):
    P = make()
    result = route_uncertainty(rebuild=GridRebuildPolicy(P.table_builder()), **_inputs(P))
    assert result.local_posterior.claim is RouteClaim.REFUSED
    assert result.decision is RouteDecision.GRID_REBUILT_FROM_LOCAL_COVARIANCE
    assert result.approximation_class is ApproximationClass.POSTERIOR_GRID
    mean, sd = _reference(P, axes)
    assert np.all(np.abs(np.asarray(result.mean) - mean) / sd < 0.05)
    assert np.all(np.abs(np.sqrt(np.diag(result.covariance)) / sd - 1.0) < 0.05)


def test_structural_refusals_are_not_rebuilt_and_end_in_a_refusal():
    P = S.nearly_singular()
    result = route_uncertainty(rebuild=GridRebuildPolicy(P.table_builder()), **_inputs(P))
    assert result.decision is RouteDecision.REFUSED
    assert result.considered[-1]["outcome"] == "PASSED_OVER"


def test_a_rebuild_over_budget_is_passed_over():
    P = S.bimodal_two_parameter()
    result = route_uncertainty(rebuild=GridRebuildPolicy(P.table_builder(), maximum_points=200), **_inputs(P))
    assert result.decision is RouteDecision.REFUSED
    assert any(c.get("reason") == RouteReason.GRID_REBUILD_OVER_BUDGET.value for c in result.considered)


def test_a_downgraded_local_route_is_reported_downgraded():
    P = S.affine()
    inputs = _inputs(P)
    inputs["multistart"] = None
    result = route_uncertainty(**inputs)
    assert result.decision is RouteDecision.LOCAL_GAUSSIAN and result.claim is RouteClaim.DOWNGRADED
    assert result.considered[-1]["route"] == "LOCAL_GAUSSIAN_DOWNGRADED"


def test_routing_is_deterministic():
    P = S.strong_nonlinearity()
    first = route_uncertainty(rebuild=GridRebuildPolicy(P.table_builder()), **_inputs(P))
    P2 = S.strong_nonlinearity()
    second = route_uncertainty(rebuild=GridRebuildPolicy(P2.table_builder()), **_inputs(P2))
    assert first.digest == second.digest


def test_routed_predictive_uses_the_route_that_was_chosen():
    P = S.affine()
    local = route_uncertainty(**_inputs(P))
    (r,) = routed_predictive_uncertainty(local, [PredictiveObservableSpec("y@1", UNIT, Quantity(0.05, UNIT))],
                                         predict=lambda t: [Quantity(t[0] + t[1], UNIT)])
    assert r.approximation_class is ApproximationClass.LINEARIZED_PREDICTIVE_UQ
    grid = route_uncertainty(grid=P.grid([np.linspace(0.6, 1.3, 61), np.linspace(1.4, 2.7, 61)]))
    with pytest.raises(HybridUQError, match="predictive_table"):
        routed_predictive_uncertainty(grid, [PredictiveObservableSpec("y@1", UNIT)])


def test_a_result_cannot_claim_a_route_it_did_not_take():
    import dataclasses

    result = route_uncertainty(**_inputs(S.affine()))
    with pytest.raises(HybridUQError):
        dataclasses.replace(result, approximation_class=ApproximationClass.POSTERIOR_GRID)
    with pytest.raises(HybridUQError):
        dataclasses.replace(result, decision=RouteDecision.REFUSED)
