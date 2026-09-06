"""When the cell models apply, and when they only appear to.

Fourteen applicability conditions plus one consistency condition, each with
three tests — inside, outside, and without the declaration that would settle
it. The third is the one that matters most: a model answering IN_DOMAIN when
nobody told it the cell's continuous rating would be reporting the *absence of
evidence* as evidence, and the platform's whole claim is that it does not.

Each OUTSIDE test pushes exactly one condition out of *its own model's* domain
and asserts that model's ``violated`` tuple, so a threshold moved by accident
cannot hide behind a neighbour's failure. Where an excursion legitimately
violates a condition on a *different* model too — a hot cell is outside both
its discharge range and its capacity rating's span — the test says so rather
than arranging the numbers to hide it.
"""

from __future__ import annotations

import pytest

from src.engcore.domains.battery import cell as bat
from src.engcore.domains.battery import context as ctx
from src.engcore.domains.battery import models as mdl
from src.engcore.scientific.models.definition import (
    RangeCondition,
    ScientificModelDefinition,
    ValidityDomain,
    ValidityStatus,
)
from src.engcore.scientific.errors import InvalidScientificProblem
from src.engcore.scientific.ir.problem import ScientificProblem
from src.engcore.scientific.ir.variables import ScientificParameter
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
V = "volt"
ONE = "dimensionless"
C_RATE = "1/hour"

RINT = mdl.RINT_OCV_MODEL.model_id
COULOMB = mdl.COULOMB_COUNTING_MODEL.model_id
RUNTIME = mdl.CONSTANT_CURRENT_RUNTIME_MODEL.model_id
PEUKERT = mdl.PEUKERT_DERATING_MODEL.model_id


def condition_of(model: ScientificModelDefinition, name: str) -> RangeCondition:
    return next(c for c in model.validity.conditions if c.name == name)

# =====================================================================
# The baseline: everything decidable, everything satisfied
# =====================================================================

def test_a_fully_declared_cell_at_a_benign_operating_point_is_in_domain():
    """All four models, all conditions decided, none violated."""
    verdicts = assess_models(make_cell(), make_load())
    for model in mdl.BATTERY_MODELS:
        assessment = verdicts[model.model_id]
        assert assessment.status is ValidityStatus.IN_DOMAIN, model.model_id
        assert assessment.violated == ()
        assert assessment.unknown == ()
        # Every declared condition actually ran; none was skipped into silence.
        assert set(assessment.satisfied) == {
            c.name for c in model.validity.conditions
        }


def test_a_cell_that_declares_nothing_beyond_its_five_numbers_is_unknown():
    """The gap this domain closes, stated as one assertion.

    A cell described only by its capacity, resistance, chord and efficiency
    can be *evaluated* — the arithmetic needs nothing else — and supports no
    applicability verdict at all. It reports UNKNOWN, and every condition it
    cannot answer is named.
    """
    bare = make_cell(limits=ctx.CellLimits())
    load = make_load(
        pulse_current=None,
        pulse_duration=None,
        cutoff_voltage=None,
        cutoff_state_of_charge=None,
    )
    verdicts = assess_models(bare, load)

    assert verdicts[RINT].status is ValidityStatus.UNKNOWN
    assert set(verdicts[RINT].unknown) == {
        ctx.CONTINUOUS_C_RATE_UTILIZATION,
        ctx.PULSE_C_RATE_UTILIZATION,
        ctx.PULSE_DURATION_UTILIZATION,
        ctx.SOC_WINDOW_MARGIN,
        ctx.DISCHARGE_TEMPERATURE_POSITION,
        ctx.INTERNAL_RESISTANCE_DRIFT_RATIO,
        ctx.SELF_HEATING_RISE_RATIO,
        ctx.POLARIZATION_UNMODELLED_FRACTION,
    }
    # The positivity checks still pass, and still prove nothing about whether
    # the Rint representation applies to this cell.
    assert set(verdicts[RINT].satisfied) == {
        ctx.NOMINAL_CAPACITY,
        ctx.INTERNAL_RESISTANCE,
        ctx.TERMINAL_VOLTAGE_RATIO,
    }

    assert verdicts[COULOMB].status is ValidityStatus.UNKNOWN
    assert set(verdicts[COULOMB].unknown) == {
        ctx.SOC_STEP_RESOLUTION_RATIO,
        ctx.CAPACITY_TEMPERATURE_DRIFT_RATIO,
        ctx.SOC_WINDOW_MARGIN,
    }
    assert verdicts[RUNTIME].status is ValidityStatus.UNKNOWN
    assert verdicts[PEUKERT].status is ValidityStatus.UNKNOWN
    for assessment in verdicts.values():
        assert assessment.violated == ()


# =====================================================================
# Condition 1 — continuous C-rate against the cell's continuous rating
# =====================================================================

def test_the_cell_model_accepts_a_discharge_inside_its_continuous_c_rate():
    """2.5 A from a 2.5 Ah cell is 1C against a 2C rating: half the budget."""
    verdicts = assess_models(make_cell(), make_load())
    assert ctx.CONTINUOUS_C_RATE_UTILIZATION in verdicts[RINT].satisfied
    assert verdicts[RINT].status is ValidityStatus.IN_DOMAIN


def test_the_cell_model_rejects_a_discharge_above_its_declared_continuous_c_rate():
    """5.5 A is 2.2C against a 2C rating: ten percent past the rating.

    The single most common way an AI-produced cell sizing is wrong — a current
    the arithmetic delivers and the cell does not. The circuit still evaluates
    perfectly; what fails is the entitlement to the answer.
    """
    verdicts = assess_models(make_cell(), make_load(current=Quantity(5.5, A)))
    assert verdicts[RINT].status is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
    assert verdicts[RINT].violated == (ctx.CONTINUOUS_C_RATE_UTILIZATION,)


def test_the_continuous_c_rate_is_unknown_when_the_cell_declares_no_rating():
    """No rating, no verdict. An undeclared limit is never an absent limit."""
    cell = make_cell(limits=make_limits(continuous_discharge_c_rate=None))
    verdicts = assess_models(cell, make_load())
    assert verdicts[RINT].status is ValidityStatus.UNKNOWN
    assert ctx.CONTINUOUS_C_RATE_UTILIZATION in verdicts[RINT].unknown
    assert verdicts[RINT].violated == ()
    # And the runtime model, which shares the condition, is UNKNOWN too.
    assert ctx.CONTINUOUS_C_RATE_UTILIZATION in verdicts[RUNTIME].unknown


