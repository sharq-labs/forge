"""IND-02: a consensus level is bound to executed results, never to a mapping of numbers.

The audit (probe ``agentD/ind2.py``) showed routes were labels and values were
unbound to any execution:

* ``CrossSolverConsensus.over`` with identical fabricated numbers under the two
  production DC route ids established ``CROSS_SOLVER_VALIDATED`` -- nothing ran;
* ``dc_consensus`` duck-typed ``getattr(result, "provenance").solvers``, so the
  native ``solve_circuit`` result's values inside a ``SimpleNamespace`` whose
  provenance claimed the external solver established the level.

The rule these tests pin: the level is available only through
:meth:`CrossSolverConsensus.from_results`, which takes type-checked
``ScientificResult`` objects, requires each route's result to name that route's
solver (id, version and backend) in its own record, derives the compared numbers
from the results, and binds each route to its result id, run id, solver and a
digest of its numbers. Results that are not distinct executions earn nothing.
A plain mapping of numbers (``over``, or the constructor) can never award it,
and a serialized binding is re-verified on the way back in.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from engcore.domains.electrical import dc_consensus as dcc
from engcore.domains.electrical.dc import (
    DCCircuit,
    DCVoltageSource,
    ElectricalDCSolver,
    ElectricalNode,
    Resistor,
    solve_circuit,
)
from engcore.scientific.consensus import CrossSolverConsensus
from engcore.scientific.errors import ScientificValidationError
from engcore.scientific.results.provenance import ProvenanceRecord
from engcore.scientific.results.result import ScientificResult
from engcore.scientific.results.validation import ValidationLevel
from engcore.scientific.solvers.protocol import SolverIdentity
from engcore.scientific.units.quantity import Quantity
from tests.route_declarations_for_tests import (  # noqa: F401 - autouse fixture
    route,
    route_declarations_for_tests,
)

MNA = ElectricalDCSolver().identity
EXT = SolverIdentity("engcore.electrical.dc.ngspice", "fake-9.9", backend="ngspice")
THRESHOLDS = dcc.DC_CONSENSUS_THRESHOLDS
KEY = "agreement_rel_tol"


def _circuit() -> DCCircuit:
    return DCCircuit(
        circuit_id="c",
        nodes=(ElectricalNode("n0"), ElectricalNode("n1"), ElectricalNode("gnd", is_reference=True)),
        resistors=(
            Resistor("R1", "n0", "n1", Quantity(10.0, "ohm")),
            Resistor("R2", "n1", "gnd", Quantity(20.0, "ohm")),
        ),
        voltage_sources=(DCVoltageSource("V1", "n0", "gnd", Quantity(12.0, "volt")),),
    )


def _result(solver: SolverIdentity, values: dict[str, float], *, result_id: str, run_id: str,
            provenance_solvers=None) -> ScientificResult:
    return ScientificResult(
        result_id=result_id,
        values={name: Quantity(value, "dimensionless") for name, value in values.items()},
        provenance=ProvenanceRecord(
            run_id=run_id,
            solvers=tuple(provenance_solvers) if provenance_solvers is not None else (solver.key,),
        ),
        solver=solver,
    )


def _bound(a, b, ra, rb, required=("x", "y")):
    return CrossSolverConsensus.from_results(
        consensus_id="bound",
        routes=(a, b),
        results={a.route_id: ra, b.route_id: rb},
        thresholds=THRESHOLDS,
        tolerance_key=KEY,
        required_outputs=required,
    )


def _pair(**overrides):
    a, b = route("a"), route("b")
    ra = _result(a.solver, {"x": 1.0, "y": 2.0}, result_id="ra", run_id="run-a")
    rb = _result(b.solver, {"x": 1.0, "y": 2.0}, result_id="rb", run_id="run-b")
    return a, b, ra, rb


# ---- the probes --------------------------------------------------------------------------
def test_probe_identical_fabricated_numbers_under_both_production_route_ids_earn_nothing():
    routes = (dcc.native_route(MNA), dcc.external_route(EXT))
    values = {"node_voltage:n1": 3.3, "resistor_current:R1": 0.001}
    consensus = CrossSolverConsensus.over(
        consensus_id="x", routes=routes,
        values={dcc.NATIVE_ROUTE_ID: values, dcc.EXTERNAL_ROUTE_ID: dict(values)},
        thresholds=THRESHOLDS, tolerance_key=KEY, required_outputs=tuple(values),
    )
    assert consensus.routes_are_independent and consensus.comparison.agreed
    assert consensus.establishes is None
    assert consensus.execution_binding_gap is not None
    assert "executed results" in consensus.reason


def test_probe_a_duck_typed_external_result_is_refused_by_the_dc_entry_point():
    native = solve_circuit(_circuit(), run_id="n1")
    fake = SimpleNamespace(
        values=native.values,
        provenance=SimpleNamespace(solvers=((EXT.solver_id, EXT.version),)),
    )
    with pytest.raises(ScientificValidationError, match="ScientificResult"):
        dcc.dc_consensus(native=native, native_solver=MNA, external=fake, external_solver=EXT)


def test_a_plain_values_record_built_by_the_constructor_earns_nothing():
    a, b, ra, rb = _pair()
    earned = _bound(a, b, ra, rb)
    assert earned.establishes is ValidationLevel.CROSS_SOLVER_VALIDATED
    rebuilt = CrossSolverConsensus(
        consensus_id=earned.consensus_id, routes=earned.routes, comparison=earned.comparison,
        thresholds=earned.thresholds, required_outputs=earned.required_outputs,
        reported_outputs=earned.reported_outputs, tolerance_key=earned.tolerance_key,
        reported_values=earned.reported_values,
    )
    assert rebuilt.establishes is None


# ---- from_results: what it refuses ----------------------------------------------------------
def test_a_non_result_is_refused():
    a, b, ra, _ = _pair()
    with pytest.raises(ScientificValidationError, match="ScientificResult"):
        _bound(a, b, ra, SimpleNamespace(values=ra.values, provenance=ra.provenance))


def test_every_route_needs_exactly_one_result():
    a, b, ra, rb = _pair()
    with pytest.raises(ScientificValidationError, match="no result"):
        CrossSolverConsensus.from_results(
            consensus_id="c", routes=(a, b), results={"a": ra},
            thresholds=THRESHOLDS, tolerance_key=KEY, required_outputs=("x",),
        )
    with pytest.raises(ScientificValidationError, match="undeclared"):
        CrossSolverConsensus.from_results(
            consensus_id="c", routes=(a, b), results={"a": ra, "b": rb, "ghost": rb},
            thresholds=THRESHOLDS, tolerance_key=KEY, required_outputs=("x",),
        )


def test_a_result_whose_provenance_does_not_name_the_routes_solver_is_refused():
    a, b, ra, _ = _pair()
    other = SolverIdentity("solver.other", "1.0", backend="b")
    rb = _result(other, {"x": 1.0, "y": 2.0}, result_id="rb", run_id="run-b")
    with pytest.raises(ScientificValidationError, match="solver"):
        _bound(a, b, ra, rb)


def test_a_result_under_another_version_of_the_routes_solver_is_refused():
    a, b, ra, _ = _pair()
    older = SolverIdentity(b.solver.solver_id, "0.9", backend=b.solver.backend)
    rb = _result(older, {"x": 1.0, "y": 2.0}, result_id="rb", run_id="run-b")
    with pytest.raises(ScientificValidationError, match="0.9"):
        _bound(a, b, ra, rb)


def test_a_result_under_another_backend_is_refused():
    a, b, ra, _ = _pair()
    swapped = SolverIdentity(b.solver.solver_id, b.solver.version, backend="a")
    rb = _result(swapped, {"x": 1.0, "y": 2.0}, result_id="rb", run_id="run-b")
    with pytest.raises(ScientificValidationError, match="backend"):
        _bound(a, b, ra, rb)


def test_one_result_presented_for_both_routes_earns_nothing():
    shared = SolverIdentity("solver.shared", "1.0", backend="shared")
    a, b = route("a", solver=shared), route("b", solver=shared)
    both = _result(shared, {"x": 1.0, "y": 2.0}, result_id="r", run_id="run")
    consensus = CrossSolverConsensus.from_results(
        consensus_id="same", routes=(a, b), results={"a": both, "b": both},
        thresholds=THRESHOLDS, tolerance_key=KEY, required_outputs=("x", "y"),
    )
    assert consensus.routes_are_independent and consensus.comparison.agreed
    assert consensus.establishes is None
    assert "distinct" in consensus.execution_binding_gap


def test_two_results_from_one_run_are_not_two_executions():
    a, b = route("a"), route("b")
    ra = _result(a.solver, {"x": 1.0, "y": 2.0}, result_id="ra", run_id="one-run")
    rb = _result(b.solver, {"x": 1.0, "y": 2.0}, result_id="rb", run_id="one-run")
    consensus = _bound(a, b, ra, rb)
    assert consensus.comparison.agreed
    assert consensus.establishes is None
    assert "run" in consensus.execution_binding_gap


def test_two_results_under_one_result_id_are_not_two_executions():
    a, b = route("a"), route("b")
    ra = _result(a.solver, {"x": 1.0, "y": 2.0}, result_id="same", run_id="run-a")
    rb = _result(b.solver, {"x": 1.0, "y": 2.0}, result_id="same", run_id="run-b")
    consensus = _bound(a, b, ra, rb)
    assert consensus.establishes is None
    assert "result" in consensus.execution_binding_gap


def test_the_compared_numbers_are_read_from_the_results():
    a, b, ra, rb = _pair()
    consensus = _bound(a, b, ra, rb)
    assert dict(consensus.reported_values["a"]) == {"x": 1.0, "y": 2.0}
    rb2 = _result(b.solver, {"x": 1.5, "y": 2.0}, result_id="rb", run_id="run-b")
    disagreeing = _bound(a, b, ra, rb2)
    assert not disagreeing.comparison.agreed
    assert disagreeing.establishes is None


# ---- serialization: the binding is re-verified -----------------------------------------------
def test_a_bound_record_keeps_its_level_through_a_round_trip():
    a, b, ra, rb = _pair()
    payload = json.loads(json.dumps(_bound(a, b, ra, rb).to_dict()))
    assert set(payload["execution_bindings"]) == {"a", "b"}
    assert CrossSolverConsensus.from_dict(payload).establishes is ValidationLevel.CROSS_SOLVER_VALIDATED


@pytest.mark.parametrize(
    "tamper",
    [
        pytest.param(lambda p: p.pop("execution_bindings"), id="binding-removed"),
        pytest.param(lambda p: p["execution_bindings"]["b"].update(run_id="run-a"), id="one-run"),
        pytest.param(lambda p: p["execution_bindings"]["b"].update(result_id="ra"), id="one-result"),
        pytest.param(lambda p: p["execution_bindings"]["b"]["solver"].update(version="0.0"), id="version"),
        pytest.param(lambda p: p["execution_bindings"]["b"].update(values_digest="0" * 64), id="numbers"),
        pytest.param(lambda p: p["execution_bindings"].pop("b"), id="route-unbound"),
    ],
)
def test_a_tampered_binding_cannot_keep_the_level(tamper):
    a, b, ra, rb = _pair()
    payload = json.loads(json.dumps(_bound(a, b, ra, rb).to_dict()))
    tamper(payload)
    with pytest.raises(ScientificValidationError, match="may not assert"):
        CrossSolverConsensus.from_dict(payload)
    payload["establishes"] = None
    assert CrossSolverConsensus.from_dict(payload).establishes is None


def test_changed_numbers_under_an_intact_binding_cannot_keep_the_level():
    a, b, ra, rb = _pair()
    payload = json.loads(json.dumps(_bound(a, b, ra, rb).to_dict()))
    payload["reported_values"]["b"]["x"] = 1.0 + 1e-12
    payload["comparison"] = CrossSolverConsensus.over(
        consensus_id="bound", routes=(a, b),
        values={"a": payload["reported_values"]["a"], "b": payload["reported_values"]["b"]},
        thresholds=THRESHOLDS, tolerance_key=KEY, required_outputs=("x", "y"),
    ).comparison.to_dict()
    with pytest.raises(ScientificValidationError, match="may not assert"):
        CrossSolverConsensus.from_dict(payload)


# ---- the DC entry point ---------------------------------------------------------------------
def test_dc_consensus_binds_the_real_native_result():
    native = solve_circuit(_circuit(), run_id="native-run")
    external = ScientificResult(
        result_id="external-run",
        values=native.values,
        provenance=ProvenanceRecord(run_id="external-run", solvers=(EXT.key,)),
        solver=EXT,
    )
    consensus = dcc.dc_consensus(native=native, native_solver=MNA, external=external, external_solver=EXT)
    binding = consensus.to_dict()["execution_bindings"]
    assert binding[dcc.NATIVE_ROUTE_ID]["run_id"] == "native-run"
    assert binding[dcc.EXTERNAL_ROUTE_ID]["solver"]["backend"] == "ngspice"
    assert consensus.execution_binding_gap is None
    assert consensus.establishes is ValidationLevel.CROSS_SOLVER_VALIDATED


def test_dc_consensus_refuses_an_identity_the_result_does_not_carry():
    native = solve_circuit(_circuit(), run_id="native-run")
    external = ScientificResult(
        result_id="external-run", values=native.values,
        provenance=ProvenanceRecord(run_id="external-run", solvers=(EXT.key,)), solver=EXT,
    )
    renamed = SolverIdentity(EXT.solver_id, EXT.version, backend="another-simulator")
    with pytest.raises(ScientificValidationError):
        dcc.dc_consensus(native=native, native_solver=MNA, external=external, external_solver=renamed)
