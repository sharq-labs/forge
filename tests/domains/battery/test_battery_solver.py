"""The evaluator: what it computes, what it claims, and what it refuses.

Three concerns, kept apart here as they are in the code:

* the arithmetic is right, and is checked against hand-derived values;
* what the solver reports about itself is honest — a closed form reports
  NOT_APPLICABLE and not CONVERGED, and its checks claim only the one level
  they earn;
* a result may not be attributed to a system that did not produce it.
"""

from __future__ import annotations

import pytest

from engcore.domains.battery import cell as bat
from engcore.domains.battery import context as ctx
from engcore.domains.battery import models as mdl
from engcore.domains.battery import solver as sol
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.models.definition import ModelValidationStatus
from engcore.scientific.realizations.definition import ModelFormulation
from engcore.scientific.results.validation import (
    ValidationLevel,
    ValidationOutcome,
)
from engcore.scientific.solvers.protocol import ConvergenceState
from engcore.scientific.units.quantity import Quantity

from battery_cases import assess, build_cell, build_limits, build_load

# The builders are used under two names on purpose: ``build_*`` inside this
# module's own helpers, and ``make_*`` in the test bodies, where the shorter
# name keeps the one field a test is about visible at its call site.
assess_models = assess
make_cell = build_cell
make_limits = build_limits
make_load = build_load


K = "kelvin"
S = "second"
A = "ampere"
V = "volt"
AH = "ampere_hour"
ONE = "dimensionless"


def solved(cell, load, realization=mdl.RINT_OCV_REALIZATION):
    problem = bat.build_battery_problem(cell, load)
    solver = sol.BatteryCellSolver()
    solver.bind_cell(cell, load, problem.problem_id)
    prepared = solver.prepare(problem, realization=realization)
    return solver, prepared, solver.solve(prepared)


# =====================================================================
# The arithmetic
# =====================================================================

def test_the_step_computes_the_hand_derived_values():
    """2.5 A for two minutes from a 2.5 Ah cell at 90 % charge.

        z_end = 0.9 - 2.5 * (1/30) / (0.99 * 2.5)
        OCV   = 3.0 + 1.2 * z_end
        V     = OCV - 2.5 * 0.030
        Q     = 2.5^2 * 0.030                     = 0.1875 W
    """
    computed = sol.evaluate_step(make_cell(), make_load())
    expected_soc = 0.9 - (1.0 / 30.0) / 0.99
    assert computed.final_state_of_charge == pytest.approx(expected_soc)
    assert computed.open_circuit_voltage == pytest.approx(3.0 + 1.2 * expected_soc)
    assert computed.terminal_voltage == pytest.approx(3.0 + 1.2 * expected_soc - 0.075)
    assert computed.heat_generation == pytest.approx(0.1875)


def test_the_runtime_is_the_time_to_the_first_cutoff_reached():
    """A 0.15 SoC cutoff binds before a 3.0 V cutoff at 0.0625 SoC.

        t = (0.90 - 0.15) * 0.99 * 2.5 Ah / 2.5 A = 0.7425 h = 2673 s
    """
    computed = sol.evaluate_step(make_cell(), make_load())
    assert computed.binding_cutoff_state_of_charge == pytest.approx(0.15)
    assert computed.runtime_to_cutoff == pytest.approx(2673.0)


def test_the_binding_cutoff_switches_to_the_voltage_limit_at_high_current():
    """At 25 A the 3.0 V cutoff bites at SoC 0.625, above the 0.15 target.

    This is the sizing error the runtime model's consistency condition exists
    to report, seen from the arithmetic: the run stops with 0.625 of the charge
    still in the cell rather than the 0.15 that was asked for, so the honest
    runtime is 0.275/0.75 — barely a third — of what a depth-of-discharge
    calculation that ignored the voltage limit would give.
    """
    computed = sol.evaluate_step(make_cell(), make_load(current=Quantity(25.0, A)))
    assert computed.binding_cutoff_state_of_charge == pytest.approx(0.625)
    honest = (0.90 - 0.625) * 0.99 * 2.5 / 25.0 * 3600.0
    naive = (0.90 - 0.15) * 0.99 * 2.5 / 25.0 * 3600.0
    assert computed.runtime_to_cutoff == pytest.approx(honest)
    assert computed.runtime_to_cutoff == pytest.approx(naive * 0.275 / 0.75)
    assert computed.runtime_to_cutoff < naive / 2.0