def test_the_continuous_c_rate_bound_is_a_named_definitional_constant():
    condition = condition_of(mdl.RINT_OCV_MODEL, ctx.CONTINUOUS_C_RATE_UTILIZATION)
    assert condition.maximum == mdl.RATING_UTILIZATION_LIMIT
    assert condition.minimum is None
    assert mdl.RATING_UTILIZATION_LIMIT.magnitude_in(ONE) == 1.0
    assert "definitional" in condition.description


# =====================================================================
# Condition 2 — peak C-rate against the cell's pulse rating
# =====================================================================

def test_the_cell_model_accepts_a_pulse_inside_its_declared_pulse_c_rate():
    """An 8 A peak from a 2.5 Ah cell is 3.2C against a 10C pulse rating."""
    verdicts = assess_models(make_cell(), make_load())
    assert ctx.PULSE_C_RATE_UTILIZATION in verdicts[RINT].satisfied


def test_the_cell_model_rejects_a_pulse_above_its_declared_pulse_c_rate():
    """30 A is 12C against a 10C pulse rating, while the continuous draw is 1C.

    The two ratings fail independently, which is why they are two conditions:
    a duty can sit comfortably inside the continuous rating and still ask the
    cell for a peak it is not rated to deliver.
    """
    verdicts = assess_models(
        make_cell(), make_load(pulse_current=Quantity(30.0, A))
    )
    assert verdicts[RINT].status is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
    assert verdicts[RINT].violated == (ctx.PULSE_C_RATE_UTILIZATION,)
    assert ctx.CONTINUOUS_C_RATE_UTILIZATION in verdicts[RINT].satisfied


def test_the_pulse_c_rate_is_unknown_when_the_duty_declares_no_pulse():
    """A duty with no declared pulse does not thereby pass the pulse condition.

    This is the omission case that matters most for a pulsed load: silence
    about the peak is not a claim that there is no peak.
    """
    verdicts = assess_models(make_cell(), make_load(pulse_current=None))
    assert verdicts[RINT].status is ValidityStatus.UNKNOWN
    assert ctx.PULSE_C_RATE_UTILIZATION in verdicts[RINT].unknown
    assert verdicts[RINT].violated == ()


def test_the_pulse_c_rate_is_also_unknown_when_the_cell_declares_no_pulse_rating():
    """Either half of the comparison being absent leaves it unanswered."""
    cell = make_cell(limits=make_limits(pulse_discharge_c_rate=None))
    verdicts = assess_models(cell, make_load())
    assert ctx.PULSE_C_RATE_UTILIZATION in verdicts[RINT].unknown
    assert verdicts[RINT].violated == ()


# =====================================================================
# Condition 3 — pulse duration against the duration the rating is published at
# =====================================================================

def test_the_cell_model_accepts_a_pulse_shorter_than_its_rated_pulse():
    """A 5 s pulse against a rating published for 10 s: half the budget."""
    verdicts = assess_models(make_cell(), make_load())
    assert ctx.PULSE_DURATION_UTILIZATION in verdicts[RINT].satisfied


def test_the_cell_model_rejects_a_pulse_longer_than_its_rating_was_measured_over():
    """A 20 s pulse against a 10 s rating, at a peak current well inside it.

    A peak rating is meaningless without its duration: what it bounds is the
    heat deposited and the overpotential reached during the pulse, and both
    grow with its length. The current condition passes and this one does not.
    """
    verdicts = assess_models(
        make_cell(), make_load(pulse_duration=Quantity(20.0, S))
    )
    assert verdicts[RINT].status is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
    assert verdicts[RINT].violated == (ctx.PULSE_DURATION_UTILIZATION,)
    assert ctx.PULSE_C_RATE_UTILIZATION in verdicts[RINT].satisfied


def test_the_pulse_duration_is_unknown_when_the_cell_declares_no_rated_duration():
    cell = make_cell(limits=make_limits(rated_pulse_duration=None))
    verdicts = assess_models(cell, make_load())
    assert verdicts[RINT].status is ValidityStatus.UNKNOWN
    assert ctx.PULSE_DURATION_UTILIZATION in verdicts[RINT].unknown
    assert verdicts[RINT].violated == ()


# =====================================================================
# Condition 4 — the state-of-charge window
# =====================================================================

def test_the_cell_model_accepts_a_discharge_inside_the_declared_soc_window():
    """0.90 down to 0.867 sits inside a declared 0.10-0.95 window."""
    verdicts = assess_models(make_cell(), make_load())
    assert ctx.SOC_WINDOW_MARGIN in verdicts[RINT].satisfied
    assert ctx.SOC_WINDOW_MARGIN in verdicts[COULOMB].satisfied
    assert ctx.SOC_WINDOW_MARGIN in verdicts[RUNTIME].satisfied


def test_the_cell_model_rejects_a_discharge_starting_above_its_usable_window():
    """Starting at 0.99 against a declared 0.95 ceiling.

    Near full, the affine OCV chord is furthest from the plateau it is
    replacing and a constant R_int is least defensible. The condition catches
    the *whole trajectory* leaving the window, not just its end, which is why
    a run that starts outside and finishes inside is still outside.
    """
    verdicts = assess_models(
        make_cell(), make_load(initial_state_of_charge=Quantity(0.99, ONE))
    )
    assert verdicts[RINT].status is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
    assert verdicts[RINT].violated == (ctx.SOC_WINDOW_MARGIN,)
    # Shared with the other two models, each for its own reason.
    assert verdicts[COULOMB].violated == (ctx.SOC_WINDOW_MARGIN,)
    assert verdicts[RUNTIME].violated == (ctx.SOC_WINDOW_MARGIN,)


def test_the_soc_window_is_unknown_when_the_cell_declares_no_lower_edge():
    """One edge missing leaves the window undefined, not one-sided."""
    cell = make_cell(limits=make_limits(usable_soc_minimum=None))
    verdicts = assess_models(cell, make_load())
    assert verdicts[RINT].status is ValidityStatus.UNKNOWN
    assert ctx.SOC_WINDOW_MARGIN in verdicts[RINT].unknown
    assert ctx.SOC_WINDOW_MARGIN in verdicts[COULOMB].unknown
    assert verdicts[RINT].violated == ()


