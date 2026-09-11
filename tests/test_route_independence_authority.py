"""Independence is derived from canonical identity, never from names a caller supplies.

Sprint 3, Part B. Reproductions written against ``CrossSolverConsensus`` and the
DC domain's ``dc_consensus`` at ``3a4f063``, before any fix. In every case below
the routes agree exactly, so any level awarded rests entirely on the independence
verdict -- and at that commit every one of them earned ``CROSS_SOLVER_VALIDATED``,
including the production entry point handed one result under one solver twice.

    Independence must be derived from canonical implementation/dependency
    identity, not merely from names supplied by the caller.
"""

from __future__ import annotations

import pytest

from engcore.domains.electrical.dc import (
    DCCircuit,
    DCVoltageSource,
    ElectricalNode,
    Resistor,
    solve_circuit,
)
from engcore.domains.electrical.dc.solver import ElectricalDCSolver
from engcore.domains.electrical.dc_consensus import DC_CONSENSUS_THRESHOLDS, dc_consensus
from engcore.scientific.consensus import (
    ComponentKind as K,
    CrossSolverConsensus,
    SharedComponent as C,
    SolveRoute,
)
from engcore.scientific.errors import ScientificValidationError
from engcore.scientific.solvers.protocol import SolverIdentity
from engcore.scientific.units.quantity import Quantity

#: Reproduced at ``3a4f063``. Strict, so the fix has to remove these marks.
REPRODUCED = pytest.mark.xfail(
    strict=True,
    reason="Sprint 3 B2 reproduction: caller-declared names earned CROSS_SOLVER_VALIDATED at 3a4f063",
)

MNA = ElectricalDCSolver().identity
BDF = "scipy.integrate.solve_ivp:BDF"


def _over(*routes: SolveRoute) -> CrossSolverConsensus:
    return CrossSolverConsensus.over(
        consensus_id="route-independence",
        routes=routes,
        values={route.route_id: {"x": 1.0, "y": 2.0} for route in routes},
        thresholds=DC_CONSENSUS_THRESHOLDS,
        tolerance_key="agreement_rel_tol",
        required_outputs=("x", "y"),
    )


def _circuit() -> DCCircuit:
    gnd = ElectricalNode("gnd", is_reference=True)
    return DCCircuit(
        circuit_id="divider",
        nodes=(gnd, ElectricalNode("top"), ElectricalNode("mid")),
        resistors=(
            Resistor("R1", "top", "mid", Quantity(1.0, "kohm")),
            Resistor("R2", "mid", "gnd", Quantity(3.0, "kohm")),
        ),
        voltage_sources=(DCVoltageSource("V1", "top", "gnd", Quantity(12.0, "volt")),),
    )


CASE_1 = (
    SolveRoute("route-a", MNA, frozenset({C(K.IMPLEMENTATION, "mna-impl-a")})),
    SolveRoute("route-b", MNA, frozenset({C(K.IMPLEMENTATION, "mna-impl-b")})),
)
CASE_2 = (
    SolveRoute("a", SolverIdentity("s.one", "1"), frozenset({C(K.LINEAR_ALGEBRA, "numpy.linalg:solve")})),
    SolveRoute("b", SolverIdentity("s.two", "1"), frozenset({C(K.LINEAR_ALGEBRA, "numpy.linalg.solve")})),
)
CASE_3 = (
    SolveRoute("a", SolverIdentity("wrapper.a", "1", backend=BDF), frozenset({C(K.RESIDUAL, "wrapper.a:rhs")})),
    SolveRoute("b", SolverIdentity("wrapper.b", "1", backend=BDF), frozenset({C(K.RESIDUAL, "wrapper.b:rhs")})),
)
CASE_5 = (
    SolveRoute("a", SolverIdentity("s.one", "1"), frozenset({C(K.LINEAR_ALGEBRA, "dense:lu")})),
    SolveRoute("b", SolverIdentity("s.two", "1"), frozenset({C(K.LINEAR_ALGEBRA, "sparse:cg")})),
)


@REPRODUCED
@pytest.mark.parametrize(
    "routes",
    [
        pytest.param(CASE_1, id="1-one-solver-identity-two-route-names"),
        pytest.param(CASE_2, id="2-one-function-under-two-spellings"),
        pytest.param(CASE_3, id="3-one-backend-behind-two-wrappers"),
        pytest.param(CASE_5, id="5-disjoint-labels-nothing-verifiable"),
    ],
)
def test_caller_declared_names_do_not_earn_cross_solver_validation(routes):
    consensus = _over(*routes)
    assert consensus.comparison.agreed
    assert consensus.establishes is None
    assert consensus.to_check().establishes is None


@REPRODUCED
def test_production_dc_consensus_one_result_under_one_solver_on_both_routes_earns_nothing():
    native = solve_circuit(_circuit(), run_id="ri-native")
    consensus = dc_consensus(
        native=native, native_solver=MNA, external=native, external_solver=MNA
    )
    assert consensus.comparison.agreed
    assert consensus.establishes is None
    assert consensus.to_check().establishes is None


@REPRODUCED
def test_production_dc_consensus_refuses_a_native_result_presented_as_the_external_route():
    native = solve_circuit(_circuit(), run_id="ri-native")
    claimed_external = SolverIdentity("engcore.electrical.dc.ngspice", "ngspice-44", backend="ngspice")
    with pytest.raises(ScientificValidationError, match="provenance"):
        dc_consensus(
            native=native, native_solver=MNA, external=native, external_solver=claimed_external
        )


@REPRODUCED
def test_a_serialized_level_for_routes_named_apart_is_refused_on_the_way_back_in():
    payload = _over(*CASE_1).to_dict()
    payload["establishes"] = "cross_solver_validated"
    with pytest.raises(ScientificValidationError):
        CrossSolverConsensus.from_dict(payload)