def test_no_cutoff_declared_means_no_runtime_rather_than_an_infinite_one():
    computed = sol.evaluate_step(
        make_cell(),
        make_load(cutoff_voltage=None, cutoff_state_of_charge=None),
    )
    assert computed.binding_cutoff_state_of_charge is None
    assert computed.runtime_to_cutoff is None


def test_no_peukert_exponent_means_no_effective_capacity():
    cell = make_cell(limits=make_limits(peukert_exponent=None))
    assert sol.evaluate_step(cell, make_load()).effective_capacity is None


def test_the_step_reads_units_rather_than_magnitudes():
    """The same physical run, declared in different units, gives one answer."""
    metric = sol.evaluate_step(make_cell(), make_load())
    mixed = sol.evaluate_step(
        make_cell(
            nominal_capacity=Quantity(9000.0, "coulomb"),
            internal_resistance=Quantity(30.0, "milliohm"),
            open_circuit_voltage_at_full=Quantity(4200.0, "millivolt"),
            open_circuit_voltage_at_empty=Quantity(3000.0, "millivolt"),
        ),
        make_load(
            current=Quantity(2500.0, "milliampere"),
            duration=Quantity(2.0, "minute"),
            cell_temperature=Quantity(25.0, "degC"),
        ),
    )
    assert mixed.final_state_of_charge == pytest.approx(metric.final_state_of_charge)
    assert mixed.terminal_voltage == pytest.approx(metric.terminal_voltage)
    assert mixed.heat_generation == pytest.approx(metric.heat_generation)


# =====================================================================
# What the solver reports about itself
# =====================================================================

def test_a_closed_form_reports_not_applicable_and_never_converged():
    """It neither converges nor fails to, and the two must not be conflated."""
    _, _, raw = solved(make_cell(), make_load())
    assert raw.convergence is ConvergenceState.NOT_APPLICABLE
    assert raw.convergence is not ConvergenceState.CONVERGED
    assert raw.iterations == 1


def test_the_metrics_come_back_carrying_the_units_the_records_declare():
    solver, prepared, raw = solved(make_cell(), make_load())
    metrics = solver.extract_metrics(prepared, raw)
    assert metrics[mdl.TERMINAL_VOLTAGE_METRIC].is_compatible_with(V)
    assert metrics[mdl.HEAT_GENERATION_METRIC].is_compatible_with("watt")
    assert metrics[mdl.RUNTIME_METRIC].is_compatible_with(S)
    assert metrics[mdl.EFFECTIVE_CAPACITY_METRIC].is_compatible_with(AH)
    assert metrics[mdl.FINAL_STATE_OF_CHARGE_METRIC].is_compatible_with(ONE)


def test_each_model_receives_only_the_metrics_it_declares():
    """One evaluator produces the union; each record claims its own share.

    A consumer asking what the charge balance produced must not be handed a
    terminal voltage: that number rests on the Rint model's assumptions and
    carries the Rint model's validity verdict, not this one's.
    """
    solver, prepared, raw = solved(make_cell(), make_load())
    assert set(solver.metrics_for(mdl.COULOMB_COUNTING_MODEL.model_id, prepared, raw)) == {
        mdl.FINAL_STATE_OF_CHARGE_METRIC
    }
    assert set(solver.metrics_for(mdl.RINT_OCV_MODEL.model_id, prepared, raw)) == {
        mdl.TERMINAL_VOLTAGE_METRIC,
        mdl.OPEN_CIRCUIT_VOLTAGE_METRIC,
        mdl.HEAT_GENERATION_METRIC,
    }
    assert set(
        solver.metrics_for(
            mdl.CONSTANT_CURRENT_RUNTIME_MODEL.model_id, prepared, raw
        )
    ) == {mdl.RUNTIME_METRIC}
    assert set(
        solver.metrics_for(mdl.PEUKERT_DERATING_MODEL.model_id, prepared, raw)
    ) == {mdl.EFFECTIVE_CAPACITY_METRIC}


def test_an_unknown_model_id_is_refused_rather_than_returning_nothing():
    solver, prepared, raw = solved(make_cell(), make_load())
    with pytest.raises(InvalidScientificProblem, match="unknown battery model"):
        solver.metrics_for("battery.cell.invented", prepared, raw)


# =====================================================================
# What the checks establish
# =====================================================================

