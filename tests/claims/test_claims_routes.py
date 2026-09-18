"""CORE-6: route classification is computed from the pinned identities, never declared.

The classification is a planning-time prediction of what the executed consensus
decides. These tests hold the two to the same rule on every pinned pair, so the
prediction can never be more permissive than the authority.
"""

from __future__ import annotations

import itertools

import pytest

from engcore.claims import (
    RouteClass,
    assess_routes,
    classify_dependencies,
    pinned_dependencies,
)
from engcore.domains import SCIENTIFIC_ROUTE_DECLARATIONS
from engcore.mcp.capabilities import production_registry
from engcore.scientific.consensus import (
    CrossSolverConsensus,
    IndependenceDimension,
    IndependenceVerdict,
    RouteDependencies,
    SolveRoute,
)
from engcore.scientific.results.validation import ValidationLevel
from engcore.scientific.solvers.protocol import SolverIdentity


def _thresholds(gate_id: str):
    if gate_id == "electrical.dc.cross_solver":
        from engcore.domains.electrical.dc_consensus import DC_CONSENSUS_THRESHOLDS

        return DC_CONSENSUS_THRESHOLDS
    from engcore.domains.kinetics.cstr.validation import CSTR_GATE_THRESHOLDS

    return CSTR_GATE_THRESHOLDS


def _solve_route(route_id: str) -> SolveRoute:
    pin = SCIENTIFIC_ROUTE_DECLARATIONS[route_id]
    return SolveRoute(
        route_id=route_id,
        solver=SolverIdentity(pin["solver_id"], "0.1.0", pin.get("backend", "")),
        dependencies=RouteDependencies(identities={k: frozenset(v) for k, v in dict(pin["identities"]).items()}),
    )


_PAIRS = [
    (a, b)
    for a, b in itertools.combinations(sorted(SCIENTIFIC_ROUTE_DECLARATIONS), 2)
    if SCIENTIFIC_ROUTE_DECLARATIONS[a]["threshold_gate_id"] == SCIENTIFIC_ROUTE_DECLARATIONS[b]["threshold_gate_id"]
]


@pytest.mark.parametrize("pair", _PAIRS, ids=lambda pair: f"{pair[0]}~{pair[1]}")
def test_the_prediction_agrees_with_the_consensus_on_every_pinned_pair(pair) -> None:
    a, b = pair
    pin = SCIENTIFIC_ROUTE_DECLARATIONS[a]
    consensus = CrossSolverConsensus.over(
        consensus_id="prediction-check",
        routes=(_solve_route(a), _solve_route(b)),
        values={a: {"q": 1.0}, b: {"q": 1.0}},
        thresholds=_thresholds(pin["threshold_gate_id"]),
        tolerance_key=pin["tolerance_key"],
    )
    predicted, _ = classify_dependencies(pinned_dependencies(a).identities, pinned_dependencies(b).identities)
    assert consensus.routes_are_independent == (predicted is RouteClass.INDEPENDENT)
    assert (consensus.independence is IndependenceVerdict.NOT_INDEPENDENT) == (
        predicted in (RouteClass.ALIAS, RouteClass.SHARED_IMPLEMENTATION)
    )


def test_the_native_and_external_dc_routes_are_independent_sharing_only_the_problem() -> None:
    route_class, shared = classify_dependencies(
        pinned_dependencies("electrical.dc.native_mna").identities,
        pinned_dependencies("electrical.dc.external_simulator").identities,
    )
    assert route_class is RouteClass.INDEPENDENT and shared == ()


def test_two_numerical_methods_in_one_implementation_are_not_independent() -> None:
    route_class, shared = classify_dependencies(
        pinned_dependencies("kinetics.cstr.integration:BDF").identities,
        pinned_dependencies("kinetics.cstr.integration:Radau").identities,
    )
    assert route_class is RouteClass.SHARED_IMPLEMENTATION
    assert IndependenceDimension.IMPLEMENTATION in shared and IndependenceDimension.BACKEND in shared


def test_the_same_implementation_under_another_name_is_an_alias() -> None:
    """A re-export is one object: canonical identity sees through the spelling."""
    pin = SCIENTIFIC_ROUTE_DECLARATIONS["kinetics.cstr.integration:BDF"]
    respelled = {k: frozenset(v) for k, v in dict(pin["identities"]).items()}
    respelled["implementation"] = frozenset({"py:engcore.domains.kinetics.cstr:CSTRSolver"})
    alias = RouteDependencies(identities=respelled).canonical()
    route_class, _ = classify_dependencies(pinned_dependencies("kinetics.cstr.integration:BDF").identities, alias)
    assert route_class is RouteClass.ALIAS


def test_a_shared_backend_or_preprocessor_blocks_independence() -> None:
    base = pinned_dependencies("electrical.dc.native_mna").identities
    other = dict(pinned_dependencies("electrical.dc.external_simulator").identities)
    for dimension in (IndependenceDimension.BACKEND, IndependenceDimension.PREPROCESSING, IndependenceDimension.NUMERICAL_METHOD):
        shared = dict(other)
        shared[dimension] = base[dimension]
        route_class, dims = classify_dependencies(base, shared)
        assert route_class is RouteClass.PARTIALLY_INDEPENDENT and dimension in dims


def test_an_unpinned_route_is_unverified_and_establishes_nothing() -> None:
    assert pinned_dependencies("made.up.route").identities is None
    assert pinned_dependencies(None).identities is None


def test_production_routes_are_classified_without_trusting_their_declarations() -> None:
    registry = production_registry()
    et = {r.route_id: r for r in assess_routes(registry.get("system.electrothermal"), ())}
    external = et["electrical.dc.external_simulator"]
    assert external.route_class is RouteClass.INDEPENDENT
    assert external.could_establish is ValidationLevel.CROSS_SOLVER_VALIDATED
    assert external.is_validation is False  # two codes agreeing is verification, not validation
    assert external.attainable_here is False and external.active is False
    requested = {r.route_id: r for r in assess_routes(registry.get("system.electrothermal"), ("cross_solver_check.external_provider",))}
    assert requested["electrical.dc.external_simulator"].active is True
    analytic = et["thermal.lumped.series_recurrence"]
    assert analytic.could_establish is ValidationLevel.ANALYTICALLY_VERIFIED and analytic.is_validation is False
    t3 = {r.route_id: r for r in assess_routes(registry.get("benchmark.nafems_t3"), ())}
    oracle = t3["nafems.p18.t3.oracle"]
    assert oracle.route_class is RouteClass.BENCHMARK
    assert oracle.could_establish is ValidationLevel.BENCHMARK_VALIDATED and oracle.is_validation is True
    assert oracle.attainable_here is True