# =====================================================================
# Condition 5 — cell temperature within the declared discharge range
# =====================================================================

def test_the_cell_model_accepts_a_cell_inside_its_declared_discharge_range():
    """25 degC sits 56 % of the way up a declared -20 to +60 degC range."""
    verdicts = assess_models(make_cell(), make_load())
    assert ctx.DISCHARGE_TEMPERATURE_POSITION in verdicts[RINT].satisfied


def test_the_cell_model_rejects_a_cell_hotter_than_its_declared_discharge_range():
    """70 degC against a declared 60 degC ceiling.

    The capacity rating's own temperature span is also exceeded here, on the
    coulomb-counting model — which is correct and is asserted rather than
    arranged away: a cell that hot is outside two different declarations at
    once, and a reader must be able to see both.
    """
    verdicts = assess_models(
        make_cell(), make_load(cell_temperature=Quantity(343.15, K))
    )
    assert verdicts[RINT].status is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
    assert verdicts[RINT].violated == (ctx.DISCHARGE_TEMPERATURE_POSITION,)
    assert ctx.INTERNAL_RESISTANCE_DRIFT_RATIO in verdicts[RINT].satisfied
    assert verdicts[COULOMB].violated == (ctx.CAPACITY_TEMPERATURE_DRIFT_RATIO,)


def test_the_cell_model_rejects_a_cell_colder_than_its_declared_discharge_range():
    """-30 degC against a declared -20 degC floor. The range is two-sided."""
    verdicts = assess_models(
        make_cell(), make_load(cell_temperature=Quantity(243.15, K))
    )
    assert verdicts[RINT].status is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
    assert ctx.DISCHARGE_TEMPERATURE_POSITION in verdicts[RINT].violated


def test_the_discharge_range_is_unknown_when_the_cell_declares_no_upper_edge():
    cell = make_cell(limits=make_limits(maximum_discharge_temperature=None))
    verdicts = assess_models(cell, make_load())
    assert verdicts[RINT].status is ValidityStatus.UNKNOWN
    assert ctx.DISCHARGE_TEMPERATURE_POSITION in verdicts[RINT].unknown
    assert verdicts[RINT].violated == ()


def test_the_discharge_range_condition_says_it_models_discharge_only():
    """The narrower charge range is not modelled, and the record says so.

    A cell's charge temperature range is narrower than its discharge range,
    most sharply at the cold end. This domain declares only the discharge
    range, so a caller charging the cell is outside the whole domain rather
    than outside this condition — and no condition here would catch it. The
    description must keep saying that rather than implying coverage.
    """
    description = condition_of(
        mdl.RINT_OCV_MODEL, ctx.DISCHARGE_TEMPERATURE_POSITION
    ).description
    assert "DISCHARGE ONLY" in description
    assert "charge temperature range is narrower" in description


# =====================================================================
# Condition 6 — internal-resistance temperature drift
# =====================================================================

def test_the_cell_model_accepts_operation_at_the_temperature_r_int_was_measured():
    """The declared R_int reference is 25 degC and the cell is at 25 degC."""
    verdicts = assess_models(make_cell(), make_load())
    assert ctx.INTERNAL_RESISTANCE_DRIFT_RATIO in verdicts[RINT].satisfied


def test_the_cell_model_rejects_operation_outside_the_span_r_int_was_declared_over():
    """A 2 K span around 25 degC, evaluated at 32 degC.

    Expressed by narrowing the *span* rather than by moving far in
    temperature, so the discharge-range condition stays satisfied and this
    test is about one thing. A cell's R_int is dominated by thermally
    activated processes; declaring a narrow span is how a caller says their
    single measured value does not carry far.
    """
    cell = make_cell(limits=make_limits(resistance_temperature_span=Quantity(2.0, K)))
    verdicts = assess_models(
        cell, make_load(cell_temperature=Quantity(305.15, K))
    )
    assert verdicts[RINT].status is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
    assert verdicts[RINT].violated == (ctx.INTERNAL_RESISTANCE_DRIFT_RATIO,)
    assert ctx.DISCHARGE_TEMPERATURE_POSITION in verdicts[RINT].satisfied


def test_the_r_int_drift_is_unknown_when_the_cell_declares_no_span():
    """A reference temperature with no span states where, not how far."""
    cell = make_cell(limits=make_limits(resistance_temperature_span=None))
    verdicts = assess_models(cell, make_load())
    assert verdicts[RINT].status is ValidityStatus.UNKNOWN
    assert ctx.INTERNAL_RESISTANCE_DRIFT_RATIO in verdicts[RINT].unknown
    assert verdicts[RINT].violated == ()


# =====================================================================
# Condition 7 — self-heating against the declared cooling
# =====================================================================

def test_the_cell_model_accepts_self_heating_inside_the_declared_isothermal_budget():
    """0.1875 W into 0.15 W/K implies 1.25 K against a declared 15 K budget."""
    verdicts = assess_models(make_cell(), make_load())
    assert ctx.SELF_HEATING_RISE_RATIO in verdicts[RINT].satisfied


def test_the_cell_model_rejects_self_heating_beyond_its_isothermal_assumption():
    """The same dissipation into 0.005 W/K implies 37.5 K, past a 15 K budget.

    Nothing about the current changed: the cell is still at 1C, still inside
    its rating and still at 25 degC when assessed. What changed is that the
    heat it makes has nowhere to go, so the single temperature every model
    here assigns it stops describing it.
    """
    cell = make_cell(
        limits=make_limits(cell_thermal_conductance=Quantity(0.005, "watt/kelvin"))
    )
    verdicts = assess_models(cell, make_load())
    assert verdicts[RINT].status is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
    assert verdicts[RINT].violated == (ctx.SELF_HEATING_RISE_RATIO,)
    assert ctx.CONTINUOUS_C_RATE_UTILIZATION in verdicts[RINT].satisfied


def test_the_self_heating_rise_is_unknown_when_the_cell_declares_no_conductance():
    """No cooling path declared, no implied rise, no verdict."""
    cell = make_cell(limits=make_limits(cell_thermal_conductance=None))
    verdicts = assess_models(cell, make_load())
    assert verdicts[RINT].status is ValidityStatus.UNKNOWN
    assert ctx.SELF_HEATING_RISE_RATIO in verdicts[RINT].unknown
    assert verdicts[RINT].violated == ()


