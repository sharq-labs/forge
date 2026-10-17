"""Phase 3.5 WS2 -- the electrothermal migration candidate on the one coupling authority.

* ``RelaxationPolicy.scope = "lagged_edges"``: a scalar-mix relaxation restricted to the lagged edges
  of a serial sweep (the native loop's torn-only under-relaxation); forward edges then need no criterion.
* ``run_coupled_via_runtime`` executes the composition on ``MultiphysicsRuntime`` and returns a native
  ``CoupledRun``; ``run_electrothermal_coupling`` keeps the NATIVE loop as the default, and the
  candidate refuses to run without an explicit acknowledgement while parity is unverified.
* PARITY fixtures: outcome, iteration count, per-iteration largest change and final values against
  the native loop on NOMINAL, TWO_STAGE, a relaxed plan, an iteration limit and a refused transfer.
  These are the evidence gate for the migration (never asserted as passed here).

NOT RUN (Phase 3.5 build phase): docs/work/DEFERRED_VALIDATION.md, DV-88..DV-90.
"""

from __future__ import annotations

import dataclasses

import pytest

from engcore.domains.electrical import material as mat
from engcore.domains.thermal_models import lumped as lump
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.multiphysics import (
    ConvergenceCriterion, CouplingPlan, CouplingScheme, IterationSemantics, RelaxationKind, RelaxationPolicy, TimePolicy,
)
from engcore.scientific.units.quantity import Quantity
from engcore.systems.electrothermal import coupled as cp
from engcore.systems.electrothermal.runtime_adapter import (
    RUNTIME_PATH_PARITY_VERIFIED, CouplingPathChoice, run_coupled_via_runtime, run_electrothermal_coupling, runtime_equivalent,
)

KELVIN = "kelvin"


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
#: a strongly negative temperature coefficient: heating drives R(T) negative, a result its own checks reject
REFUSING = cp.CoupledElectroThermalSystem(
    stages=(cp.CoupledStage(_conductor("R1", 10.0, -0.03), _body("R1", 2.5, 0.05)),), source_voltage=Quantity(5.0, "volt"))


def _plan(system, budget=50, relaxation=None):
    problems = cp.coupled_problems(system, {s.component_id: s.conductor.reference_resistance for s in system.stages})
    dependencies = cp.coupled_dependencies(system, problems, temperature_metric=lump.TEMPERATURE_METRIC)
    plan = cp.nominal_plan(system, dependencies, seed=Quantity(300.0, KELVIN), tolerance=Quantity(1e-6, KELVIN),
                           max_iterations=budget)
    return plan if relaxation is None else dataclasses.replace(plan, relaxation_factor=relaxation)


# ---- the relaxation scope ------------------------------------------------------------------------------------------


def test_the_lagged_scope_is_declared_serialized_only_when_used_and_refused_where_meaningless():
    lagged = RelaxationPolicy(RelaxationKind.CONSTANT, 0.5, 0.05, 1.0, scope="lagged_edges")
    assert lagged.to_dict()["scope"] == "lagged_edges" and RelaxationPolicy.from_dict(lagged.to_dict()) == lagged
    assert "scope" not in RelaxationPolicy(RelaxationKind.CONSTANT, 0.5, 0.05, 1.0).to_dict()
    for kind in (RelaxationKind.NONE, RelaxationKind.IQN_ILS):
        with pytest.raises(InvalidScientificProblem, match="lagged_edges"):
            RelaxationPolicy(kind, 1.0 if kind is RelaxationKind.NONE else 0.5, 0.05, 1.0,
                             3 if kind is RelaxationKind.IQN_ILS else 0, scope="lagged_edges")
    with pytest.raises(InvalidScientificProblem, match="IMPLICIT SERIAL"):
        CouplingPlan("p", CouplingScheme.IMPLICIT, IterationSemantics.JACOBI,
                     TimePolicy(Quantity(0, "s"), Quantity(1, "s"), Quantity(1, "s")), ("a", "b"),
                     (ConvergenceCriterion("e", 0.0, Quantity(1e-8, "K")),), lagged, 10, True)


