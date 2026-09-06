"""A cell heating itself against the existing lumped thermal model.

The test this file exists for is
``test_self_heating_carries_the_cell_out_of_its_validated_domain``: the cell's
own dissipation raises its temperature until a temperature-dependent condition
flips to OUTSIDE_VALIDATED_DOMAIN, *while* the numerical convergence of every
sub-solve and the structure of the coupling stay exactly what they were.

Those are three claims, and the suite keeps them separate on purpose:

1. **Numerical convergence** — each thermal step's ``ConvergenceState``. Both
   participants are closed forms, so it is NOT_APPLICABLE and stays so.
2. **Coupling structure** — ``CouplingDirection.ONE_WAY``, because with a
   constant R_int the heat does not depend on the temperature and no fixed
   point exists to iterate toward. It is not a convergence verdict and is not
   computed from one.
3. **Scientific validity** — a per-model ``ValidityAssessment`` per step. This
   is the one that changes.

A run that reported "converged" here would be fabricating a claim about an
iteration that never happened, which is why there is no such field.

The coupled fixture
-------------------
The baseline cell with two changes, each of which the test's own assertions
depend on::

    cell_thermal_conductance   0.02 W/K   so T_ss = 298.15 + 0.1875/0.02
                                          = 307.5 K, a 9.4 K rise
    resistance_temperature_span  5 K      so the declared R_int stops carrying
                                          above 303.15 K

With C = 5 J/K the body's time constant is 250 s and a 120 s step covers about
half of it, so the cell crosses 303.15 K during the third step and the verdict
flips there and stays flipped.
"""

from __future__ import annotations

import pytest

from src.engcore.domains.battery import cell as bat
from src.engcore.domains.battery import context as ctx
from src.engcore.domains.battery import coupling as cp
from src.engcore.domains.battery import models as mdl
from src.engcore.domains.thermal_models import lumped as lump
from src.engcore.scientific.errors import InvalidScientificProblem
from src.engcore.scientific.models.definition import ValidityStatus
from src.engcore.scientific.results.validation import ValidationOutcome
from src.engcore.scientific.solvers.protocol import ConvergenceState
from src.engcore.scientific.units.quantity import Quantity

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
ONE = "dimensionless"

RINT = mdl.RINT_OCV_MODEL.model_id
AMBIENT = Quantity(298.15, K)
HEAT_CAPACITY = Quantity(5.0, "joule/kelvin")


def coupled_cell(**limit_overrides):
    overrides = {
        "cell_thermal_conductance": Quantity(0.02, "watt/kelvin"),
        "resistance_temperature_span": Quantity(5.0, K),
    }
    overrides.update(limit_overrides)
    return build_cell(limits=build_limits(**overrides))


def march(cell=None, load=None, **kwargs):
    return cp.run_self_heating_discharge(
        coupled_cell() if cell is None else cell,
        build_load() if load is None else load,
        heat_capacity=HEAT_CAPACITY,
        ambient_temperature=AMBIENT,
        **{"steps": 8, **kwargs},
    )


# =====================================================================
# The coupled run itself
# =====================================================================

def test_self_heating_raises_the_cell_temperature_toward_its_steady_asymptote():
    """0.1875 W into 0.02 W/K approaches a 9.4 K rise, monotonically."""
    run = march()
    temperatures = [t.magnitude_in(K) for t in run.temperatures()]
    assert temperatures[0] == pytest.approx(298.15)
    assert temperatures == sorted(temperatures)
    # Approaching, never passing, the asymptote the self-heating condition is
    # stated over.
    asymptote = 298.15 + 0.1875 / 0.02
    assert temperatures[-1] < asymptote
    assert temperatures[-1] == pytest.approx(asymptote, rel=0.01)