# =====================================================================
# Condition 8 — the interval against the relaxation the model omits
# =====================================================================

def test_the_cell_model_accepts_an_interval_that_outlasts_the_omitted_relaxation():
    """A 120 s interval against a declared 30 s polarization time constant.

    t = 4 tau, so f = 1 - exp(-4) = 0.982 and the unmodelled remainder is
    0.018 — the settled regime.
    """
    verdicts = assess_models(make_cell(), make_load())
    assert ctx.POLARIZATION_UNMODELLED_FRACTION in verdicts[RINT].satisfied


def test_the_cell_model_accepts_a_pulse_far_shorter_than_the_relaxation():
    """A 1 s interval against a 30 s time constant, which the floor rejected.

    This is the case the old one-sided condition got wrong. At t = tau/30 the
    diffusion overpotential has reached 3.3 % of its asymptote: the branch the
    Rint circuit omits has barely begun, and the terminal voltage is
    essentially the instantaneous ohmic drop that a short-pulse R_int
    represents. A constant resistance is defensible here for the opposite
    reason it is defensible when settled, and the previous ``t/tau >= 3``
    floor excluded the whole regime.
    """
    verdicts = assess_models(make_cell(), make_load(duration=Quantity(1.0, S)))
    assert ctx.POLARIZATION_UNMODELLED_FRACTION in verdicts[RINT].satisfied
    assert ctx.POLARIZATION_UNMODELLED_FRACTION not in verdicts[RINT].violated
    # And it is genuinely the short side, not an accident of the fold: the
    # ratio the old floor tested is well below 1, not above 3.
    ratio = ctx.polarization_settling_ratio(
        duration=Quantity(1.0, S), time_constant=Quantity(30.0, S)
    )
    assert ratio.magnitude_in(ONE) < 1.0
    unmodelled = ctx.polarization_unmodelled_fraction(
        duration=Quantity(1.0, S), time_constant=Quantity(30.0, S)
    )
    assert unmodelled.magnitude_in(ONE) < 0.05


def test_the_cell_model_rejects_an_interval_comparable_to_the_relaxation():
    """A 30 s interval against a 30 s time constant: the excluded middle.

    At t = tau the diffusion overpotential is 63 % developed and still moving
    fast. It is neither absent nor constant across the interval, so no single
    resistance reproduces the terminal voltage. This is the band the condition
    removes — and the only band it removes.
    """
    verdicts = assess_models(make_cell(), make_load(duration=Quantity(30.0, S)))
    assert verdicts[RINT].status is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
    assert verdicts[RINT].violated == (ctx.POLARIZATION_UNMODELLED_FRACTION,)


def test_the_settling_ratio_is_unknown_when_the_cell_declares_no_time_constant():
    cell = make_cell(limits=make_limits(polarization_time_constant=None))
    verdicts = assess_models(cell, make_load())
    assert verdicts[RINT].status is ValidityStatus.UNKNOWN
    assert ctx.POLARIZATION_UNMODELLED_FRACTION in verdicts[RINT].unknown
    assert verdicts[RINT].violated == ()


def test_the_polarization_ceiling_is_labelled_a_convention_and_not_a_citation():
    """The one non-definitional number in the domain, and it admits it.

    Five per cent is the engineering reading of "done" for a first-order
    response. No source in this repository's bibliography prints it as a
    threshold for this quantity, and the constant, the condition description,
    the documentation row and this test all say so. The physics behind the
    condition *is* cited; the number is not, and the two must not be confused
    — which is the mistake the applicability review caught once already in a
    sibling domain.
    """
    assert mdl.POLARIZATION_UNMODELLED_CEILING.magnitude_in(ONE) == 0.05
    condition = condition_of(
        mdl.RINT_OCV_MODEL, ctx.POLARIZATION_UNMODELLED_FRACTION
    )
    assert condition.maximum == mdl.POLARIZATION_UNMODELLED_CEILING
    assert condition.minimum is None
    # The admission, in the condition a reader will actually look at.
    assert "CONVENTION AND NOT A CITED THRESHOLD" in condition.description
    assert "no source in this repository does either" in condition.description
    # Both regimes are named, and both bounds are called conventions.
    assert "TWO REGIMES ARE ADMISSIBLE" in condition.description
    assert "BOTH resulting bounds" in condition.description
    assert "t >= 3.0 tau_pol" in condition.description
    assert "t <= 0.051 tau_pol" in condition.description
    # The physics is cited even though the number is not.
    assert "Plett" in condition.description
    assert "Plett prints no threshold" in condition.description
    # And the honest reading of a failure, which must not become an overclaim.
    assert "not shown to be wrong" in condition.description
    # The limit the condition does not check, stated rather than implied.
    assert "characterised in the regime it is being used in" in condition.description


def test_every_other_threshold_in_the_domain_is_definitional():
    """Fifteen of sixteen bounds are 1 or 0, and that is checkable.

    "You have consumed all of the budget you declared" and "you are on the
    edge of the interval you declared" need no citation, because the number is
    a consequence of how the ratio was defined. This test is what stops a
    tuned constant from being added later without anyone noticing that the
    domain suddenly carries an uncited number.
    """
    definitional = {
        mdl.RATING_UTILIZATION_LIMIT,
        mdl.DECLARED_BUDGET_LIMIT,
        mdl.WINDOW_MARGIN_FLOOR,
        mdl.TEMPERATURE_POSITION_FLOOR,
        mdl.TEMPERATURE_POSITION_CEILING,
        mdl.MINIMUM_TERMINAL_VOLTAGE_RATIO,
        mdl.STEP_RESOLUTION_LIMIT,
        mdl.CUTOFF_CONSISTENCY_FLOOR,
        mdl.PEUKERT_DERATING_LIMIT,
    }
    for bound in definitional:
        assert bound.magnitude_in(ONE) in (0.0, 1.0), bound

    every_bound = {
        bound
        for model in mdl.BATTERY_MODELS
        for condition in model.validity.conditions
        for bound in (condition.minimum, condition.maximum)
        if bound is not None and bound.units == ONE
    }
    # Exactly one dimensionless bound in the whole domain is neither 0 nor 1,
    # and it is the one labelled a convention.
    exceptional = {b for b in every_bound if b.magnitude_in(ONE) not in (0.0, 1.0)}
    assert exceptional == {mdl.POLARIZATION_UNMODELLED_CEILING}