def test_the_only_level_claimed_is_the_one_the_dimension_check_earns():
    """Three checks pass; exactly one establishes a level.

    The dimension check compares what was computed against what the model
    records declare, which is a reference outside the arithmetic. The two
    residuals compare a closed form against the equation it was derived from,
    with no independent reference — real work, but weaker evidence than the
    byte-pinned conduction solver has, and that solver claims no more than
    dimensional validity either.
    """
    solver, prepared, raw = solved(make_cell(), make_load())
    report = solver.validate(prepared, raw)
    assert report.status is ValidationOutcome.PASS
    assert report.attained_levels == frozenset({ValidationLevel.DIMENSIONALLY_VALID})
    assert not report.claims(ValidationLevel.ANALYTICALLY_VERIFIED)
    assert not report.claims(ValidationLevel.EXPERIMENTALLY_VALIDATED)

    by_name = {check.name: check for check in report.checks}
    assert by_name["metric_dimensions"].establishes is (
        ValidationLevel.DIMENSIONALLY_VALID
    )
    assert by_name["coulomb_balance_residual"].establishes is None
    assert by_name["rint_terminal_residual"].establishes is None


def test_the_closed_forms_satisfy_the_relations_they_solve():
    """Both residuals sit at round-off, and each carries the number it got."""
    solver, prepared, raw = solved(make_cell(), make_load())
    by_name = {check.name: check for check in solver.validate(prepared, raw).checks}
    for name in ("coulomb_balance_residual", "rint_terminal_residual"):
        check = by_name[name]
        assert check.outcome is ValidationOutcome.PASS
        assert check.residual is not None
        assert check.tolerance is not None
        assert check.residual <= check.tolerance


def test_the_residual_checks_would_catch_a_broken_closed_form():
    """The residuals do real work, shown by giving them a wrong answer.

    A check that passes whatever it is handed establishes nothing. This
    rewrites the state of charge in the raw output as though the efficiency
    had been dropped, and asserts the balance residual notices.
    """
    solver, prepared, raw = solved(make_cell(), make_load())
    from dataclasses import replace

    tampered = replace(
        raw,
        values={
            **raw.values,
            # 0.9 - 2.5 * (1/30) / 2.5, i.e. eta silently taken as 1.
            mdl.FINAL_STATE_OF_CHARGE_METRIC: 0.9 - (1.0 / 30.0),
        },
    )
    by_name = {
        check.name: check for check in solver.validate(prepared, tampered).checks
    }
    assert by_name["coulomb_balance_residual"].outcome is ValidationOutcome.FAIL
    assert solver.validate(prepared, tampered).status is ValidationOutcome.FAIL


def test_the_three_closed_form_models_are_self_consistent_and_peukert_is_not():
    """A curve fit has no differential balance to be consistent with.

    Evaluating a correlation correctly establishes nothing about whether the
    correlation holds, so awarding it the same word as a closed form that
    solves an equation would be the strongest term this repository has applied
    to the weakest evidence it holds.
    """
    for model in (
        mdl.RINT_OCV_MODEL,
        mdl.COULOMB_COUNTING_MODEL,
        mdl.CONSTANT_CURRENT_RUNTIME_MODEL,
    ):
        assert model.validation_status is ModelValidationStatus.SELF_CONSISTENT
    assert (
        mdl.PEUKERT_DERATING_MODEL.validation_status
        is ModelValidationStatus.UNVALIDATED
    )
    # And nothing in the domain claims a measurement nobody made.
    for model in mdl.BATTERY_MODELS:
        assert model.validation_status not in (
            ModelValidationStatus.EXPERIMENTALLY_VALIDATED,
            ModelValidationStatus.BENCHMARK_VALIDATED,
        )


# =====================================================================
# Attribution
# =====================================================================

def test_a_problem_may_not_be_solved_against_a_cell_it_does_not_describe():
    """A result whose provenance contradicts its system is worse than none."""
    original = make_cell()
    load = make_load()
    problem = bat.build_battery_problem(original, load)
    solver = sol.BatteryCellSolver()
    solver.bind_cell(original, load, problem.problem_id)

    other = make_cell(cell_id="CELL-2", internal_resistance=Quantity(0.5, "ohm"))
    with pytest.raises(InvalidScientificProblem, match="already bound"):
        solver.bind_cell(other, load, problem.problem_id)


def test_the_same_cell_rebinds_freely_under_a_second_operating_point():
    """A load is an operating point, not a system. Changing it is not a swap."""
    cell = make_cell()
    problem = bat.build_battery_problem(cell, make_load())
    solver = sol.BatteryCellSolver()
    solver.bind_cell(cell, make_load(), problem.problem_id)
    solver.bind_cell(
        cell, make_load(current=Quantity(1.0, A)), problem.problem_id
    )


