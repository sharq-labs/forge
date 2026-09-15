"""Regression coverage for trust-boundary findings 5-8."""

from __future__ import annotations

import math

import pytest

import hybrid_synthetic as S
from engcore.hybrid_uq import (
    HybridUQResult,
    MultistartPolicy,
    RouteClaim,
    RouteDecision,
    local_gaussian_posterior,
)
from engcore.scientific.solvers.protocol import SolverIdentity
from engcore.scientific.solvers.registry import SolverDefinition
from engcore.scientific.units.quantity import Quantity


def test_route_diagnostics_are_transitively_immutable() -> None:
    problem = S.affine()
    posterior = local_gaussian_posterior(
        problem.calibrate(),
        problem.observations,
        problem.forward,
        multistart=MultistartPolicy(),
    )
    diagnostics = posterior.diagnostics
    before = diagnostics.to_dict()
    digest = diagnostics.digest

    with pytest.raises(TypeError, match="immutable"):
        diagnostics.thresholds["nonlinearity_refuse"] = 999.0
    assert diagnostics.multistart
    with pytest.raises(TypeError, match="immutable"):
        diagnostics.multistart[0]["objective"] = 999.0

    assert diagnostics.to_dict() == before
    assert diagnostics.digest == digest


def test_hybrid_result_freezes_grid_summary_and_considered_recursively() -> None:
    result = HybridUQResult(
        decision=RouteDecision.REFUSED,
        approximation_class=None,
        claim=RouteClaim.REFUSED,
        parameter_names=(),
        coordinates="none",
        mean=None,
        covariance=None,
        local_posterior=None,
        grid_summary={"route": "test", "nested": {"points": [1, 2]}},
        considered=({"route": "local", "detail": "refused"},),
        identifiability=None,
    )
    before = result.to_dict()
    digest = result.digest

    with pytest.raises(TypeError, match="immutable"):
        result.grid_summary["route"] = "tampered"
    with pytest.raises(TypeError, match="immutable"):
        result.grid_summary["nested"]["points"] = [3]
    with pytest.raises(TypeError, match="immutable"):
        result.considered[0]["detail"] = "tampered"

    assert result.to_dict() == before
    assert result.digest == digest


def test_calibration_residuals_survive_serialization_and_spec_is_immutable() -> None:
    problem = S.affine()
    calibration = problem.calibrate()
    payload = calibration.to_dict()

    assert calibration.residuals
    assert len(calibration.residuals) == len(problem.observations.observations)
    assert all(math.isfinite(value) for value in calibration.residuals)
    assert payload["residuals"] == list(calibration.residuals)

    with pytest.raises(TypeError, match="immutable"):
        calibration.spec.fixed["tamper"] = Quantity(1.0, "dimensionless")
    name = next(iter(calibration.spec.initial_point))
    with pytest.raises(TypeError, match="immutable"):
        calibration.spec.initial_point[name] = Quantity(
            999.0,
            calibration.spec.initial_point[name].units,
        )


def test_registry_refuses_a_session_whose_freshness_cannot_be_tracked() -> None:
    class NonWeakrefableSolver:
        __slots__ = ()

        @property
        def identity(self) -> SolverIdentity:
            return SolverIdentity("nonweak", "1")

    definition = SolverDefinition(NonWeakrefableSolver, NonWeakrefableSolver())
    with pytest.raises(TypeError, match="freshness cannot be proven"):
        definition.new_session()