# =====================================================================
# Condition 9 — terminal-voltage admissibility (consistency, not applicability)
# =====================================================================

def test_the_cell_model_accepts_an_ohmic_drop_that_leaves_a_positive_terminal():
    verdicts = assess_models(make_cell(), make_load())
    assert ctx.TERMINAL_VOLTAGE_RATIO in verdicts[RINT].satisfied


def test_the_cell_model_rejects_an_ohmic_drop_that_reverses_the_terminal_voltage():
    """A 2 ohm series resistance at 2.5 A drops 5 V from a 4.04 V chord.

    Past the crossing the expression does not describe a deeply loaded cell,
    it describes one sourcing current at a negative terminal voltage. The
    conductance is raised alongside so the self-heating condition stays
    satisfied and this test is about the one thing it names.
    """
    cell = make_cell(
        internal_resistance=Quantity(2.0, "ohm"),
        limits=make_limits(cell_thermal_conductance=Quantity(5.0, "watt/kelvin")),
    )
    verdicts = assess_models(cell, make_load())
    assert verdicts[RINT].status is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
    assert verdicts[RINT].violated == (ctx.TERMINAL_VOLTAGE_RATIO,)


def test_the_terminal_voltage_ratio_is_unknown_without_an_operating_point():
    """No current supplied, no terminal voltage, no verdict on it.

    Unlike every other condition here, this one needs no optional declaration
    — only the state and the control. Withholding those is the omission that
    makes it UNKNOWN, and it is still UNKNOWN and never IN_DOMAIN.
    """
    verdicts = assess_models(make_cell(), make_load(), discharge_current=None)
    assert verdicts[RINT].status is ValidityStatus.UNKNOWN
    assert ctx.TERMINAL_VOLTAGE_RATIO in verdicts[RINT].unknown
    assert verdicts[RINT].violated == ()


# =====================================================================
# Condition 10 — the step's state-of-charge resolution
# =====================================================================

def test_the_counter_accepts_a_step_that_resolves_the_charge_it_moves():
    """A two-minute step moves 0.033 of the charge against a 0.10 resolution."""
    verdicts = assess_models(make_cell(), make_load())
    assert ctx.SOC_STEP_RESOLUTION_RATIO in verdicts[COULOMB].satisfied


def test_the_counter_rejects_a_step_that_traverses_more_charge_than_it_resolves():
    """A fifteen-minute step moves 0.2475 against a declared 0.10 resolution.

    The integral itself is still exact. What is unrepresented is everything
    the step holds fixed while the charge moves: the OCV and terminal voltage
    are evaluated once, at one state of charge, and both are functions of it.
    """
    verdicts = assess_models(make_cell(), make_load(duration=Quantity(900.0, S)))
    assert verdicts[COULOMB].status is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
    assert verdicts[COULOMB].violated == (ctx.SOC_STEP_RESOLUTION_RATIO,)


def test_the_step_resolution_is_unknown_when_the_caller_declares_none():
    cell = make_cell(limits=make_limits(soc_step_resolution=None))
    verdicts = assess_models(cell, make_load())
    assert verdicts[COULOMB].status is ValidityStatus.UNKNOWN
    assert ctx.SOC_STEP_RESOLUTION_RATIO in verdicts[COULOMB].unknown
    assert verdicts[COULOMB].violated == ()


# =====================================================================
# Condition 11 — capacity rating temperature drift
# =====================================================================

def test_the_counter_accepts_a_cell_near_the_temperature_its_capacity_was_rated():
    """25 degC against a 20 degC rating reference and a 20 K span."""
    verdicts = assess_models(make_cell(), make_load())
    assert ctx.CAPACITY_TEMPERATURE_DRIFT_RATIO in verdicts[COULOMB].satisfied


def test_the_counter_rejects_a_cell_far_from_the_temperature_its_capacity_was_rated():
    """A 2 K span around 20 degC, evaluated at 32 degC.

    The counter divides by Q_nom, and Q_nom is a measurement under stated
    conditions. Normalizing by a rating taken somewhere else reports a state
    of charge against a capacity the cell does not have. Distinct from the
    R_int drift condition: the resistance span here is the wide baseline one
    and stays satisfied.
    """
    cell = make_cell(limits=make_limits(capacity_temperature_span=Quantity(2.0, K)))
    verdicts = assess_models(cell, make_load(cell_temperature=Quantity(305.15, K)))
    assert verdicts[COULOMB].status is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
    assert verdicts[COULOMB].violated == (ctx.CAPACITY_TEMPERATURE_DRIFT_RATIO,)
    assert ctx.INTERNAL_RESISTANCE_DRIFT_RATIO in verdicts[RINT].satisfied


def test_the_capacity_drift_is_unknown_when_the_cell_declares_no_rating_reference():
    cell = make_cell(limits=make_limits(capacity_reference_temperature=None))
    verdicts = assess_models(cell, make_load())
    assert verdicts[COULOMB].status is ValidityStatus.UNKNOWN
    assert ctx.CAPACITY_TEMPERATURE_DRIFT_RATIO in verdicts[COULOMB].unknown
    assert verdicts[COULOMB].violated == ()


# =====================================================================
# Condition 12 — consistency of the two declared cutoffs
# =====================================================================

def test_the_runtime_model_accepts_two_cutoffs_that_agree_at_this_load():
    """A 3.0 V cutoff bites at SoC 0.0625; the declared SoC cutoff is 0.15."""
    verdicts = assess_models(make_cell(), make_load())
    assert ctx.CUTOFF_CONSISTENCY_MARGIN in verdicts[RUNTIME].satisfied


def test_the_runtime_model_rejects_a_depth_of_discharge_the_voltage_cutoff_forbids():
    """A 3.9 V cutoff bites at SoC 0.81, well above the declared 0.15 target.

    The failure this catches is a silently over-reported runtime: a time
    computed to the declared depth of discharge is only that time if the cell
    can reach it, and here the voltage limit stops the run with two thirds of
    the charge still in the cell.
    """
    verdicts = assess_models(
        make_cell(), make_load(cutoff_voltage=Quantity(3.9, V))
    )
    assert verdicts[RUNTIME].status is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
    assert verdicts[RUNTIME].violated == (ctx.CUTOFF_CONSISTENCY_MARGIN,)


