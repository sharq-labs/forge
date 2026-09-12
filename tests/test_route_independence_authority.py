"""Independence is derived from canonical identity, never from names a caller supplies.

Sprint 3, Part B. ``test(consensus): reproduce false route independence`` recorded
the first block as strict xfails against ``CrossSolverConsensus`` and the DC
domain's ``dc_consensus`` at ``c0acdf6``: in every case the routes agree exactly,
so any level awarded rests entirely on the independence verdict -- and every one
of them earned ``CROSS_SOLVER_VALIDATED``, including the production entry point
handed one result under one solver twice.

    Independence must be derived from canonical implementation/dependency
    identity, not merely from names supplied by the caller.

The second block is the dimension matrix: what each kind of sharing is worth,
against routes declared and pinned for the test (see
``tests/route_declarations_for_tests.py``).
"""

from __future__ import annotations

import json

import pytest

from engcore.domains.electrical.dc import (
    DCCircuit,
    DCVoltageSource,
    ElectricalDCSolver,
    ElectricalNode,
    Resistor,
    solve_circuit,
)
from engcore.domains.electrical.dc_consensus import (
    DC_CONSENSUS_THRESHOLDS,
    dc_consensus,
    external_route,
    native_route,
)
from engcore.domains.kinetics.cstr.validation import integration_route
from engcore.scientific.consensus import (
    ComponentKind as K,
    CrossSolverConsensus,
    IndependenceDimension as D,
    IndependenceVerdict,
    RouteDependencies,
    SharedComponent as C,
    SolveRoute,
)
from engcore.scientific.errors import ScientificValidationError
from engcore.scientific.results.validation import ValidationLevel
from engcore.scientific.solvers.protocol import SolverIdentity
from engcore.scientific.units.quantity import Quantity
from tests.route_declarations_for_tests import (  # noqa: F401 - autouse fixture
    declare,
    dependencies,
    route,
    route_declarations_for_tests,
)

MNA = ElectricalDCSolver().identity
NGSPICE = SolverIdentity("engcore.electrical.dc.ngspice", "ngspice-44", backend="ngspice")
CSTR = SolverIdentity("kinetics.cstr.scipy_implicit_ivp", "0.1.0", backend="scipy.integrate.solve_ivp")
BDF_BACKEND = "scipy.integrate.solve_ivp:BDF"


