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
    sd = np.sqrt(np.diag(cov))
    # Compare in posterior-sigma units so harmless optimizer endpoint changes
    # across SciPy versions cannot masquerade as a routing regression.
    assert np.all(np.abs(np.asarray(result.mean) - mu) / sd < 1e-4)
    assert not np.allclose(result.mean, aliased.mean, atol=0.1 * sd.max())


def test_an_unresolved_grid_alone_is_a_refusal_with_no_numbers():
    P = S.weak_identification()
    aliased = P.grid([np.linspace(-50, 50, 401), np.linspace(-5, 5, 401)])
    result = route_uncertainty(grid=aliased, observations=P.observations, forward=P.forward)
    assert result.considered[0]["outcome"] == "REFUSED_BY_V1"
    assert result.decision is RouteDecision.REFUSED and result.claim is RouteClaim.REFUSED
    assert result.mean is None and result.covariance is None and result.identifiability is None
    with pytest.raises(RouteRefusedError):
        routed_predictive_uncertainty(result, [PredictiveObservableSpec("y", UNIT)], predict=lambda t: [Quantity(0.0, UNIT)])


def test_a_grid_beyond_the_validated_dimension_is_passed_over():
    x = np.linspace(0.0, 1.0, 20)
    P = S.Problem("six", lambda t, x: t[0] + t[1] * x + t[2] * x ** 2 + t[3] * x ** 3 + t[4] * x ** 4 + t[5] * x ** 5, x,
                  (1, 0.5, 0.2, 0.1, 0.05, 0.02), 0.01, (-10,) * 6, (10,) * 6, (0,) * 6)
    grid = P.grid([np.linspace(-1.0, 1.0, 3)] * 6)
    result = route_uncertainty(grid=grid, observations=P.observations, forward=P.forward)
    assert result.considered[0]["reason"] == RouteReason.GRID_BEYOND_VALIDATED_DIMENSION.value
    with pytest.raises(HybridUQError):
        route_uncertainty(grid=grid, maximum_grid_parameters=GRID_ROUTE_MAXIMUM_PARAMETERS + 1)


def test_a_supported_local_route_is_used_when_no_grid_is_supplied():
    result = route_uncertainty(**_inputs(S.affine()))
    assert result.decision is RouteDecision.LOCAL_GAUSSIAN and result.claim is RouteClaim.SUPPORTED
    assert result.approximation_class is ApproximationClass.LOCAL_GAUSSIAN_APPROXIMATION
    assert result.coordinates == "inference" and result.identifiability is not None


@pytest.mark.parametrize("make,axes", [
    (S.at_bound, [np.linspace(0.8, 1.2, 401), np.linspace(0.0, 0.3, 401)]),
    (S.mirror_mode, [np.linspace(-3.0, 3.0, 6001)]),
    (S.bimodal_two_parameter, [np.linspace(-3.0, 3.0, 1201), np.linspace(-2.0, 2.0, 801)]),
], ids=["F2_at_bound", "F4_mirror", "bimodal"])
def test_a_refused_local_route_is_replaced_by_a_verified_rebuilt_grid_that_matches_a_dense_reference(make, axes):
    P = make()
    result = route_uncertainty(rebuild=GridRebuildPolicy(P.table_builder()), **_inputs(P))
    assert result.local_posterior.claim is RouteClaim.REFUSED
    assert result.decision is RouteDecision.GRID_REBUILT_FROM_LOCAL_COVARIANCE
    assert result.approximation_class is ApproximationClass.POSTERIOR_GRID
    mean, sd = _reference(P, axes)
    assert np.all(np.abs(np.asarray(result.mean) - mean) / sd < 0.05)
    assert np.all(np.abs(np.sqrt(np.diag(result.covariance)) / sd - 1.0) < 0.05)


def test_a_rebuilt_grid_whose_posterior_spans_both_declared_bounds_is_not_used():
    """F1 was the first case above until CORE-002 (scientific core audit 2026-09-16).

    Its decay rate's posterior density is within 7 nats of the peak at BOTH declared bounds, 0.01 and 20. The rebuilt
    grid matched a dense reference over those bounds and was SUPPORTED with sd 1.75 -- but that sd is the upper bound's:
    the same data give sd 2.57 with the bound at 40 and 5.81 with it at 80. A width the declared range chooses is not
    the data's, so the rebuild is passed over GRID_POSTERIOR_BOUND_DOMINATED and the route ends in a refusal.
    """
    P = S.strong_nonlinearity()
    result = route_uncertainty(rebuild=GridRebuildPolicy(P.table_builder()), **_inputs(P))
    assert result.decision is RouteDecision.REFUSED
    assert result.considered[-1]["reason"] == RouteReason.GRID_POSTERIOR_BOUND_DOMINATED.value
    assert "theta1" in result.considered[-1]["detail"]


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
    grid = route_uncertainty(grid=P.grid([np.linspace(0.6, 1.3, 61), np.linspace(1.4, 2.7, 61)]),
                              observations=P.observations, forward=P.forward)
    with pytest.raises(HybridUQError, match="predictive_table"):
        routed_predictive_uncertainty(grid, [PredictiveObservableSpec("y@1", UNIT)])


def test_a_result_cannot_claim_a_route_it_did_not_take():
    import dataclasses

    result = route_uncertainty(**_inputs(S.affine()))
    with pytest.raises(HybridUQError):
        dataclasses.replace(result, approximation_class=ApproximationClass.POSTERIOR_GRID)
    with pytest.raises(HybridUQError):
        dataclasses.replace(result, decision=RouteDecision.REFUSED)