def test_the_cutoff_consistency_is_unknown_when_only_one_cutoff_is_declared():
    """Declaring one cutoff does not make the two consistent — there is no two.

    This is the omission case with the sharpest consequence: a caller who
    declares only a state-of-charge cutoff gets a runtime, and gets UNKNOWN
    rather than IN_DOMAIN on whether the cell's voltage would have allowed it.
    """
    verdicts = assess_models(make_cell(), make_load(cutoff_voltage=None))
    assert verdicts[RUNTIME].status is ValidityStatus.UNKNOWN
    assert ctx.CUTOFF_CONSISTENCY_MARGIN in verdicts[RUNTIME].unknown
    assert verdicts[RUNTIME].violated == ()


# =====================================================================
# Condition 13 — Peukert extrapolation in current
# =====================================================================

def test_the_peukert_model_accepts_a_current_inside_the_decades_it_was_fitted_over():
    """2.5 A is 0.70 decades from a 0.5 A reference, inside a declared decade."""
    verdicts = assess_models(make_cell(), make_load())
    assert ctx.PEUKERT_EXTRAPOLATION_RATIO in verdicts[PEUKERT].satisfied


def test_the_peukert_model_rejects_a_current_outside_the_decades_it_was_fitted_over():
    """The same current against a fit declared to cover only 0.3 decades.

    The exponent is not a constant of the cell: it is extracted over a range
    of currents and moves with them. Using the law far outside that range
    extrapolates a fit whose own parameter has changed.
    """
    cell = make_cell(limits=make_limits(peukert_fit_decades=Quantity(0.3, ONE)))
    verdicts = assess_models(cell, make_load())
    assert verdicts[PEUKERT].status is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
    assert verdicts[PEUKERT].violated == (ctx.PEUKERT_EXTRAPOLATION_RATIO,)


def test_the_peukert_extrapolation_is_unknown_when_no_fit_reach_is_declared():
    cell = make_cell(limits=make_limits(peukert_fit_decades=None))
    verdicts = assess_models(cell, make_load())
    assert verdicts[PEUKERT].status is ValidityStatus.UNKNOWN
    assert ctx.PEUKERT_EXTRAPOLATION_RATIO in verdicts[PEUKERT].unknown
    assert verdicts[PEUKERT].violated == ()


# =====================================================================
# Condition 14 — the Peukert derating may only derate
# =====================================================================

def test_the_peukert_model_accepts_a_derating_below_the_nominal_capacity():
    """At 2.5 A against a 0.5 A reference the law predicts 92 % of nominal."""
    verdicts = assess_models(make_cell(), make_load())
    assert ctx.PEUKERT_CAPACITY_RATIO in verdicts[PEUKERT].satisfied


def test_the_peukert_model_rejects_a_predicted_capacity_above_the_cell_rating():
    """At 0.1 A, below the 0.5 A reference, the law predicts 108 % of nominal.

    That is not a conservative error: it is the formula read outside the
    direction it means anything in. The extrapolation condition still passes
    at 0.7 decades, so the two failures are genuinely separate.
    """
    verdicts = assess_models(make_cell(), make_load(current=Quantity(0.1, A)))
    assert verdicts[PEUKERT].status is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
    assert verdicts[PEUKERT].violated == (ctx.PEUKERT_CAPACITY_RATIO,)
    assert ctx.PEUKERT_EXTRAPOLATION_RATIO in verdicts[PEUKERT].satisfied


def test_the_peukert_capacity_ratio_is_unknown_when_no_exponent_is_declared():
    """No fitted exponent, no derating, and no claim that none is needed."""
    cell = make_cell(limits=make_limits(peukert_exponent=None))
    verdicts = assess_models(cell, make_load())
    assert verdicts[PEUKERT].status is ValidityStatus.UNKNOWN
    assert ctx.PEUKERT_CAPACITY_RATIO in verdicts[PEUKERT].unknown
    assert verdicts[PEUKERT].violated == ()


# =====================================================================
# Condition 15 — Peukert exponent temperature drift
# =====================================================================

def test_the_peukert_model_accepts_a_cell_at_the_temperature_it_was_fitted_at():
    verdicts = assess_models(make_cell(), make_load())
    assert ctx.PEUKERT_TEMPERATURE_DRIFT_RATIO in verdicts[PEUKERT].satisfied


def test_the_peukert_model_rejects_a_cell_outside_the_span_the_fit_covers():
    """A 2 K span around 25 degC, evaluated at 32 degC.

    Distinct from the capacity and resistance drift conditions: a different
    fitted object, with its own reference and its own declared reach, and the
    other two stay satisfied here.
    """
    cell = make_cell(limits=make_limits(peukert_temperature_span=Quantity(2.0, K)))
    verdicts = assess_models(cell, make_load(cell_temperature=Quantity(305.15, K)))
    assert verdicts[PEUKERT].status is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
    assert verdicts[PEUKERT].violated == (ctx.PEUKERT_TEMPERATURE_DRIFT_RATIO,)
    assert ctx.INTERNAL_RESISTANCE_DRIFT_RATIO in verdicts[RINT].satisfied
    assert ctx.CAPACITY_TEMPERATURE_DRIFT_RATIO in verdicts[COULOMB].satisfied


def test_the_peukert_temperature_drift_is_unknown_without_a_declared_span():
    cell = make_cell(limits=make_limits(peukert_temperature_span=None))
    verdicts = assess_models(cell, make_load())
    assert verdicts[PEUKERT].status is ValidityStatus.UNKNOWN
    assert ctx.PEUKERT_TEMPERATURE_DRIFT_RATIO in verdicts[PEUKERT].unknown
    assert verdicts[PEUKERT].violated == ()


# =====================================================================
# No declared category may move any verdict
# =====================================================================

def test_no_declared_category_changes_any_verdict_at_all():
    """Three declarations that differ only in their strings assess identically.

    ``chemistry``, ``cooling_mode`` and ``duty_type`` are recorded context and
    nothing else. This is the rule a sibling domain shipped without and had to
    fix: a condition that could be satisfied by *asserting a regime* rested its
    strongest term on an unverifiable claim by the party being assessed.

    Every field of every assessment is compared, not just the status: a
    category that moved one condition from satisfied to unknown while leaving
    the overall status alone would be just as much of a bypass.
    """
    variants = [
        (
            make_cell(
                limits=make_limits(cooling_mode=cooling), chemistry=chemistry
            ),
            make_load(duty_type=duty),
        )
        for chemistry, cooling, duty in (
            (None, None, None),
            (ctx.LITHIUM_ION, ctx.PASSIVE_COOLING, ctx.CONTINUOUS_DUTY),
            (ctx.LEAD_ACID, ctx.LIQUID_COOLING, ctx.PULSED_DUTY),
        )
    ]
    assessments = [assess_models(cell, load) for cell, load in variants]
    reference = assessments[0]
    for other in assessments[1:]:
        assert other.keys() == reference.keys()
        for model_id in reference:
            assert other[model_id] == reference[model_id], model_id