def test_declaring_more_about_a_cell_does_not_make_it_a_different_cell():
    """The same cell known to greater depth keeps its physical identity."""
    bare = make_cell(limits=ctx.CellLimits())
    detailed = make_cell()
    assert bare.physical_key == detailed.physical_key
    assert bare != detailed


def test_a_problem_omitting_a_limit_the_cell_declares_is_refused():
    """A verdict must not be attributed to evidence the problem never carried."""
    cell = make_cell()
    load = make_load()
    lean = bat.build_battery_problem(make_cell(limits=ctx.CellLimits()), load)
    solver = sol.BatteryCellSolver()
    solver.bind_cell(cell, load, lean.problem_id)
    with pytest.raises(InvalidScientificProblem, match="omits"):
        solver.prepare(lean)


def test_solving_an_unbound_problem_is_refused():
    problem = bat.build_battery_problem(make_cell(), make_load())
    with pytest.raises(InvalidScientificProblem, match="no cell is bound"):
        sol.BatteryCellSolver().prepare(problem)


# =====================================================================
# The records themselves
# =====================================================================

def test_every_model_binds_cleanly_to_a_problem_built_from_a_declared_cell():
    """Typed binding, not name matching: dimensions and source kinds too."""
    problem = bat.build_battery_problem(make_cell(), make_load())
    for model in mdl.BATTERY_MODELS:
        report = model.check_against(problem)
        assert report.is_satisfied, (model.model_id, report.issues)


def test_a_problem_from_a_bare_cell_still_binds_because_limits_are_optional():
    """An omitted declaration must not be a binding failure — only an UNKNOWN."""
    problem = bat.build_battery_problem(
        make_cell(limits=ctx.CellLimits()),
        make_load(
            pulse_current=None,
            pulse_duration=None,
            cutoff_voltage=None,
            cutoff_state_of_charge=None,
        ),
    )
    for model in mdl.BATTERY_MODELS:
        report = model.check_against(problem)
        assert report.is_satisfied, (model.model_id, report.issues)


def test_the_realizations_point_at_their_models_and_share_one_implementation():
    """Four records for four claims, one evaluator behind them.

    A realization points *at* a model. Sharing an implementation between four
    of them is what ``ImplementationReference`` is for; sharing a validity
    domain would be the merge this domain refuses.
    """
    by_model = {r.model.model_id: r for r in mdl.BATTERY_REALIZATIONS}
    assert set(by_model) == {m.model_id for m in mdl.BATTERY_MODELS}
    for model in mdl.BATTERY_MODELS:
        realization = by_model[model.model_id]
        assert realization.model.version == model.version
        assert (
            realization.implementation.implementation_id
            == "engcore.domains.battery.solver"
        )


def test_the_charge_balance_is_posed_as_an_ode_and_discharged_without_one():
    """Formulation is a property of the claim, not of how it is computed.

    The counter poses ``dz/dt = -I / (eta Q_nom)``. Its realization integrates
    that in closed form and needs no integrator, declaring only the algebraic
    solver capability — which is exactly the separation the realization
    contract exists to express.
    """
    counter = next(
        r
        for r in mdl.BATTERY_REALIZATIONS
        if r.model.model_id == mdl.COULOMB_COUNTING_MODEL.model_id
    )
    assert counter.formulation is ModelFormulation.ODE
    required = {c.name for c in counter.required_solver_capabilities}
    assert "core:algebraic" in required
    assert not any(name.startswith("core:ode") for name in required)
    rint = next(
        r
        for r in mdl.BATTERY_REALIZATIONS
        if r.model.model_id == mdl.RINT_OCV_MODEL.model_id
    )
    assert rint.formulation is ModelFormulation.ALGEBRAIC


def test_every_realization_declares_the_thermal_dependency_it_actually_has():
    """R_int drift, capacity drift and the discharge range all need a T.

    Declared by capability identifier, with no thermal module imported by the
    models file — a machine-checkable scientific dependency rather than a code
    coupling.
    """
    for realization in mdl.BATTERY_REALIZATIONS:
        assert mdl.REQUIRED_BODY_TEMPERATURE in realization.required_capabilities
    import inspect

    assert "thermal_models" not in inspect.getsource(mdl)


def test_the_registries_are_fresh_every_call_and_carry_every_record():
    """No global mutable registry exists, so no caller's set can be mutated."""
    first, second = mdl.battery_model_registry(), mdl.battery_model_registry()
    assert first is not second
    assert mdl.battery_realizations() is not mdl.battery_realizations()
    for model in mdl.BATTERY_MODELS:
        assert first.get(model.model_id, model.version) is model
