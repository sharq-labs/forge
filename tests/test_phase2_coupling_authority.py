"""Phase 2 BR8 -- one coupling authority; the electrothermal loop as runtime participants.

* ``MultiphysicsRuntime`` is the one declared coupling authority; every other
  loop is declared with its status, and the electrothermal fixed point is
  NOT_MIGRATED with its remaining work.
* The electrothermal composition builds as a runtime plan (``runtime_adapter``)
  whose outcome, iteration count and outputs must match the native loop
  (parity), and a relaxed plan is refused because the two relax differently.
* Steady participants may defer their initial outputs, only where a serial
  sweep overwrites them before they are read.
* No relaxation now delivers the transfer exactly.
* Native provenance no longer claims "no relaxation" for a relaxed run.

NOT RUN (Phase 2 build phase): docs/work/DEFERRED_VALIDATION.md, DV-48..DV-50.
"""

from __future__ import annotations

import hashlib
import importlib

import numpy as np
import pytest

from engcore.data import BulkDataResolver, InMemoryBulkStore
from engcore.domains.electrical import material as mat
from engcore.domains.thermal_models import lumped as lump
from engcore.execution.multiphysics import (
    AdvanceResult, CallbackParticipant, InitializationResult, MultiphysicsRuntime,
)
from engcore.execution.multiphysics.authority import (
    COUPLING_PATHS, CouplingPathStatus, coupling_authority, fixed_point_outcome,
)
from engcore.execution.multiphysics.concurrency import ConcurrentAdvancePolicy
from engcore.execution.multiphysics.participant import RuntimeCheckpoint
from engcore.execution.multiphysics.relaxation import RelaxationController
from engcore.execution.multiphysics.runtime import CouplingRunOutcome, assess_run_outcome
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.multiphysics import (
    CheckpointRecord, ConvergenceCriterion, CouplingEdge, CouplingPlan, CouplingScheme, IterationSemantics,
    ParticipantSpec, PhysicsGraph, PortDefinition, PortDirection, PortKind, PortRef, RelaxationPolicy, TimePolicy,
)
from engcore.scientific.results.uncertainty import Uncertainty
from engcore.scientific.units.quantity import Quantity
from engcore.systems.electrothermal import coupled as cp
from engcore.systems.electrothermal.runtime_adapter import (
    compare_with_native, run_through_runtime, runtime_equivalent,
)

KELVIN = "kelvin"
UNKNOWN = Uncertainty.unknown("test output uncertainty not quantified")


# ---- the declared authority ------------------------------------------------------------------------------


def test_exactly_one_coupling_authority_is_declared_and_it_is_the_runtime():
    assert coupling_authority().module == "engcore.execution.multiphysics.runtime"


def test_every_declared_coupling_path_names_a_module_that_exists():
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1]
    for path in COUPLING_PATHS:
        if path.module.startswith("engcore."):
            importlib.import_module(path.module)
        else:  # a provider package outside src (forge_precice): it exists in the repository
            assert any(root.glob(f"providers/*/{path.module}/__init__.py")), path.module


def test_the_electrothermal_loop_is_declared_not_migrated_with_its_remaining_work():
    path = next(p for p in COUPLING_PATHS if p.path_id == "electrothermal_fixed_point")
    assert path.status is CouplingPathStatus.NOT_MIGRATED
    assert "parity" in path.remaining and "relaxation" in path.remaining


@pytest.mark.parametrize("token, expected", [
    ("criterion_met", CouplingRunOutcome.CONVERGED),
    (cp.CouplingOutcome.ITERATION_LIMIT_REACHED, CouplingRunOutcome.NOT_COMPLETED),
    (cp.CouplingOutcome.TRANSFER_REFUSED, CouplingRunOutcome.NOT_COMPLETED),
])
def test_fixed_point_outcomes_read_in_the_runtime_vocabulary(token, expected):
    assert fixed_point_outcome(token) is expected


def test_every_fixed_point_outcome_member_is_classified():
    for member in cp.CouplingOutcome:
        fixed_point_outcome(member)


def test_an_unknown_fixed_point_outcome_is_refused():
    with pytest.raises(InvalidScientificProblem):
        fixed_point_outcome("diverged_probably")


# ---- the electrothermal composition on the runtime: parity -------------------------------------------------


def _conductor(cid, r_ref, alpha, t_ref=293.15):
    return mat.TemperatureDependentConductor(
        component_id=cid, reference_resistance=Quantity(r_ref, "ohm"),
        temperature_coefficient=Quantity(alpha, "1/kelvin"), reference_temperature=Quantity(t_ref, KELVIN))