def test_a_relaxed_plan_requires_criteria_on_the_torn_edges_only():
    built = runtime_equivalent(TWO_STAGE, _plan(TWO_STAGE, relaxation=0.5))
    assert set(built.plan.required_convergence_edges(built.graph)) == set(built.torn_edges)


# ---- the controlled switch -----------------------------------------------------------------------------------------


def test_the_native_loop_stays_the_default_and_the_candidate_needs_an_acknowledgement():
    assert RUNTIME_PATH_PARITY_VERIFIED is False
    plan = _plan(NOMINAL)
    default = run_electrothermal_coupling(NOMINAL, plan, run_id="x")
    native = cp.run_fixed_point_coupling(NOMINAL, plan, run_id="x")
    assert default.outcome is native.outcome and default.final_values == native.final_values
    assert default.provenance.software_version == native.provenance.software_version
    with pytest.raises(InvalidScientificProblem, match="acknowledge_unverified_parity"):
        run_electrothermal_coupling(NOMINAL, plan, path=CouplingPathChoice.RUNTIME_CANDIDATE)
    with pytest.raises(InvalidScientificProblem, match="parity"):
        run_coupled_via_runtime(NOMINAL, plan)


# ---- parity fixtures (the migration's evidence gate) ---------------------------------------------------------------


def _assert_parity(native, candidate, *, tol=1e-9):
    assert candidate.outcome is native.outcome
    assert len(candidate.iterations) == len(native.iterations)
    for a, b in zip(native.iterations, candidate.iterations):
        assert b.largest_iterate_change.magnitude_in(str(a.largest_iterate_change.units)) == pytest.approx(
            a.largest_iterate_change.magnitude, abs=tol)
    assert set(candidate.final_values) == set(native.final_values)
    for key, value in native.final_values.items():
        assert candidate.final_values[key].magnitude_in(str(value.units)) == pytest.approx(value.magnitude, abs=tol)
    assert {c.key for c in candidate.crossings} == {c.key for c in native.crossings}


@pytest.mark.parametrize("system,relaxation", [(NOMINAL, None), (TWO_STAGE, None), (NOMINAL, 0.5), (TWO_STAGE, 0.7)],
                         ids=["nominal", "two_stage", "nominal_relaxed", "two_stage_relaxed"])
def test_the_candidate_reproduces_the_native_loop(system, relaxation):
    plan = _plan(system, relaxation=relaxation)
    native = cp.run_fixed_point_coupling(system, plan, run_id="native")
    candidate, record = run_coupled_via_runtime(system, plan, run_id="candidate", acknowledge_unverified_parity=True)
    assert native.outcome is cp.CouplingOutcome.CRITERION_MET
    _assert_parity(native, candidate)
    assert record is not None and any("NOT VERIFIED" in a for a in candidate.provenance.assumptions)


def test_an_iteration_limit_reproduces_the_native_final_iterate():
    plan = _plan(NOMINAL, budget=2, relaxation=0.5)
    native = cp.run_fixed_point_coupling(NOMINAL, plan, run_id="native")
    candidate, _ = run_coupled_via_runtime(NOMINAL, plan, run_id="candidate", acknowledge_unverified_parity=True)
    assert native.outcome is cp.CouplingOutcome.ITERATION_LIMIT_REACHED
    _assert_parity(native, candidate)  # the RELAXED last iterate, as the native loop reports it


def test_a_refused_transfer_is_a_recorded_stop_on_both_paths():
    plan = _plan(REFUSING)
    native = cp.run_fixed_point_coupling(REFUSING, plan, run_id="native")
    candidate, record = run_coupled_via_runtime(REFUSING, plan, run_id="candidate", acknowledge_unverified_parity=True)
    assert native.outcome is candidate.outcome is cp.CouplingOutcome.TRANSFER_REFUSED
    assert record is None and candidate.refusal is not None
    assert candidate.refusal.iteration == native.refusal.iteration
    assert candidate.refusal.result.problem_id == native.refusal.result.problem_id
    # boundary difference 1 (recorded, not hidden): the runtime refuses at production, so the refused
    # sweep may list fewer results than the native one -- never more
    assert len(candidate.iterations[-1].results) <= len(native.iterations[-1].results)