def make_limits_with_cooling():
    return build_limits(cooling_mode=ctx.LIQUID_COOLING)


def test_a_declared_category_never_reaches_the_problem_as_a_parameter():
    """The categories are not merely ignored — they are not transported.

    A category cannot cross the provenance boundary, which admits only
    Quantity-valued inputs. Emitting one as a parameter would put a verdict's
    input somewhere provenance cannot record it even if no condition read it,
    so the builder emits none and the problem stays entirely quantitative.
    """
    cell = make_cell(
        limits=make_limits_with_cooling(), chemistry=ctx.LITHIUM_ION
    )
    problem = bat.build_battery_problem(cell, make_load(duty_type=ctx.PULSED_DUTY))
    assert all(p.is_quantity for p in problem.parameters)
    names = {p.name for p in problem.parameters}
    assert "chemistry" not in names
    assert "cooling_mode" not in names
    assert "duty_type" not in names
    # And the context built from it carries no string anywhere.
    context = bat.battery_validity_context(
        problem,
        state_of_charge=Quantity(0.9, ONE),
        discharge_current=Quantity(2.5, A),
        cell_temperature=Quantity(298.15, K),
    )
    assert all(isinstance(value, Quantity) for value in context.values())


def test_a_declared_category_is_still_recorded_and_serialized():
    """Inert is not the same as discarded.

    The categories survive a round trip, because they are why a reader should
    believe the declared numbers. Removing them would lose that context; using
    them would lose the guarantee above. Both are avoided at once.
    """
    cell = make_cell(
        limits=make_limits_with_cooling(), chemistry=ctx.NICKEL_METAL_HYDRIDE
    )
    load = make_load(duty_type=ctx.PULSED_DUTY)
    assert bat.CellSpecification.from_dict(cell.to_dict()) == cell
    assert bat.DischargeLoad.from_dict(load.to_dict()) == load
    assert cell.to_dict()["chemistry"] == ctx.NICKEL_METAL_HYDRIDE
    assert cell.to_dict()["limits"]["cooling_mode"] == ctx.LIQUID_COOLING
    assert load.to_dict()["duty_type"] == ctx.PULSED_DUTY


def test_a_declared_category_is_not_part_of_a_cell_s_physical_identity():
    """The same cell known to different depth is still the same cell.

    Including a category in the identity would let a caller change what a
    solver considers the same system by asserting a string — the same defect
    as letting one decide a verdict, one layer over.
    """
    stated = make_cell(chemistry=ctx.LITHIUM_ION)
    silent = make_cell(chemistry=None)
    assert stated.physical_key == silent.physical_key
    assert stated != silent


def test_an_unknown_category_is_refused_rather_than_ignored():
    """A string outside its vocabulary is a specification error.

    Silently accepting it would make the record's own claim — that these are
    validated declarations — untrue, even though nothing reads them.
    """
    from src.engcore.scientific.errors import InvalidScientificProblem

    with pytest.raises(InvalidScientificProblem, match="chemistry"):
        make_cell(chemistry="unobtainium")
    with pytest.raises(InvalidScientificProblem, match="cooling_mode"):
        build_limits(cooling_mode="cryogenic")
    with pytest.raises(InvalidScientificProblem, match="duty_type"):
        make_load(duty_type="intermittent")


# =====================================================================
# No validity domain was left empty
# =====================================================================

def test_a_model_with_no_declared_conditions_would_be_unknown():
    """The core's rule, restated where this domain can be checked against it.

    Absence of declared limits is not evidence of unlimited validity. A model
    record with an empty domain reports UNKNOWN however much context it is
    handed — which is why leaving one empty is the failure the next test
    guards against.
    """
    empty = ScientificModelDefinition(
        model_id="battery.cell.undeclared",
        version="0.0.0",
        validity=ValidityDomain(),
    )
    assert empty.assess_validity({}).status is ValidityStatus.UNKNOWN
    assert (
        empty.assess_validity(
            {ctx.CONTINUOUS_C_RATE_UTILIZATION: Quantity(0.1, ONE)}
        ).status
        is ValidityStatus.UNKNOWN
    )


def test_no_model_in_this_domain_left_its_validity_domain_empty():
    """Every record carries real conditions, and enough of them to matter."""
    for model in mdl.BATTERY_MODELS:
        assert model.validity.conditions, model.model_id
        assert model.validity.description, model.model_id
        for condition in model.validity.conditions:
            assert condition.description.strip(), (model.model_id, condition.name)


def test_the_domain_declares_at_least_ten_conditions_on_derived_quantities():
    """Counted mechanically, not asserted in prose.

    A condition counts only if its name is a quantity this domain *derives* —
    something no caller can declare, and that exists only as the output of a
    function in ``context.py``. Bounds on declared parameters (a positive
    capacity, an efficiency in (0, 1]) say the declaration is well formed and
    are excluded from the count.
    """
    derived_names = set(
        ctx.derived_cell_quantities(
            {
                ctx.NOMINAL_CAPACITY: Quantity(2.5, "ampere_hour"),
                ctx.INTERNAL_RESISTANCE: Quantity(0.03, "ohm"),
                ctx.OCV_AT_FULL: Quantity(4.2, V),
                ctx.OCV_AT_EMPTY: Quantity(3.0, V),
                ctx.COULOMBIC_EFFICIENCY: Quantity(0.99, ONE),
                ctx.DURATION: Quantity(120.0, S),
                **{
                    spec.name: getattr(build_limits(), spec.name)
                    for spec in ctx.LIMIT_SPECS
                },
                ctx.PULSE_CURRENT: Quantity(8.0, A),
                ctx.PULSE_DURATION: Quantity(5.0, S),
                ctx.CUTOFF_VOLTAGE: Quantity(3.0, V),
                ctx.CUTOFF_STATE_OF_CHARGE: Quantity(0.15, ONE),
            },
            state_of_charge=Quantity(0.9, ONE),
            discharge_current=Quantity(2.5, A),
            cell_temperature=Quantity(298.15, K),
        )
    )
    conditioned = {
        condition.name
        for model in mdl.BATTERY_MODELS
        for condition in model.validity.conditions
    }
    on_derived = conditioned & derived_names
    # The consistency condition is real but does not count toward the ten.
    applicability = on_derived - {ctx.TERMINAL_VOLTAGE_RATIO}
    assert len(applicability) >= 10, sorted(applicability)
    # Nothing conditioned is neither a derived quantity nor a declared input.
    declared = {
        ctx.NOMINAL_CAPACITY,
        ctx.INTERNAL_RESISTANCE,
        ctx.COULOMBIC_EFFICIENCY,
    }
    assert conditioned <= on_derived | declared