def _body(cid, capacity, conductance, duration=120.0):
    return lump.ThermalBody(
        body_id=cid, heat_capacity=Quantity(capacity, "joule/kelvin"),
        ambient_conductance=Quantity(conductance, "watt/kelvin"), ambient_temperature=Quantity(300.0, KELVIN),
        initial_temperature=Quantity(300.0, KELVIN), duration=Quantity(duration, "second"))


NOMINAL = cp.CoupledElectroThermalSystem(
    stages=(cp.CoupledStage(_conductor("R1", 10.0, 0.00393), _body("R1", 2.5, 0.05)),), source_voltage=Quantity(5.0, "volt"))
TWO_STAGE = cp.CoupledElectroThermalSystem(
    stages=(cp.CoupledStage(_conductor("R1", 10.0, 0.00393), _body("R1", 2.5, 0.05)),
            cp.CoupledStage(_conductor("R2", 20.0, 0.00060), _body("R2", 5.0, 0.02))),
    source_voltage=Quantity(12.0, "volt"))


def _plan(system, budget=50, relaxation=None):
    problems = cp.coupled_problems(system, {s.component_id: s.conductor.reference_resistance for s in system.stages})
    dependencies = cp.coupled_dependencies(system, problems, temperature_metric=lump.TEMPERATURE_METRIC)
    plan = cp.nominal_plan(system, dependencies, seed=Quantity(300.0, KELVIN), tolerance=Quantity(1e-6, KELVIN),
                           max_iterations=budget)
    if relaxation is not None:
        import dataclasses

        plan = dataclasses.replace(plan, relaxation_factor=relaxation)
    return plan


@pytest.mark.parametrize("system", [NOMINAL, TWO_STAGE], ids=["nominal", "two_stage"])
def test_the_runtime_build_reaches_the_native_outcome_iterations_and_values(system):
    plan = _plan(system)
    native = cp.run_fixed_point_coupling(system, plan, run_id="native")
    run, built = run_through_runtime(system, plan, run_id="runtime")
    parity = compare_with_native(native, run, built)
    assert parity.same_outcome and parity.runtime_outcome == "converged"
    assert parity.native_iterations == parity.runtime_iterations
    assert parity.output_differences
    for key, difference in parity.output_differences.items():
        assert difference <= 1e-9, (key, difference)


def test_an_iteration_limit_is_not_completed_on_both_paths():
    plan = _plan(NOMINAL, budget=1)
    native = cp.run_fixed_point_coupling(NOMINAL, plan, run_id="native")
    run, built = run_through_runtime(NOMINAL, plan, run_id="runtime")
    parity = compare_with_native(native, run, built)
    assert parity.native_outcome == parity.runtime_outcome == "not_completed"


def test_the_torn_edges_are_exactly_the_edges_the_runtime_requires_criteria_on():
    plan = _plan(TWO_STAGE)
    built = runtime_equivalent(TWO_STAGE, plan)
    assert set(built.plan.required_convergence_edges(built.graph)) == set(built.torn_edges)
    assert {c.edge_id for c in built.plan.criteria} == set(built.torn_edges)


def test_a_relaxed_native_plan_is_refused_by_the_runtime_build():
    with pytest.raises(InvalidScientificProblem, match="relaxes only the torn values"):
        runtime_equivalent(NOMINAL, _plan(NOMINAL, relaxation=0.5))


def test_a_relaxed_native_run_no_longer_claims_it_was_not_relaxed():
    run = cp.run_fixed_point_coupling(NOMINAL, _plan(NOMINAL, relaxation=0.5), run_id="relaxed")
    assert not any("no relaxation" in a for a in run.provenance.assumptions)
    assert any("under-relaxed with factor 0.5" in a for a in run.provenance.assumptions)
    plain = cp.run_fixed_point_coupling(NOMINAL, _plan(NOMINAL), run_id="plain")
    assert "no relaxation, damping or acceleration is applied" in plain.provenance.assumptions


def test_the_runtime_build_keeps_every_produced_result():
    run, built = run_through_runtime(NOMINAL, _plan(NOMINAL), run_id="runtime")
    produced = sum(len(p.results) for p in built.participants.values())
    assert produced == len(built.participants) * len(run.windows[0].iterations)
    assert assess_run_outcome(run).outcome is CouplingRunOutcome.CONVERGED


# ---- deferred initial outputs ------------------------------------------------------------------------------


def _spec(pid, ports, transient=False):
    return ParticipantSpec(pid, "m", "1", "r", "1", "s", "1", "a", "1", tuple(ports), transient=transient,
                           checkpointable=True, deterministic_restore=True)


def _port(pid, direction):
    return PortDefinition(pid, PortDirection(direction), PortKind.SCALAR, "temperature", "K")