def test_self_heating_carries_the_cell_out_of_its_validated_domain():
    """The claim this module exists to make, and only this claim.

    The declared R_int carries 5 K either side of 25 degC. Self-heating takes
    the cell past 30 degC during the third step, and from there the Rint
    model's verdict is OUTSIDE_VALIDATED_DOMAIN — not because the arithmetic
    got worse, but because the single resistance the arithmetic uses stopped
    being one the caller declared for this temperature.
    """
    run = march()
    assert run.steps[0].status(RINT) is ValidityStatus.IN_DOMAIN
    flipped = run.first_step_outside(RINT)
    assert flipped is not None
    assert flipped.index == 3
    assert flipped.validity[RINT].violated == (
        ctx.INTERNAL_RESISTANCE_DRIFT_RATIO,
    )
    assert flipped.cell_temperature.magnitude_in(K) > 303.15
    # And it stays flipped: the temperature only rises.
    for step in run.steps[flipped.index - 1 :]:
        assert step.status(RINT) is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN


def test_numerical_convergence_is_unchanged_across_the_whole_march():
    """Claim one, asserted alone.

    Every thermal sub-solve is a closed form. It reports NOT_APPLICABLE on the
    step where the verdict was IN_DOMAIN and on the step where it was OUTSIDE,
    because whether a model applies has nothing to do with whether a solver
    terminated. Asserted per step rather than once, so a value that changed
    halfway through could not hide.
    """
    run = march()
    for step in run.steps:
        assert step.thermal_convergence is ConvergenceState.NOT_APPLICABLE
    assert {step.thermal_convergence for step in run.steps} == {
        ConvergenceState.NOT_APPLICABLE
    }
    # It did not quietly become the success token either.
    assert ConvergenceState.CONVERGED not in {
        step.thermal_convergence for step in run.steps
    }


def test_coupling_structure_is_unchanged_across_the_whole_march():
    """Claim two, asserted alone.

    The dependency is acyclic — a constant R_int makes the heat independent of
    the temperature — so there is no fixed point and nothing to converge. The
    run says so structurally and reports the same thing whether the validity
    verdict flipped or not.
    """
    hot = march()
    cool = march(cell=coupled_cell(cell_thermal_conductance=Quantity(5.0, "watt/kelvin")))
    assert hot.coupling is cp.CouplingDirection.ONE_WAY
    assert cool.coupling is cp.CouplingDirection.ONE_WAY
    assert hot.first_step_outside(RINT) is not None
    assert cool.first_step_outside(RINT) is None
    # Same structure, opposite verdicts.
    assert hot.coupling is cool.coupling


def test_the_three_claims_are_carried_on_three_different_types():
    """The separation, asserted structurally rather than only behaviourally.

    A convergence state, a validation report and a validity assessment are
    three different types on the step record, and the coupling direction is a
    fourth on the run. Collapsing any two would let one stand in for another,
    which is the confusion this whole arrangement exists to prevent.
    """
    from src.engcore.scientific.models.definition import ValidityAssessment
    from src.engcore.scientific.results.validation import ValidationReport

    step = march().final
    assert isinstance(step.thermal_convergence, ConvergenceState)
    assert isinstance(step.thermal_validation, ValidationReport)
    assert isinstance(step.validity[RINT], ValidityAssessment)
    assert isinstance(march().coupling, cp.CouplingDirection)
    # And the coupling direction is not a member of either convergence type.
    assert not isinstance(cp.CouplingDirection.ONE_WAY, ConvergenceState)
    assert cp.CouplingDirection.ONE_WAY.value not in {
        member.value for member in ConvergenceState
    }


def test_the_thermal_sub_solve_is_checked_at_every_step_and_passes():
    """Claim one's sibling: "terminated" and "was checked" are also different.

    The lumped model's own residual check runs on each step and passes,
    including on the steps where the *battery* model is outside its domain. A
    verified answer to an inapplicable model's question is still a verified
    answer, and this is where that is said.
    """
    run = march()
    for step in run.steps:
        assert step.thermal_validation.status is ValidationOutcome.PASS
        residuals = [
            check.residual
            for check in step.thermal_validation.checks
            if check.residual is not None
        ]
        assert residuals and all(r < 1e-6 for r in residuals)


def test_the_coupling_direction_enum_carries_only_the_member_it_executes():
    """A second member would be a name minted for a case nothing produces.

    Nothing here makes the heat depend on the temperature, so no cyclic run
    exists to label ``TWO_WAY``. The sibling electrothermal pack deleted a
    ``DIVERGED`` member on exactly this reasoning; when R_int(T) arrives, the
    member arrives with a run that exercises it.
    """
    assert [member.value for member in cp.CouplingDirection] == ["one_way"]