# =====================================================================
# F03 — a caller parameter cannot be read as a derived quantity
# =====================================================================

def _with_parameters(problem, values):
    """The same problem with extra caller parameters, through public APIs only.

    A ``to_dict``/``from_dict`` round trip, which is how the review reproduced
    this: no private attribute is touched and nothing is monkeypatched.
    """
    payload = problem.to_dict()
    payload["parameters"].extend(
        ScientificParameter(name=name, value=value).to_dict()
        for name, value in values.items()
    )
    return ScientificProblem.from_dict(payload)


def test_f03_a_caller_parameter_cannot_stand_in_for_a_failed_derivation():
    """A cell that declared no resistance span cannot be handed the ratio.

    Without ``resistance_temperature_span`` the drift ratio cannot be formed,
    so ``internal_resistance_drift_ratio`` is UNKNOWN. Context assembly started
    from every caller parameter and overwrote only what it derived, so a caller
    parameter of the same name survived the failure of the derivation it was
    named after and was read as though this domain had computed it.
    """
    silent = build_cell(limits=build_limits(resistance_temperature_span=None))
    load = build_load()
    problem = bat.build_battery_problem(silent, load)
    point = dict(
        state_of_charge=load.initial_state_of_charge,
        discharge_current=load.current,
        cell_temperature=load.cell_temperature,
    )

    honest = bat.assess_rint_validity(problem, **point)
    assert ctx.INTERNAL_RESISTANCE_DRIFT_RATIO in honest.unknown

    forged = bat.assess_rint_validity(
        _with_parameters(
            problem,
            {ctx.INTERNAL_RESISTANCE_DRIFT_RATIO: Quantity(0.1, ONE)},
        ),
        **point,
    )
    assert ctx.INTERNAL_RESISTANCE_DRIFT_RATIO in forged.unknown
    assert ctx.INTERNAL_RESISTANCE_DRIFT_RATIO not in forged.satisfied
    assert forged.status is ValidityStatus.UNKNOWN


def test_f03_a_caller_parameter_cannot_supply_an_absent_state_coordinate():
    """The state coordinates are reserved too, and are protected twice.

    ``cell_temperature`` is what every temperature-dependent group is computed
    from, so a caller parameter of that name — on a call that supplied no
    temperature — would decide a whole family of conditions at once.

    On a problem this domain builds, the core refuses that outright: a
    parameter may not share a name with a declared variable, and the state
    coordinates are variables. The reservation is the second layer, and it is
    the one that holds on a problem that declares no such variable — which
    nothing prevents anybody from building.
    """
    cell, load = build_cell(), build_load()
    problem = bat.build_battery_problem(cell, load)

    with pytest.raises(InvalidScientificProblem, match="duplicate name"):
        _with_parameters(problem, {ctx.CELL_TEMPERATURE: Quantity(298.15, K)})

    # the same collision on a problem carrying no such variable
    payload = problem.to_dict()
    payload["variables"] = [
        v for v in payload["variables"] if v["name"] != ctx.CELL_TEMPERATURE
    ]
    payload["parameters"].append(
        ScientificParameter(
            name=ctx.CELL_TEMPERATURE, value=Quantity(298.15, K)
        ).to_dict()
    )
    forged = ScientificProblem.from_dict(payload)

    point = dict(
        state_of_charge=load.initial_state_of_charge,
        discharge_current=load.current,
    )
    honest = bat.assess_rint_validity(problem, **point)
    assert ctx.DISCHARGE_TEMPERATURE_POSITION in honest.unknown
    assert bat.assess_rint_validity(forged, **point) == honest


@pytest.mark.parametrize("declared", [True, False])
def test_f03_colliding_with_every_assembled_name_changes_no_verdict(declared):
    """Not one name and not the ones that were noticed: all of them.

    Run against a fully declared cell and one that declares no optional limit
    at all. The second is the case that matters — where the derivations fail
    and the old assembly left the caller's values in place — and the first is
    the regression guard that reserving a name does not stop the domain from
    filling it.
    """
    cell = build_cell() if declared else build_cell(limits=ctx.CellLimits())
    load = build_load()
    problem = bat.build_battery_problem(cell, load)
    point = dict(
        state_of_charge=load.initial_state_of_charge,
        discharge_current=load.current,
        cell_temperature=load.cell_temperature,
    )
    # The state coordinates are declared variables of this problem and the
    # core already refuses a parameter that shadows one — see the test above,
    # which exercises the reservation on a problem where it does not.
    declared_variables = {v.name for v in problem.variables}
    collisions = {
        name: Quantity(0.5, ONE)
        for name in ctx.ASSEMBLED_QUANTITIES - declared_variables
    }
    assert len(collisions) >= 19
    tampered = _with_parameters(problem, collisions)
    for model in mdl.BATTERY_MODELS:
        assert bat.assess_all(tampered, **point)[model.model_id] == (
            bat.assess_all(problem, **point)[model.model_id]
        )


def test_f03_every_derivable_name_is_reserved():
    """The registry cannot fall behind the assembler."""
    cell, load = build_cell(), build_load()
    problem = bat.build_battery_problem(cell, load)
    derivable = set(
        ctx.derived_cell_quantities(
            problem.validity_context(),
            state_of_charge=load.initial_state_of_charge,
            discharge_current=load.current,
            cell_temperature=load.cell_temperature,
        )
    )
    assert derivable
    assert derivable <= ctx.ASSEMBLED_QUANTITIES