def _over(*routes: SolveRoute) -> CrossSolverConsensus:
    return CrossSolverConsensus.over(
        consensus_id="route-independence",
        routes=routes,
        values={r.route_id: {"x": 1.0, "y": 2.0} for r in routes},
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


# ---- the B2 reproductions -------------------------------------------------------------
CASE_1 = (
    SolveRoute("route-a", MNA, frozenset({C(K.IMPLEMENTATION, "mna-impl-a")})),
    SolveRoute("route-b", MNA, frozenset({C(K.IMPLEMENTATION, "mna-impl-b")})),
)
CASE_2 = (
    SolveRoute("a", SolverIdentity("s.one", "1"), frozenset({C(K.LINEAR_ALGEBRA, "numpy.linalg:solve")})),
    SolveRoute("b", SolverIdentity("s.two", "1"), frozenset({C(K.LINEAR_ALGEBRA, "numpy.linalg.solve")})),
)
CASE_3 = (
    SolveRoute("a", SolverIdentity("wrapper.a", "1", backend=BDF_BACKEND), frozenset({C(K.RESIDUAL, "wrapper.a:rhs")})),
    SolveRoute("b", SolverIdentity("wrapper.b", "1", backend=BDF_BACKEND), frozenset({C(K.RESIDUAL, "wrapper.b:rhs")})),
)
CASE_5 = (
    SolveRoute("a", SolverIdentity("s.one", "1"), frozenset({C(K.LINEAR_ALGEBRA, "dense:lu")})),
    SolveRoute("b", SolverIdentity("s.two", "1"), frozenset({C(K.LINEAR_ALGEBRA, "sparse:cg")})),
)


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
    assert consensus.independence is IndependenceVerdict.UNDECLARED
    assert consensus.establishes is None
    assert consensus.to_check().establishes is None
    assert "declare no dependencies" in consensus.reason


def test_production_dc_consensus_one_result_under_one_solver_on_both_routes_earns_nothing():
    native = solve_circuit(_circuit(), run_id="ri-native")
    consensus = dc_consensus(
        native=native, native_solver=MNA, external=native, external_solver=MNA
    )
    assert consensus.comparison.agreed
    assert consensus.independence is IndependenceVerdict.UNVERIFIED
    assert consensus.establishes is None
    assert consensus.to_check().establishes is None
    assert "electrical.dc.external_simulator" in consensus.reason


def test_production_dc_consensus_refuses_a_native_result_presented_as_the_external_route():
    native = solve_circuit(_circuit(), run_id="ri-native")
    with pytest.raises(ScientificValidationError, match="provenance"):
        dc_consensus(
            native=native, native_solver=MNA, external=native, external_solver=NGSPICE
        )


def test_a_serialized_level_for_routes_named_apart_is_refused_on_the_way_back_in():
    payload = _over(*CASE_1).to_dict()
    payload["establishes"] = "cross_solver_validated"
    with pytest.raises(ScientificValidationError):
        CrossSolverConsensus.from_dict(payload)


# ---- B6: what each kind of sharing is worth ----------------------------------------------
def test_one_implementation_under_two_declared_routes_is_not_independent():
    shared = "ext:test:one-implementation"
    consensus = _over(
        route("a", implementation=shared), route("b", implementation=shared)
    )
    assert consensus.independence is IndependenceVerdict.NOT_INDEPENDENT
    assert consensus.establishes is None
    assert (D.IMPLEMENTATION, shared) in consensus.shared_dependencies


def test_one_implementation_under_two_import_paths_is_one_identity():
    """An alias is not a second implementation: both spellings resolve to the
    class's own module and qualified name, so the routes share it."""
    consensus = _over(
        route("a", implementation="py:engcore.domains.electrical.dc.solver:ElectricalDCSolver"),
        route("b", implementation="py:engcore.domains.electrical.dc:ElectricalDCSolver"),
    )
    assert consensus.independence is IndependenceVerdict.NOT_INDEPENDENT
    assert consensus.establishes is None
    assert (
        D.IMPLEMENTATION,
        "py:engcore.domains.electrical.dc.solver:ElectricalDCSolver",
    ) in consensus.shared_dependencies


def test_two_implementations_over_one_backend_are_only_partially_independent():
    consensus = _over(route("a", backend="ext:one-library"), route("b", backend="ext:one-library"))
    assert consensus.independence is IndependenceVerdict.PARTIALLY_INDEPENDENT
    assert not consensus.routes_are_independent
    assert consensus.establishes is None


def test_two_implementations_over_one_preprocessing_step_are_only_partially_independent():
    consensus = _over(
        route("a", preprocessing="ext:one-assembly"), route("b", preprocessing="ext:one-assembly")
    )
    assert consensus.independence is IndependenceVerdict.PARTIALLY_INDEPENDENT
    assert consensus.establishes is None


def test_sharing_only_the_problem_declaration_is_partial_independence_and_earns():
    """The production shape: two solvers asked one question. Partial, and enough."""
    consensus = _over(route("a"), route("b"))
    assert consensus.independence is IndependenceVerdict.PARTIALLY_INDEPENDENT
    assert consensus.shared_dimensions == (D.PROBLEM_DECLARATION,)
    assert consensus.routes_are_independent
    assert consensus.establishes is ValidationLevel.CROSS_SOLVER_VALIDATED
    assert consensus.to_check().earns_its_level


def test_sharing_nothing_at_all_is_full_independence():
    consensus = _over(
        route("a", problem_declaration="ext:test:problem-a"),
        route("b", problem_declaration="ext:test:problem-b"),
    )
    assert consensus.independence is IndependenceVerdict.FULLY_INDEPENDENT
    assert consensus.shared_dependencies == ()
    assert consensus.establishes is ValidationLevel.CROSS_SOLVER_VALIDATED


def test_a_route_whose_id_the_domain_layer_does_not_declare_earns_nothing():
    undeclared = SolveRoute("nobody-declares-this", MNA, dependencies=dependencies("x"))
    consensus = _over(route("a"), undeclared)
    assert consensus.independence is IndependenceVerdict.UNVERIFIED
    assert consensus.establishes is None
    assert "is not a route the domain layer declares" in consensus.reason


def test_a_declaration_edited_after_it_was_pinned_earns_nothing():
    declared = route("a")
    edited = SolveRoute(
        declared.route_id,
        declared.solver,
        dependencies=dependencies("a", numerical_method="ext:something-else"),
    )
    consensus = _over(edited, route("b"))
    assert consensus.independence is IndependenceVerdict.UNVERIFIED
    assert "the domain layer pins" in consensus.reason
    assert consensus.establishes is None


def test_a_route_bound_to_another_solver_than_its_declaration_earns_nothing():
    """Only the solver binding can catch this one: the backend matches, so a
    route id says one implementation ran and the identity says another did."""
    declared = route("a")
    impostor = SolveRoute(
        declared.route_id,
        SolverIdentity("another.solver", "1.0", backend=declared.solver.backend),
        dependencies=declared.dependencies,
    )
    consensus = _over(impostor, route("b"))
    assert consensus.independence is IndependenceVerdict.UNVERIFIED
    assert "another.solver" in consensus.reason
    assert consensus.establishes is None


def test_a_route_bound_to_another_backend_than_its_declaration_earns_nothing():
    """And only the backend binding can catch this one."""
    declared = route("a")
    impostor = SolveRoute(
        declared.route_id,
        SolverIdentity(declared.solver.solver_id, "1.0", backend="another-provider"),
        dependencies=declared.dependencies,
    )
    consensus = _over(impostor, route("b"))
    assert consensus.independence is IndependenceVerdict.UNVERIFIED
    assert "another-provider" in consensus.reason
    assert consensus.establishes is None


def test_a_dependency_set_missing_a_dimension_is_refused():
    with pytest.raises(ScientificValidationError, match="declare no identity for"):
        RouteDependencies({D.IMPLEMENTATION: {"ext:only-this"}})


def test_an_identity_with_no_scheme_is_refused():
    with pytest.raises(ScientificValidationError, match="no recognised scheme"):
        route("a", implementation="numpy.linalg.solve").dependencies.digest


# ---- the production declarations ---------------------------------------------------------
def test_the_two_dc_routes_are_independent_except_in_the_problem_they_share():
    consensus = _over(native_route(MNA), external_route(NGSPICE))
    assert consensus.independence is IndependenceVerdict.PARTIALLY_INDEPENDENT
    assert consensus.shared_dimensions == (D.PROBLEM_DECLARATION,)
    assert consensus.routes_are_independent
    assert consensus.establishes is ValidationLevel.CROSS_SOLVER_VALIDATED


def test_the_two_integration_routes_share_everything_but_the_method():
    consensus = _over(integration_route("BDF", CSTR), integration_route("Radau", CSTR))
    assert consensus.independence is IndependenceVerdict.NOT_INDEPENDENT
    assert consensus.establishes is None
    shared = {dimension for dimension, _ in consensus.shared_dependencies}
    assert shared == {D.PROBLEM_DECLARATION, D.PREPROCESSING, D.IMPLEMENTATION, D.BACKEND}
    assert D.NUMERICAL_METHOD not in shared


# ---- serialization ---------------------------------------------------------------------------
def test_the_record_carries_its_dependencies_and_is_verified_again_on_the_way_in():
    consensus = _over(route("a"), route("b"))
    payload = json.loads(json.dumps(consensus.to_dict()))
    assert payload["independence"] == "partially_independent"
    assert payload["shared_dependencies"] == ["problem_declaration:ext:test:one-problem"]
    assert payload["unverified_routes"] == []
    restored = CrossSolverConsensus.from_dict(payload)
    assert restored == consensus
    assert restored.establishes is ValidationLevel.CROSS_SOLVER_VALIDATED


def test_a_tampered_serialized_dependency_cannot_keep_its_level():
    consensus = _over(route("a"), route("b"))
    payload = json.loads(json.dumps(consensus.to_dict()))
    payload["routes"][0]["dependencies"]["identities"]["implementation"] = ["ext:something-else"]
    with pytest.raises(ScientificValidationError, match="may not assert one"):
        CrossSolverConsensus.from_dict(payload)


def test_a_payload_whose_dependencies_are_removed_cannot_keep_its_level():
    consensus = _over(route("a"), route("b"))
    payload = json.loads(json.dumps(consensus.to_dict()))
    payload["routes"][0]["dependencies"] = None
    with pytest.raises(ScientificValidationError, match="may not assert one"):
        CrossSolverConsensus.from_dict(payload)