# =====================================================================
# What the march carries, step by step
# =====================================================================

def test_each_step_records_the_temperature_the_cell_was_actually_evaluated_at():
    """The verdict rests on the start-of-step temperature, and the record says so.

    ``cell_temperature`` is what the cell model saw; ``final_temperature`` is
    where the body ended up and is what the next step starts from. Naming them
    apart is what lets a reader check that a flipped verdict belongs to the
    temperature it was computed at.
    """
    run = march()
    for earlier, later in zip(run.steps, run.steps[1:]):
        assert earlier.final_temperature == later.cell_temperature
        assert earlier.final_state_of_charge == later.state_of_charge


def test_the_state_of_charge_falls_and_the_terminal_voltage_falls_with_it():
    run = march()
    charges = [s.state_of_charge.magnitude_in(ONE) for s in run.steps]
    voltages = [s.terminal_voltage.magnitude_in("volt") for s in run.steps]
    assert charges == sorted(charges, reverse=True)
    assert voltages == sorted(voltages, reverse=True)


def test_the_heat_is_constant_because_r_int_does_not_depend_on_temperature():
    """The reason the coupling is one-way, visible in the numbers.

    Every step dissipates the same 0.1875 W. That is exactly why no fixed
    point exists, and it is a limitation of the model rather than of the
    runner: an R_int(T) would make this vary and would make the coupling
    cyclic. It is recorded in NEEDS.md rather than approximated here.
    """
    run = march()
    heats = [s.heat_generation.magnitude_in("watt") for s in run.steps]
    assert len(set(heats)) == 1
    assert heats[0] == pytest.approx(0.1875)


def test_a_march_stops_at_the_cutoff_rather_than_running_past_it():
    """A cutoff is a stopping rule, and the outcome says which rule stopped it."""
    run = march(
        load=build_load(
            duration=Quantity(600.0, S),
            cutoff_state_of_charge=Quantity(0.70, ONE),
        ),
        steps=20,
    )
    assert run.outcome is cp.MarchOutcome.CUTOFF_REACHED
    assert len(run.steps) < 20
    assert run.final.final_state_of_charge.magnitude_in(ONE) <= 0.70


def test_a_march_can_be_asked_to_stop_when_the_entitlement_stops():
    """Continuing past a lost verdict is the default; stopping is a choice.

    Continuing produces the evidence that a condition *did* flip and where —
    which is what the flip test above needs. A caller who wants the numbers to
    stop when the entitlement to them stops says so, and gets an outcome named
    for that rather than for a cutoff.
    """
    run = march(stop_on_validity_loss=True)
    assert run.outcome is cp.MarchOutcome.VALIDITY_LOST
    assert run.final.status(RINT) is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
    assert len(run.steps) == 3
    for step in run.steps[:-1]:
        assert step.status(RINT) is not ValidityStatus.OUTSIDE_VALIDATED_DOMAIN


def test_first_step_outside_does_not_count_unknown_as_a_violation():
    """UNKNOWN is not a violation, and collapsing them would misreport.

    A cell that never declared a resistance span is not shown to be outside
    anything; it is a cell nobody said enough about. The march reports
    UNKNOWN throughout and names no first offending step.
    """
    silent = coupled_cell(resistance_temperature_span=None)
    run = march(cell=silent)
    assert run.first_step_outside(RINT) is None
    assert run.final.status(RINT) is ValidityStatus.UNKNOWN
    assert ctx.INTERNAL_RESISTANCE_DRIFT_RATIO in run.final.validity[RINT].unknown


def test_every_battery_model_gets_a_verdict_at_every_step():
    run = march()
    for step in run.steps:
        assert set(step.validity) == set(cp.coupled_model_ids())
    with pytest.raises(InvalidScientificProblem, match="no verdict"):
        run.final.status("battery.cell.invented")


# =====================================================================
# What the coupling consumes, and what it refuses
# =====================================================================