# --- a rebuilt grid is the grid that was requested, row for row ---------------------------------------------------------
#
# The router reshapes a rebuilt table's log-likelihood onto the node layout it asked for and reads its faces by index.
# A builder that answers with any other table -- other coordinates, the same coordinates in another order, the same
# numbers under other parameter names -- must not be checked for containment, passed to V1 and certified as
# GRID_REBUILT_FROM_LOCAL_COVARIANCE. Each adversary below wraps the honest builder, so every table it returns is
# internally consistent and admissible; only its correspondence to the request is wrong.


def _permuted(table, order):
    import dataclasses

    return dataclasses.replace(table, points=table.points[order], values=table.values[order],
                               admissible_mask=table.admissible_mask[order],
                               admission_refs=tuple(table.admission_refs[i] for i in order),
                               rejection_reasons=tuple(table.rejection_reasons[i] for i in order))


def _adversaries(honest):
    import dataclasses

    def shifted_grid(points):
        # the same row count, every row evaluated and labelled at another coordinate
        return honest(np.asarray(points, dtype=float) + np.array([0.25, 0.125]))

    def rescaled_grid(points):
        # a cached table for another grid with exactly prod(nodes) rows
        return honest(np.asarray(points, dtype=float) * 1.1)

    def one_stale_row(points):
        # a single row that belongs to another coordinate, its values consistent with that coordinate
        points = np.array(points, dtype=float)
        points[len(points) // 2] += np.array([1.0e-3, 0.0])
        return honest(points)

    def reversed_rows(points):
        table = honest(points)
        return _permuted(table, np.arange(len(table.points))[::-1])

    def two_rows_swapped(points):
        table = honest(points)
        order = np.arange(len(table.points))
        order[[0, len(order) - 1]] = order[[len(order) - 1, 0]]
        return _permuted(table, order)

    def parameter_names_swapped(points):
        table = honest(points)
        return dataclasses.replace(table, parameter_names=tuple(reversed(table.parameter_names)))

    def parameter_names_renamed(points):
        table = honest(points)
        return dataclasses.replace(table, parameter_names=tuple(f"{n}_cached" for n in table.parameter_names))

    def one_row_short(points):
        return honest(list(points)[:-1])

    return {"shifted_grid": shifted_grid, "rescaled_grid": rescaled_grid, "one_stale_row": one_stale_row,
            "reversed_rows": reversed_rows, "two_rows_swapped": two_rows_swapped,
            "parameter_names_swapped": parameter_names_swapped, "parameter_names_renamed": parameter_names_renamed,
            "one_row_short": one_row_short}


_ADVERSARY_MESSAGES = {
    "shifted_grid": "not the requested grid", "rescaled_grid": "not the requested grid", "one_stale_row": r"1 row\(s\) differ",
    "reversed_rows": "not the requested grid", "two_rows_swapped": r"2 row\(s\) differ",
    "parameter_names_swapped": "requested over", "parameter_names_renamed": "requested over", "one_row_short": "were requested",
}


@pytest.mark.parametrize("adversary", sorted(_ADVERSARY_MESSAGES))
def test_a_rebuilt_table_that_is_not_the_requested_grid_is_never_certified(adversary):
    P = S.strong_nonlinearity()
    builder = _adversaries(P.table_builder())[adversary]
    with pytest.raises(HybridUQError, match=_ADVERSARY_MESSAGES[adversary]):
        route_uncertainty(rebuild=GridRebuildPolicy(builder), **_inputs(P))


def test_a_reordered_table_is_refused_even_though_its_rows_are_the_requested_rows():
    """Sorting would hide the attack: the refusal is about the order the router reads, not the set of rows."""
    P = S.strong_nonlinearity()
    honest = P.table_builder()
    seen = {}

    def reversed_rows(points):
        seen["requested"] = np.asarray(points, dtype=float)
        table = honest(points)
        return _permuted(table, np.arange(len(table.points))[::-1])

    with pytest.raises(HybridUQError, match="first at row 0"):
        route_uncertainty(rebuild=GridRebuildPolicy(reversed_rows), **_inputs(P))
    requested = seen["requested"]
    assert np.array_equal(np.unique(requested, axis=0), np.unique(requested[::-1], axis=0))


def test_an_honest_builder_still_rebuilds_and_the_certified_grid_is_the_last_grid_it_was_asked_for():
    # F1 until CORE-002: its rebuilt posterior spans both declared bounds and is no longer used
    P = S.bimodal_two_parameter()
    honest = P.table_builder()
    requests = []

    def recording(points):
        requests.append(np.asarray(points, dtype=float))
        return honest(points)

    result = route_uncertainty(rebuild=GridRebuildPolicy(recording), **_inputs(P))
    assert result.decision is RouteDecision.GRID_REBUILT_FROM_LOCAL_COVARIANCE and result.claim is RouteClaim.SUPPORTED
    assert result.grid.parameter_names == P.parameters.names
    assert np.array_equal(result.grid.points, requests[-1])
    mean, sd = _reference(P, [np.linspace(-3.0, 3.0, 1201), np.linspace(-2.0, 2.0, 801)])
    assert np.all(np.abs(np.asarray(result.mean) - mean) / sd < 0.05)
