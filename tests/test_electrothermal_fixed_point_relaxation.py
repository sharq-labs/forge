"""Opt-in under-relaxation of the electrothermal fixed point (Engineering Runtime V1, Big Rock 18).

The integration target's own fixed-point loop gains ``relaxation_factor``.
The stopping test stays the UNRELAXED change and a converged run reports the
unrelaxed transported values, so relaxation changes the path only.  Plans
without a factor keep their identity and records.  NOT YET EXECUTED (build
phase): see docs/work/DEFERRED_VALIDATION.md.
"""

from __future__ import annotations

import dataclasses
import importlib.util
import pathlib

import pytest

from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.units.quantity import Quantity
from engcore.systems.electrothermal import coupled as cp

HERE = pathlib.Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location(
    "lumped_applicability_fixture", str(HERE / "domains" / "thermal_models" / "test_lumped_applicability.py"))
F = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(F)

K = "kelvin"


def _plan_and_system(max_iterations=200):
    system = cp.CoupledElectroThermalSystem(
        stages=(cp.CoupledStage(F.conductor(), F.coupled_body(F.COUPLED_DECLARATION)),),
        source_voltage=Quantity(5.0, "volt"),
    )
    problems = cp.coupled_problems(system, {s.component_id: s.conductor.reference_resistance for s in system.stages})
    dependencies = cp.coupled_dependencies(system, problems)
    plan = cp.nominal_plan(system, dependencies, seed=Quantity(300.0, K), tolerance=Quantity(1e-6, K),
                           max_iterations=max_iterations)
    return plan, system


@pytest.mark.parametrize("factor", [0.0, 1.0, 1.5, float("nan"), True])
def test_relaxation_factor_is_under_relaxation_only(factor):
    plan, _ = _plan_and_system()
    with pytest.raises(InvalidScientificProblem, match="relaxation_factor"):
        dataclasses.replace(plan, relaxation_factor=factor)


def test_plans_without_a_factor_keep_their_identity_and_a_declared_one_round_trips():
    plan, _ = _plan_and_system()
    assert "relaxation_factor" not in plan.to_dict()
    relaxed = dataclasses.replace(plan, relaxation_factor=0.5)
    assert cp.FixedPointCouplingPlan.from_dict(relaxed.to_dict()) == relaxed


def test_relaxed_and_unrelaxed_runs_reach_the_same_fixed_point_under_the_same_unrelaxed_criterion():
    plan, system = _plan_and_system()
    plain = cp.run_fixed_point_coupling(system, plan, run_id="et-plain")
    relaxed = cp.run_fixed_point_coupling(system, dataclasses.replace(plan, relaxation_factor=0.5), run_id="et-relaxed")
    assert plain.outcome is cp.CouplingOutcome.CRITERION_MET
    assert relaxed.outcome is cp.CouplingOutcome.CRITERION_MET
    for key, value in plain.final_values.items():
        assert relaxed.final_values[key].magnitude_in(K) == pytest.approx(value.magnitude_in(K), abs=1e-4)
    # the criterion is judged on the unrelaxed change: the last recorded change met the declared tolerance
    assert relaxed.iterations[-1].largest_iterate_change.magnitude_in(K) <= 1e-6


def test_the_relaxed_run_records_its_factor_and_the_plain_run_does_not():
    plan, system = _plan_and_system()
    assert "relaxation_factor" not in cp.run_fixed_point_coupling(system, plan, run_id="et-plain").to_dict()["plan"]
    relaxed = cp.run_fixed_point_coupling(system, dataclasses.replace(plan, relaxation_factor=0.5), run_id="et-relaxed")
    assert relaxed.to_dict()["plan"]["relaxation_factor"] == 0.5