def test_the_thermal_body_takes_its_conductance_from_the_cell_s_own_declaration():
    """One number, one place. The condition and the solve must agree.

    The ``hA`` the self-heating condition is stated over and the ``hA`` the
    body exchanges through are the same physical path. Taking them from two
    places would let a run heat at one rate and be judged against another.
    """
    cell = coupled_cell()
    body = cp.thermal_body_for(
        cell,
        heat_capacity=HEAT_CAPACITY,
        ambient_temperature=AMBIENT,
        initial_temperature=AMBIENT,
        step_duration=Quantity(120.0, S),
    )
    assert isinstance(body, lump.ThermalBody)
    assert body.ambient_conductance == cell.limits.cell_thermal_conductance


def test_a_cell_that_declares_no_cooling_path_cannot_be_coupled():
    """There is no second source for that number, and none is invented.

    Defaulting it would make the coupled temperature rise a function of a
    value nobody declared, and would make the self-heating condition — which
    would be UNKNOWN — disagree with a run that had proceeded anyway.
    """
    silent = build_cell(limits=build_limits(cell_thermal_conductance=None))
    with pytest.raises(InvalidScientificProblem, match="cannot be coupled"):
        march(cell=silent)


def test_the_march_starts_the_body_where_the_load_says_the_cell_is():
    """The only consistent starting point, and it is not assumed silently."""
    load = build_load(cell_temperature=Quantity(283.15, K))
    run = march(load=load)
    assert run.steps[0].cell_temperature == load.cell_temperature
    # And an explicit override is honoured.
    elsewhere = march(load=load, initial_temperature=Quantity(310.0, K))
    assert elsewhere.steps[0].cell_temperature == Quantity(310.0, K)


def test_a_march_of_zero_steps_is_refused_rather_than_returning_an_empty_run():
    """A run that executed nothing is not a run, and must not look like one."""
    with pytest.raises(InvalidScientificProblem, match="at least one step"):
        march(steps=0)


def test_a_march_past_its_step_limit_is_refused_rather_than_truncated():
    """Silently returning fewer steps than asked for would misreport the horizon."""
    with pytest.raises(InvalidScientificProblem, match="raise the limit"):
        march(steps=50, step_limit=10)


def test_the_coupling_module_reimplements_nothing_from_the_thermal_domain():
    """It consumes the public API and modifies nothing.

    The thermal sub-solve is built, bound, solved, interpreted and validated
    entirely by ``thermal_models.lumped``. This module reads three values out
    of it. Nothing under ``systems/electrothermal`` is imported or duplicated.
    """
    import ast
    import inspect

    # Asserted over the module's *imports*, not over its prose: the docstring
    # names ``systems/electrothermal`` precisely in order to say it is not
    # touched, and a scan that could not tell those apart would forbid the
    # explanation along with the thing it explains.
    tree = ast.parse(inspect.getsource(cp))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            imported.append(node.module or "")
    assert not [name for name in imported if "systems" in name], imported
    assert not [name for name in imported if "electrothermal" in name], imported
    # What it does import from the thermal domain is that domain's public API.
    assert any("thermal_models" in name for name in imported)

    source = inspect.getsource(cp)
    for used in (
        "build_lumped_thermal_problem",
        "LumpedThermalSolver",
        "ThermalBody",
    ):
        assert used in source


def test_a_coupled_run_and_a_standalone_assessment_agree_at_the_same_point():
    """The march is a sequence of ordinary assessments, not a second mechanism.

    Whatever the coupled runner reports at a step must be exactly what
    ``assess_all`` reports for the same cell at the same operating point. A
    coupling that computed its own verdicts would be a second place for the
    domain's rules to live.
    """
    cell = coupled_cell()
    run = march(cell=cell)
    step = run.steps[2]
    standalone = bat.assess_all(
        bat.build_battery_problem(
            cell,
            build_load().at(
                state_of_charge=step.state_of_charge,
                cell_temperature=step.cell_temperature,
            ),
        ),
        state_of_charge=step.state_of_charge,
        discharge_current=build_load().current,
        cell_temperature=step.cell_temperature,
    )
    assert standalone == dict(step.validity)