def _deferred(spec, fn):
    out = spec.outputs[0].port_id
    digest = hashlib.sha256(spec.participant_id.encode()).hexdigest()
    return CallbackParticipant(
        spec, initialize=lambda *_: InitializationResult({}, {}),
        advance=lambda r: AdvanceResult(r.end, {out: fn(dict(r.inputs))}, {out: UNKNOWN}, 1, True),
        checkpoint=lambda t: RuntimeCheckpoint(CheckpointRecord(spec.participant_id, t, digest, True), None),
        restore=lambda cp_: None)


def _loop(semantics, *, seed=True, forward_criterion=False):
    a = _spec("a", [_port("y", "input"), _port("x", "output")])
    b = _spec("b", [_port("x", "input"), _port("y", "output")])
    graph = PhysicsGraph("deferred", (a, b), (CouplingEdge("e_x", PortRef("a", "x"), PortRef("b", "x")),
                                              CouplingEdge("e_y", PortRef("b", "y"), PortRef("a", "y"))))
    criteria = [ConvergenceCriterion("e_y", 0.0, Quantity(1e-9, "K"))]
    if forward_criterion or semantics is IterationSemantics.JACOBI:
        criteria.append(ConvergenceCriterion("e_x", 0.0, Quantity(1e-9, "K")))
    plan = CouplingPlan("deferred", CouplingScheme.IMPLICIT, semantics,
                        TimePolicy(Quantity(0, "s"), Quantity(1, "s"), Quantity(1, "s")), ("a", "b"),
                        tuple(criteria), max_iterations=200)
    store = InMemoryBulkStore()
    runtime = MultiphysicsRuntime(
        graph, plan,
        {"a": _deferred(a, lambda i: Quantity(0.5 * i["y"].magnitude_in("K") + 100.0, "K")),
         "b": _deferred(b, lambda i: Quantity(i["x"].magnitude_in("K"), "K"))},
        resolver=BulkDataResolver(store), store=store)
    seeds = {"e_y": Quantity(300.0, "K")} if seed else {}
    return runtime.run("deferred", external_inputs={}, initial_coupling_values=seeds)


def test_a_steady_participant_may_defer_outputs_that_a_serial_sweep_overwrites():
    run = _loop(IterationSemantics.SERIAL)
    assert assess_run_outcome(run).outcome is CouplingRunOutcome.CONVERGED
    assert run.final_outputs["a.x"]["magnitude"] == pytest.approx(200.0, abs=1e-6)


def test_a_lagged_edge_from_a_deferred_participant_must_be_seeded():
    with pytest.raises(Exception, match="no initial source output"):
        _loop(IterationSemantics.SERIAL, seed=False)


def test_jacobi_reads_the_previous_iterate_so_deferred_outputs_are_refused():
    with pytest.raises(Exception, match="no initial source output"):
        _loop(IterationSemantics.JACOBI)


def test_a_criterion_on_an_unseeded_forward_edge_is_refused():
    with pytest.raises(InvalidScientificProblem, match="no initial value"):
        _loop(IterationSemantics.SERIAL, forward_criterion=True)


# ---- isolation and exact NONE relaxation ------------------------------------------------------------------------


def test_one_object_under_two_concurrent_ids_is_refused():
    a = _spec("a", [_port("x", "output")], transient=True)
    b = _spec("b", [_port("x", "output")], transient=True)
    shared = _deferred(a, lambda i: Quantity(1, "K"))
    plan = CouplingPlan("iso", CouplingScheme.EXPLICIT, IterationSemantics.JACOBI,
                        TimePolicy(Quantity(0, "s"), Quantity(1, "s"), Quantity(1, "s")))
    store = InMemoryBulkStore()
    with pytest.raises(InvalidScientificProblem, match="same object"):
        MultiphysicsRuntime(PhysicsGraph("iso", (a, b), ()), plan, {"a": shared, "b": shared},
                            resolver=BulkDataResolver(store), store=store,
                            concurrency=ConcurrentAdvancePolicy(("a", "b"), 2, "test"))


def test_no_relaxation_delivers_the_transfer_exactly():
    controller = RelaxationController(RelaxationPolicy(), BulkDataResolver(InMemoryBulkStore()), InMemoryBulkStore(), {})
    old, raw = Quantity(0.2, "K"), Quantity(0.9, "K")  # 0.2 + (0.9 - 0.2) != 0.9 in float64
    assert 0.2 + (0.9 - 0.2) != 0.9
    value, factor = controller.relax("e", old, raw, unit="K")
    assert factor == 1.0 and value.magnitude_in("K") == 0.9
    assert np.isfinite(value.magnitude)
