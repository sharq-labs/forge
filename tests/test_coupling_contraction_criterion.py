"""CRITERION_MET means the iterate is near its fixed point, not only that its last step was small.

Until 2026-10-13 ``run_fixed_point`` met its criterion on the step alone. An iterate that approaches its fixed
point from one side at rate ``rho`` is still ``step * rho / (1 - rho)`` away -- 19 steps at ``rho = 0.95`` -- so a
slowly contracting loop was reported as converged far outside its own tolerance. The criterion now also requires
the a-posteriori distance, estimated per torn endpoint from its last two signed steps, to be within the tolerance.
An oscillating iterate is at most half a step away, so the electrothermal designs this loop already served (a
positive temperature coefficient feeding back through dissipation oscillates) stop exactly where they did.
"""

from __future__ import annotations

import dataclasses
import math

import pytest

from engcore.credibility.evidence import CouplingCriterion
from engcore.mcp import example_electrothermal_payload
from engcore.mcp.problem import build_electrothermal_system
from engcore.product.problem import _coupling_evidence
from engcore.scientific.units.quantity import Quantity
from engcore.systems.electrothermal import coupled as cp

K = "kelvin"
KEY = ("resistance-tcr-R1", "temperature")
AT = {KEY: Quantity(400.0, K)}


# ---------------------------------------------------------------------------
# The estimate
# ---------------------------------------------------------------------------


def test_a_one_sided_slow_iterate_is_far_from_its_fixed_point_after_a_small_step() -> None:
    distance = cp._distance_to_fixed_point({KEY: 1e-7}, {KEY: 1e-7 / 0.95}, AT, K)
    assert distance == pytest.approx(1e-7 * 0.95 / 0.05)


def test_an_oscillating_iterate_is_within_half_its_step() -> None:
    distance = cp._distance_to_fixed_point({KEY: -1e-7}, {KEY: 1e-7 / 0.95}, AT, K)
    assert distance == pytest.approx(1e-7 * 0.95 / 1.95)
    assert distance <= 0.5e-7


@pytest.mark.parametrize(
    "previous, why",
    [
        (None, "a first sweep has no rate"),
        ({KEY: 0.0}, "a rate from a zero step is not a rate"),
        ({KEY: 0.5e-7}, "growing: rho = 2"),
        ({KEY: -1e-7}, "oscillating without shrinking: rho = -1"),
    ],
)
def test_no_rate_or_no_contraction_is_infinitely_far(previous, why) -> None:
    assert cp._distance_to_fixed_point({KEY: 1e-7}, previous, AT, K) == math.inf, why


def test_a_step_at_the_round_off_floor_is_its_own_distance() -> None:
    # 64 ulp of 400 K is about 5.7e-12 K; below it a ratio of steps measures noise.
    assert cp._distance_to_fixed_point({KEY: 1e-15}, None, AT, K) == 1e-15
    assert cp._distance_to_fixed_point({KEY: 0.0}, None, AT, K) == 0.0


# ---------------------------------------------------------------------------
# The loop
# ---------------------------------------------------------------------------


def _slow_one_sided_run(fixed: float, rho: float, *, seed: float = 300.0, max_iterations: int = 2000):
    """The example composition with its thermal output replaced by ``T -> fixed + rho (T - fixed)``.

    Every participant still runs and every transfer still passes admission; only the map the loop iterates is
    controlled, so its fixed point and its contraction rate are known exactly.
    """
    system = build_electrothermal_system(example_electrothermal_payload())
    problems = cp.coupled_problems(system, {s.component_id: s.conductor.reference_resistance for s in system.stages})
    plan = cp.nominal_plan(
        system,
        cp.coupled_dependencies(system, problems),
        seed=Quantity(seed, K),
        tolerance=Quantity(1e-6, K),
        max_iterations=max_iterations,
    )
    table = dict(cp._executors(system, problems))
    received: dict[str, float] = {}
    real_property, real_thermal = table["resistance-tcr-R1"], table["thermal-lumped-R1"]

    def property_call(inputs, run_id):
        received["T"] = inputs["temperature"].magnitude_in(K)
        return real_property(inputs, run_id)

    def thermal_call(inputs, run_id):
        result = real_thermal(inputs, run_id)
        mapped = fixed + rho * (received["T"] - fixed)
        return dataclasses.replace(result, values={**result.values, "final_temperature": Quantity(mapped, K)})

    table["resistance-tcr-R1"], table["thermal-lumped-R1"] = property_call, thermal_call
    return cp.run_fixed_point(problems, table, plan, run_id="slow-one-sided", software_version="test")


def test_a_slow_one_sided_loop_is_met_only_inside_its_tolerance() -> None:
    fixed, rho, tolerance = 350.0, 0.95, 1e-6
    run = _slow_one_sided_run(fixed, rho)
    assert run.outcome is cp.CouplingOutcome.CRITERION_MET
    (final,) = run.final_values.values()
    assert abs(final.magnitude_in(K) - fixed) <= tolerance

    # Where the step-only criterion stopped: the first sweep whose step was within the tolerance. Its iterate was
    # about rho / (1 - rho) = 19 tolerances from the fixed point -- reported as converged.
    steps = [change.magnitude_in(K) for change in run.iterate_changes]
    old_stop = next(i for i, step in enumerate(steps) if step <= tolerance)
    iterate = run.iterations[old_stop].result_for("thermal-lumped-R1").value("final_temperature").magnitude_in(K)
    assert abs(iterate - fixed) > 10 * tolerance
    assert run.iterations_run > old_stop + 1

    # The run states the distance it stopped on, re-derived from its own iterations, and the report reads it.
    distance = run.final_distance_to_fixed_point
    assert distance is not None and distance.magnitude_in(K) <= tolerance
    evidence = _coupling_evidence(run)
    assert evidence.distance_to_fixed_point == distance and evidence.criterion is CouplingCriterion.MET


@pytest.mark.parametrize(
    "seed, budget, why",
    [
        (300.0, None, "the budget runs out after the change is small but before the distance is"),
        (350.0 + 1e-6, 1, "one sweep: a change below the tolerance and no rate to bound the distance"),
    ],
)
def test_a_run_stopped_by_its_budget_with_a_small_last_change_is_never_met(seed, budget, why) -> None:
    """Review finding F1: the report read the change alone, so these runs read MET beside ``iteration_limit_reached``."""
    fixed, rho, tolerance = 350.0, 0.95, 1e-6
    if budget is None:
        unlimited = _slow_one_sided_run(fixed, rho, seed=seed)
        steps = [change.magnitude_in(K) for change in unlimited.iterate_changes]
        budget = next(i for i, step in enumerate(steps) if step <= tolerance) + 2
        assert budget < unlimited.iterations_run
    run = _slow_one_sided_run(fixed, rho, seed=seed, max_iterations=budget)
    assert run.outcome is cp.CouplingOutcome.ITERATION_LIMIT_REACHED, why
    assert run.final_iterate_change.magnitude_in(K) <= tolerance, why
    evidence = _coupling_evidence(run)
    assert evidence.criterion is CouplingCriterion.NOT_MET, why
    assert evidence.outcome == "iteration_limit_reached"
