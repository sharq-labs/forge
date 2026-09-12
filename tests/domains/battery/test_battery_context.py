"""The derived quantities, one function at a time.

Every function in ``context.py`` gets three kinds of test: it computes the
right number, it handles units rather than magnitudes, and it returns ``None``
when it was not given what it needs. The third is the mechanism the whole
domain's honesty rests on — a function that invented a default would turn every
UNKNOWN in ``test_applicability.py`` into a silent IN_DOMAIN — so it is
asserted here directly rather than only through the assessments built on it.

A fourth kind appears where it matters: a value of the *wrong type* is refused
rather than skipped. A caller who passed a bare float declared something wrong,
which is a different situation from a caller who declared nothing, and
collapsing the two would turn a specification error into a silent UNKNOWN.
"""

from __future__ import annotations

import math

import pytest

from engcore.domains.battery import context as ctx
from engcore.scientific.errors import (
    InvalidScientificProblem,
    UnitCompatibilityError,
)
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
ONE = "dimensionless"
AH = "ampere_hour"
OHM = "ohm"


def q(magnitude: float, unit: str) -> Quantity:
    return Quantity(magnitude, unit)

# =====================================================================
# The checking helper every function is built on
# =====================================================================

def test_a_missing_value_stays_missing_and_a_wrong_type_is_refused():
    assert ctx._checked(None, A, "current") is None
    assert ctx._checked(q(2.0, A), A, "current") == q(2.0, A)
    with pytest.raises(InvalidScientificProblem, match="bare number"):
        ctx._checked(2.0, A, "current")


def test_a_wrong_dimension_is_refused_rather_than_converted():
    with pytest.raises(UnitCompatibilityError):
        ctx._checked(q(2.0, V), A, "current")


def test_a_non_positive_value_is_refused_where_the_domain_divides_by_it():
    with pytest.raises(InvalidScientificProblem, match="strictly positive"):
        ctx._checked(q(0.0, AH), AH, ctx.NOMINAL_CAPACITY, positive=True)
    with pytest.raises(InvalidScientificProblem, match="strictly positive"):
        ctx._checked(q(-1.0, AH), AH, ctx.NOMINAL_CAPACITY, positive=True)


def test_an_affine_temperature_scale_is_refused_where_a_span_is_meant():
    """A caller writing 15 degC meaning "fifteen degrees of span" declares 288 K.

    Every ratio built on it is then wrong by a factor of nineteen, with no
    dimension check able to notice, because degC and kelvin are the same
    dimension. The test is the published-contract one: does zero of this unit
    convert to zero kelvin?
    """
    with pytest.raises(InvalidScientificProblem, match="temperature \\*span\\*"):
        ctx._checked(q(15.0, "degC"), K, ctx.SELF_HEATING_RISE_BOUND, span=True)
    # A delta scale and kelvin both pass, and mean the same thing.
    assert ctx._checked(q(15.0, "delta_degC"), K, "span", span=True) is not None
    assert ctx._checked(q(15.0, K), K, "span", span=True) == q(15.0, K)


def test_the_ohmic_drop_is_a_voltage_however_the_inputs_were_declared():
    """Milliohms and ohms, milliamps and amps, all reach the same volt."""
    assert ctx._ohmic_drop(q(2.5, A), q(0.030, OHM)) == q(0.075, V)
    assert ctx._ohmic_drop(q(2500.0, "milliampere"), q(30.0, "milliohm")) == q(
        0.075, V
    )


# =====================================================================
# Rate
# =====================================================================

def test_the_c_rate_is_the_current_in_units_of_the_cell_s_capacity():
    """2.5 A from a 2.5 Ah cell is 1C — one nominal capacity per hour."""
    rate = ctx.c_rate(current=q(2.5, A), nominal_capacity=q(2.5, AH))
    assert rate.magnitude_in("1/hour") == pytest.approx(1.0)


def test_the_c_rate_is_computed_from_units_and_not_from_magnitudes():
    """A capacity in coulombs gives the same C-rate as one in ampere-hours.

    9000 C is 2.5 Ah. A function reading magnitudes would report 2.8e-4 here.
    """
    from_coulombs = ctx.c_rate(current=q(2.5, A), nominal_capacity=q(9000.0, "coulomb"))
    from_hours = ctx.c_rate(current=q(2.5, A), nominal_capacity=q(2.5, AH))
    assert from_coulombs.magnitude_in("1/hour") == pytest.approx(
        from_hours.magnitude_in("1/hour")
    )


def test_the_c_rate_is_none_without_a_current_or_without_a_capacity():
    assert ctx.c_rate(current=None, nominal_capacity=q(2.5, AH)) is None
    assert ctx.c_rate(current=q(2.5, A), nominal_capacity=None) is None


def test_the_continuous_utilization_is_the_rate_over_the_rating():
    used = ctx.continuous_c_rate_utilization(
        rate=q(1.0, "1/hour"), rating=q(2.0, "1/hour")
    )
    assert used.magnitude_in(ONE) == pytest.approx(0.5)


def test_the_continuous_utilization_takes_a_magnitude_of_the_operating_point():
    """A rating is a magnitude and the sign of a current is a direction."""
    used = ctx.continuous_c_rate_utilization(
        rate=q(-1.0, "1/hour"), rating=q(2.0, "1/hour")
    )
    assert used.magnitude_in(ONE) == pytest.approx(0.5)


def test_the_continuous_utilization_is_none_without_a_rating():
    assert (
        ctx.continuous_c_rate_utilization(rate=q(1.0, "1/hour"), rating=None)
        is None
    )
    assert ctx.continuous_c_rate_utilization(rate=None, rating=q(2.0, "1/hour")) is None


def test_the_pulse_utilization_uses_the_pulse_current_not_the_average():
    used = ctx.pulse_c_rate_utilization(
        pulse_current=q(8.0, A),
        nominal_capacity=q(2.5, AH),
        rating=q(10.0, "1/hour"),
    )
    assert used.magnitude_in(ONE) == pytest.approx(0.32)


def test_the_pulse_utilization_is_none_when_either_half_is_absent():
    assert (
        ctx.pulse_c_rate_utilization(
            pulse_current=None,
            nominal_capacity=q(2.5, AH),
            rating=q(10.0, "1/hour"),
        )
        is None
    )
    assert (
        ctx.pulse_c_rate_utilization(
            pulse_current=q(8.0, A), nominal_capacity=q(2.5, AH), rating=None
        )
        is None
    )


def test_the_pulse_duration_utilization_compares_two_declared_durations():
    used = ctx.pulse_duration_utilization(
        pulse_duration=q(5.0, S), rated_duration=q(10.0, S)
    )
    assert used.magnitude_in(ONE) == pytest.approx(0.5)
    # Minutes and seconds meet in the same number.
    minutes = ctx.pulse_duration_utilization(
        pulse_duration=q(0.5, "minute"), rated_duration=q(60.0, S)
    )
    assert minutes.magnitude_in(ONE) == pytest.approx(0.5)


def test_the_pulse_duration_utilization_is_none_without_a_rated_duration():
    assert (
        ctx.pulse_duration_utilization(
            pulse_duration=q(5.0, S), rated_duration=None
        )
        is None
    )


# =====================================================================
# State of charge
# =====================================================================

def test_discharge_efficiency_below_one_depletes_faster_than_ideal():
    """Discharge losses reduce usable capacity; they cannot create free charge."""
    final = ctx.final_state_of_charge(
        initial_state_of_charge=q(0.9, ONE),
        current=q(2.5, A),
        duration=q(120.0, S),
        coulombic_efficiency=q(0.99, ONE),
        nominal_capacity=q(2.5, AH),
    )
    ideal = ctx.final_state_of_charge(
        initial_state_of_charge=q(0.9, ONE),
        current=q(2.5, A),
        duration=q(120.0, S),
        coulombic_efficiency=q(1.0, ONE),
        nominal_capacity=q(2.5, AH),
    )
    assert final.magnitude_in(ONE) == pytest.approx(0.9 - (1.0 / 30.0) / 0.99)
    assert final.magnitude_in(ONE) < ideal.magnitude_in(ONE)


def test_the_counter_converts_the_duration_rather_than_assuming_hours():
    """Two minutes declared as minutes and as seconds give one answer."""
    in_seconds = ctx.final_state_of_charge(
        initial_state_of_charge=q(0.9, ONE),
        current=q(2.5, A),
        duration=q(120.0, S),
        coulombic_efficiency=q(1.0, ONE),
        nominal_capacity=q(2.5, AH),
    )
    in_minutes = ctx.final_state_of_charge(
        initial_state_of_charge=q(0.9, ONE),
        current=q(2.5, A),
        duration=q(2.0, "minute"),
        coulombic_efficiency=q(1.0, ONE),
        nominal_capacity=q(2.5, AH),
    )
    assert in_seconds.magnitude_in(ONE) == pytest.approx(
        in_minutes.magnitude_in(ONE)
    )


def test_the_counter_reports_a_state_of_charge_below_zero_rather_than_clipping():
    """Driving the counter past empty is a real answer to a real question.

    Clipping it would hide exactly the case the window condition exists to
    report, and would make a run that over-discharged look like one that
    stopped at empty.
    """
    final = ctx.final_state_of_charge(
        initial_state_of_charge=q(0.1, ONE),
        current=q(2.5, A),
        duration=q(3600.0, S),
        coulombic_efficiency=q(1.0, ONE),
        nominal_capacity=q(2.5, AH),
    )
    assert final.magnitude_in(ONE) == pytest.approx(-0.9)


def test_the_counter_is_none_when_any_of_its_five_inputs_is_absent():
    complete = dict(
        initial_state_of_charge=q(0.9, ONE),
        current=q(2.5, A),
        duration=q(120.0, S),
        coulombic_efficiency=q(0.99, ONE),
        nominal_capacity=q(2.5, AH),
    )
    assert ctx.final_state_of_charge(**complete) is not None
    for missing in complete:
        assert ctx.final_state_of_charge(**{**complete, missing: None}) is None, missing


def test_the_window_margin_is_the_distance_from_the_nearest_declared_edge():
    """0.9 down to 0.867 in a 0.10-0.95 window: 0.05 of headroom at the top."""
    margin = ctx.soc_window_margin(
        initial_state_of_charge=q(0.9, ONE),
        final_soc=q(0.867, ONE),
        window_minimum=q(0.10, ONE),
        window_maximum=q(0.95, ONE),
    )
    assert margin.magnitude_in(ONE) == pytest.approx(0.05 / 0.85)


def test_the_window_margin_goes_negative_when_the_run_leaves_the_window():
    margin = ctx.soc_window_margin(
        initial_state_of_charge=q(0.99, ONE),
        final_soc=q(0.96, ONE),
        window_minimum=q(0.10, ONE),
        window_maximum=q(0.95, ONE),
    )
    assert margin.magnitude_in(ONE) < 0.0


def test_the_window_margin_is_zero_exactly_on_an_edge():
    """Touching an edge is inside the window the caller declared."""
    margin = ctx.soc_window_margin(
        initial_state_of_charge=q(0.95, ONE),
        final_soc=q(0.50, ONE),
        window_minimum=q(0.10, ONE),
        window_maximum=q(0.95, ONE),
    )
    assert margin.magnitude_in(ONE) == pytest.approx(0.0)


def test_the_window_margin_looks_at_both_ends_of_the_trajectory():
    """A run that starts inside and finishes below is outside, and vice versa."""
    below = ctx.soc_window_margin(
        initial_state_of_charge=q(0.5, ONE),
        final_soc=q(0.05, ONE),
        window_minimum=q(0.10, ONE),
        window_maximum=q(0.95, ONE),
    )
    assert below.magnitude_in(ONE) < 0.0


def test_the_window_margin_is_none_when_an_edge_was_not_declared():
    assert (
        ctx.soc_window_margin(
            initial_state_of_charge=q(0.9, ONE),
            final_soc=q(0.867, ONE),
            window_minimum=None,
            window_maximum=q(0.95, ONE),
        )
        is None
    )


def test_the_window_margin_refuses_an_inverted_window():
    with pytest.raises(InvalidScientificProblem, match="window"):
        ctx.soc_window_margin(
            initial_state_of_charge=q(0.9, ONE),
            final_soc=q(0.8, ONE),
            window_minimum=q(0.95, ONE),
            window_maximum=q(0.10, ONE),
        )


def test_the_step_resolution_ratio_is_the_span_walked_over_the_span_allowed():
    ratio = ctx.soc_step_resolution_ratio(
        initial_state_of_charge=q(0.9, ONE),
        final_soc=q(0.8, ONE),
        resolution=q(0.05, ONE),
    )
    assert ratio.magnitude_in(ONE) == pytest.approx(2.0)


def test_the_step_resolution_ratio_is_none_without_a_declared_resolution():
    assert (
        ctx.soc_step_resolution_ratio(
            initial_state_of_charge=q(0.9, ONE),
            final_soc=q(0.8, ONE),
            resolution=None,
        )
        is None
    )


# =====================================================================
# Voltage
# =====================================================================

def test_the_open_circuit_voltage_is_the_declared_chord():
    """A straight line between the two declared endpoints, and nothing more."""
    assert ctx.open_circuit_voltage(
        state_of_charge=q(0.0, ONE), ocv_at_empty=q(3.0, V), ocv_at_full=q(4.2, V)
    ) == q(3.0, V)
    assert ctx.open_circuit_voltage(
        state_of_charge=q(1.0, ONE), ocv_at_empty=q(3.0, V), ocv_at_full=q(4.2, V)
    ) == q(4.2, V)
    midpoint = ctx.open_circuit_voltage(
        state_of_charge=q(0.5, ONE), ocv_at_empty=q(3.0, V), ocv_at_full=q(4.2, V)
    )
    assert midpoint.magnitude_in(V) == pytest.approx(3.6)


def test_the_open_circuit_voltage_reads_the_endpoints_in_their_own_units():
    """Millivolts and volts describe the same chord."""
    in_millivolts = ctx.open_circuit_voltage(
        state_of_charge=q(0.5, ONE),
        ocv_at_empty=q(3000.0, "millivolt"),
        ocv_at_full=q(4200.0, "millivolt"),
    )
    assert in_millivolts.magnitude_in(V) == pytest.approx(3.6)


def test_the_open_circuit_voltage_is_none_without_a_state_of_charge():
    assert (
        ctx.open_circuit_voltage(
            state_of_charge=None, ocv_at_empty=q(3.0, V), ocv_at_full=q(4.2, V)
        )
        is None
    )


def test_the_terminal_voltage_subtracts_the_ohmic_drop():
    terminal = ctx.terminal_voltage(
        open_circuit=q(4.0404, V),
        current=q(2.5, A),
        internal_resistance=q(0.030, OHM),
    )
    assert terminal.magnitude_in(V) == pytest.approx(3.9654)


def test_the_terminal_voltage_is_none_without_a_current():
    assert (
        ctx.terminal_voltage(
            open_circuit=q(4.0, V), current=None, internal_resistance=q(0.03, OHM)
        )
        is None
    )


def test_the_terminal_voltage_ratio_falls_through_zero_at_the_crossing():
    """A large enough drop makes the terminal voltage negative, and says so."""
    ratio = ctx.terminal_voltage_ratio(
        terminal=q(-0.96, V), open_circuit=q(4.04, V)
    )
    assert ratio.magnitude_in(ONE) < 0.0


def test_the_terminal_voltage_ratio_refuses_a_non_positive_open_circuit_voltage():
    """At OCV <= 0 the ratio is not a fraction of anything."""
    with pytest.raises(InvalidScientificProblem, match="strictly positive"):
        ctx.terminal_voltage_ratio(terminal=q(1.0, V), open_circuit=q(0.0, V))


def test_the_voltage_cutoff_names_a_higher_state_of_charge_at_higher_current():
    """The mechanism behind usable-capacity loss at rate, from the circuit.

    At 0 A the 3.0 V cutoff is reached at exactly empty. At 25 A the same
    cutoff is reached with a fifth of the charge still in the cell, because
    I R_int is subtracted from every point of the chord.
    """
    def at(current: float) -> float:
        return ctx.voltage_cutoff_state_of_charge(
            cutoff_voltage=q(3.0, V),
            current=q(current, A),
            internal_resistance=q(0.030, OHM),
            ocv_at_empty=q(3.0, V),
            ocv_at_full=q(4.2, V),
        ).magnitude_in(ONE)

    assert at(0.0) == pytest.approx(0.0)
    assert at(2.5) == pytest.approx(0.0625)
    assert at(25.0) == pytest.approx(0.625)
    assert at(25.0) > at(2.5) > at(0.0)


def test_the_voltage_cutoff_is_none_without_a_declared_cutoff():
    assert (
        ctx.voltage_cutoff_state_of_charge(
            cutoff_voltage=None,
            current=q(2.5, A),
            internal_resistance=q(0.030, OHM),
            ocv_at_empty=q(3.0, V),
            ocv_at_full=q(4.2, V),
        )
        is None
    )


def test_the_voltage_cutoff_refuses_a_chord_that_does_not_rise_with_charge():
    """A flat chord makes voltage and charge non-invertible."""
    with pytest.raises(InvalidScientificProblem, match="must exceed"):
        ctx.voltage_cutoff_state_of_charge(
            cutoff_voltage=q(3.0, V),
            current=q(2.5, A),
            internal_resistance=q(0.030, OHM),
            ocv_at_empty=q(4.2, V),
            ocv_at_full=q(4.2, V),
        )


def test_the_cutoff_margin_is_the_declared_target_minus_where_the_voltage_stops():
    margin = ctx.cutoff_consistency_margin(
        cutoff_state_of_charge=q(0.15, ONE), voltage_cutoff_soc=q(0.0625, ONE)
    )
    assert margin.magnitude_in(ONE) == pytest.approx(0.0875)
    unreachable = ctx.cutoff_consistency_margin(
        cutoff_state_of_charge=q(0.15, ONE), voltage_cutoff_soc=q(0.65, ONE)
    )
    assert unreachable.magnitude_in(ONE) < 0.0


def test_the_cutoff_margin_is_none_when_only_one_cutoff_exists():
    assert (
        ctx.cutoff_consistency_margin(
            cutoff_state_of_charge=None, voltage_cutoff_soc=q(0.0625, ONE)
        )
        is None
    )
    assert (
        ctx.cutoff_consistency_margin(
            cutoff_state_of_charge=q(0.15, ONE), voltage_cutoff_soc=None
        )
        is None
    )


# =====================================================================
# Heat and temperature
# =====================================================================

def test_the_heat_generated_is_the_irreversible_joule_term():
    heat = ctx.heat_generation(
        current=q(2.5, A), internal_resistance=q(0.030, OHM)
    )
    assert heat.magnitude_in("watt") == pytest.approx(0.1875)


def test_the_heat_generated_is_quadratic_in_current():
    """Doubling the current quadruples the heat — which is why a rate that

    passes a current rating can still fail a thermal one."""
    single = ctx.heat_generation(
        current=q(2.5, A), internal_resistance=q(0.030, OHM)
    ).magnitude_in("watt")
    double = ctx.heat_generation(
        current=q(5.0, A), internal_resistance=q(0.030, OHM)
    ).magnitude_in("watt")
    assert double == pytest.approx(4.0 * single)


def test_the_heat_generated_is_none_without_a_current():
    assert (
        ctx.heat_generation(current=None, internal_resistance=q(0.03, OHM)) is None
    )


def test_the_self_heating_rise_is_the_steady_asymptote_not_an_endpoint():
    """Q/hA, the temperature the body approaches for as long as it dissipates."""
    rise = ctx.self_heating_rise(
        heat=q(0.1875, "watt"), thermal_conductance=q(0.15, "watt/kelvin")
    )
    assert rise.magnitude_in(K) == pytest.approx(1.25)


def test_the_self_heating_rise_is_none_without_a_declared_conductance():
    assert (
        ctx.self_heating_rise(heat=q(0.1875, "watt"), thermal_conductance=None)
        is None
    )


def test_the_self_heating_ratio_refuses_a_budget_on_an_affine_scale():
    with pytest.raises(InvalidScientificProblem, match="temperature \\*span\\*"):
        ctx.self_heating_rise_ratio(rise=q(1.25, K), bound=q(15.0, "degC"))


def test_the_temperature_position_is_zero_at_the_low_edge_and_one_at_the_high():
    def at(kelvin: float) -> float:
        return ctx.discharge_temperature_position(
            temperature=q(kelvin, K),
            minimum=q(253.15, K),
            maximum=q(333.15, K),
        ).magnitude_in(ONE)

    assert at(253.15) == pytest.approx(0.0)
    assert at(333.15) == pytest.approx(1.0)
    assert at(298.15) == pytest.approx(0.5625)
    assert at(343.15) > 1.0
    assert at(243.15) < 0.0


def test_the_temperature_position_reads_celsius_as_a_temperature_not_a_span():
    """The edges are states, so an affine scale is correct here and allowed."""
    in_celsius = ctx.discharge_temperature_position(
        temperature=q(25.0, "degC"), minimum=q(-20.0, "degC"), maximum=q(60.0, "degC")
    )
    assert in_celsius.magnitude_in(ONE) == pytest.approx(0.5625)


def test_the_temperature_position_is_none_without_both_edges():
    assert (
        ctx.discharge_temperature_position(
            temperature=q(298.15, K), minimum=q(253.15, K), maximum=None
        )
        is None
    )


def test_the_temperature_position_refuses_an_inverted_range():
    with pytest.raises(InvalidScientificProblem, match="range"):
        ctx.discharge_temperature_position(
            temperature=q(298.15, K), minimum=q(333.15, K), maximum=q(253.15, K)
        )


def test_the_two_property_drift_ratios_are_computed_the_same_way_and_stay_apart():
    """One shared arithmetic, two separate declarations, two separate answers.

    The same cell can declare a wide span for its capacity and a narrow one
    for its resistance; the conditions must be able to disagree, and here they
    do from the same temperature.
    """
    resistance = ctx.internal_resistance_drift_ratio(
        temperature=q(305.15, K),
        reference_temperature=q(298.15, K),
        span=q(2.0, K),
    )
    capacity = ctx.capacity_temperature_drift_ratio(
        temperature=q(305.15, K),
        reference_temperature=q(293.15, K),
        span=q(50.0, K),
    )
    assert resistance.magnitude_in(ONE) == pytest.approx(3.5)
    assert capacity.magnitude_in(ONE) == pytest.approx(0.24)


def test_each_drift_ratio_is_none_without_its_own_reference_or_span():
    for function, reference in (
        (ctx.internal_resistance_drift_ratio, q(298.15, K)),
        (ctx.capacity_temperature_drift_ratio, q(293.15, K)),
        (ctx.peukert_temperature_drift_ratio, q(298.15, K)),
    ):
        assert (
            function(
                temperature=q(305.15, K),
                reference_temperature=None,
                span=q(20.0, K),
            )
            is None
        )
        assert (
            function(
                temperature=q(305.15, K),
                reference_temperature=reference,
                span=None,
            )
            is None
        )
        assert (
            function(
                temperature=None, reference_temperature=reference, span=q(20.0, K)
            )
            is None
        )


def test_a_drift_span_on_an_affine_scale_is_refused():
    with pytest.raises(InvalidScientificProblem, match="temperature \\*span\\*"):
        ctx.internal_resistance_drift_ratio(
            temperature=q(305.15, K),
            reference_temperature=q(298.15, K),
            span=q(20.0, "degC"),
        )


# =====================================================================
# Time scale
# =====================================================================

def test_the_settling_ratio_is_the_interval_in_relaxation_time_constants():
    ratio = ctx.polarization_settling_ratio(
        duration=q(120.0, S), time_constant=q(30.0, S)
    )
    assert ratio.magnitude_in(ONE) == pytest.approx(4.0)


def test_the_settling_ratio_is_none_without_a_declared_time_constant():
    assert (
        ctx.polarization_settling_ratio(duration=q(120.0, S), time_constant=None)
        is None
    )


# =====================================================================
# Peukert
# =====================================================================

def test_the_peukert_capacity_derates_above_the_reference_current():
    derated = ctx.peukert_effective_capacity(
        nominal_capacity=q(2.5, AH),
        current=q(2.5, A),
        reference_current=q(0.5, A),
        exponent=q(1.05, ONE),
    )
    assert derated.magnitude_in(AH) == pytest.approx(2.5 * 0.2 ** 0.05)
    assert derated.magnitude_in(AH) < 2.5


def test_a_peukert_exponent_of_one_is_the_rate_independent_ideal():
    """k = 1 is the cell whose deliverable charge does not depend on rate."""
    for current in (0.1, 0.5, 25.0):
        derated = ctx.peukert_effective_capacity(
            nominal_capacity=q(2.5, AH),
            current=q(current, A),
            reference_current=q(0.5, A),
            exponent=q(1.0, ONE),
        )
        assert derated.magnitude_in(AH) == pytest.approx(2.5)


def test_the_peukert_capacity_exceeds_nominal_below_the_reference_current():
    """The formula read outside the direction it means anything in."""
    ratio = ctx.peukert_capacity_ratio(
        effective_capacity=ctx.peukert_effective_capacity(
            nominal_capacity=q(2.5, AH),
            current=q(0.1, A),
            reference_current=q(0.5, A),
            exponent=q(1.05, ONE),
        ),
        nominal_capacity=q(2.5, AH),
    )
    assert ratio.magnitude_in(ONE) > 1.0


def test_the_peukert_capacity_is_none_without_an_exponent():
    assert (
        ctx.peukert_effective_capacity(
            nominal_capacity=q(2.5, AH),
            current=q(2.5, A),
            reference_current=q(0.5, A),
            exponent=None,
        )
        is None
    )
    assert (
        ctx.peukert_effective_capacity(
            nominal_capacity=q(2.5, AH),
            current=q(2.5, A),
            reference_current=None,
            exponent=q(1.05, ONE),
        )
        is None
    )


def test_the_extrapolation_ratio_is_measured_in_decades_because_the_law_is_a_power():
    """Symmetric in log current: a factor of ten either way is one decade."""
    up = ctx.peukert_extrapolation_ratio(
        current=q(5.0, A), reference_current=q(0.5, A), fit_decades=q(1.0, ONE)
    )
    down = ctx.peukert_extrapolation_ratio(
        current=q(0.05, A), reference_current=q(0.5, A), fit_decades=q(1.0, ONE)
    )
    assert up.magnitude_in(ONE) == pytest.approx(1.0)
    assert down.magnitude_in(ONE) == pytest.approx(1.0)
    at_reference = ctx.peukert_extrapolation_ratio(
        current=q(0.5, A), reference_current=q(0.5, A), fit_decades=q(1.0, ONE)
    )
    assert at_reference.magnitude_in(ONE) == pytest.approx(0.0)


def test_the_extrapolation_ratio_is_none_without_a_declared_reach():
    assert (
        ctx.peukert_extrapolation_ratio(
            current=q(2.5, A), reference_current=q(0.5, A), fit_decades=None
        )
        is None
    )


# =====================================================================
# The declaration record
# =====================================================================

def test_an_empty_limits_declaration_derives_nothing():
    """The whole of rule 8, in one assertion over the assembler.

    A problem carrying only the five required parameters and a duration
    derives the quantities those alone support, and *no* quantity that needs
    an optional declaration. Nothing is present with a placeholder.
    """
    derived = ctx.derived_cell_quantities(
        {
            ctx.NOMINAL_CAPACITY: q(2.5, AH),
            ctx.INTERNAL_RESISTANCE: q(0.030, OHM),
            ctx.OCV_AT_FULL: q(4.2, V),
            ctx.OCV_AT_EMPTY: q(3.0, V),
            ctx.COULOMBIC_EFFICIENCY: q(0.99, ONE),
            ctx.DURATION: q(120.0, S),
        },
        state_of_charge=q(0.9, ONE),
        discharge_current=q(2.5, A),
        cell_temperature=q(298.15, K),
    )
    assert set(derived) == {
        ctx.C_RATE,
        ctx.FINAL_STATE_OF_CHARGE,
        ctx.TERMINAL_VOLTAGE_RATIO,
    }
    assert all(isinstance(value, Quantity) for value in derived.values())


def test_withholding_the_operating_point_derives_nothing_at_all():
    """No state, no controls, no derived quantity — not even a zero."""
    derived = ctx.derived_cell_quantities(
        {spec.name: getattr(build_limits(), spec.name) for spec in ctx.LIMIT_SPECS}
    )
    assert derived == {}


def test_supplying_more_can_only_move_a_verdict_away_from_unknown():
    """The asymmetry the whole declaration record rests on.

    Adding a declaration adds derived keys and never removes one, so a
    condition can move from UNKNOWN to decided and never the other way. A
    declaration that could *unset* a derived quantity would let a caller
    retreat to UNKNOWN from a violation.
    """
    base = {
        ctx.NOMINAL_CAPACITY: q(2.5, AH),
        ctx.INTERNAL_RESISTANCE: q(0.030, OHM),
        ctx.OCV_AT_FULL: q(4.2, V),
        ctx.OCV_AT_EMPTY: q(3.0, V),
        ctx.COULOMBIC_EFFICIENCY: q(0.99, ONE),
        ctx.DURATION: q(120.0, S),
    }
    point = dict(
        state_of_charge=q(0.9, ONE),
        discharge_current=q(2.5, A),
        cell_temperature=q(298.15, K),
    )
    lean = set(ctx.derived_cell_quantities(base, **point))
    for spec in ctx.LIMIT_SPECS:
        value = getattr(build_limits(), spec.name)
        richer = set(
            ctx.derived_cell_quantities({**base, spec.name: value}, **point)
        )
        assert lean <= richer, spec.name


def test_the_limits_record_round_trips_and_reports_when_it_is_empty():
    full = build_limits()
    assert not full.is_empty
    assert ctx.CellLimits.from_dict(full.to_dict()) == full
    empty = ctx.CellLimits()
    assert empty.is_empty
    assert ctx.CellLimits.from_dict(empty.to_dict()) == empty


def test_the_limits_record_refuses_an_inverted_window_or_range():
    with pytest.raises(InvalidScientificProblem, match="state-of-charge window"):
        build_limits(
            usable_soc_minimum=q(0.9, ONE), usable_soc_maximum=q(0.1, ONE)
        )
    with pytest.raises(InvalidScientificProblem, match="temperature range"):
        build_limits(
            minimum_discharge_temperature=q(333.15, K),
            maximum_discharge_temperature=q(253.15, K),
        )


def test_the_limits_record_refuses_a_state_of_charge_outside_zero_to_one():
    with pytest.raises(InvalidScientificProblem, match="\\[0, 1\\]"):
        build_limits(usable_soc_maximum=q(1.5, ONE))


def test_the_limits_record_refuses_a_peukert_exponent_below_one():
    """k < 1 asserts a cell delivers more charge the harder it is discharged."""
    with pytest.raises(InvalidScientificProblem, match="at least 1"):
        build_limits(peukert_exponent=q(0.9, ONE))
    assert build_limits(peukert_exponent=q(1.0, ONE)) is not None


def test_every_declared_limit_is_enumerated_exactly_once_by_the_spec_table():
    """The table is the only enumeration, so a field cannot reach three of four.

    Twenty fields checked, serialized, decoded and emitted as parameters from
    one list. A field added to the dataclass and not to the table would be
    silently un-checked and un-transported, which this catches.
    """
    from dataclasses import fields

    declared = {f.name for f in fields(ctx.CellLimits)} - {"cooling_mode"}
    assert declared == set(ctx.LIMIT_NAMES)
    assert len(ctx.LIMIT_SPECS) == len(set(ctx.LIMIT_NAMES))


def test_every_derived_name_is_actually_produced_by_the_assembler():
    """No derived-quantity constant names something nothing computes.

    A stale name would make a condition permanently UNKNOWN with nothing to
    show for it, which looks identical to an honest missing declaration.
    """
    produced = set(
        ctx.derived_cell_quantities(
            {
                ctx.NOMINAL_CAPACITY: q(2.5, AH),
                ctx.INTERNAL_RESISTANCE: q(0.030, OHM),
                ctx.OCV_AT_FULL: q(4.2, V),
                ctx.OCV_AT_EMPTY: q(3.0, V),
                ctx.COULOMBIC_EFFICIENCY: q(0.99, ONE),
                ctx.DURATION: q(120.0, S),
                ctx.PULSE_CURRENT: q(8.0, A),
                ctx.PULSE_DURATION: q(5.0, S),
                ctx.CUTOFF_VOLTAGE: q(3.0, V),
                ctx.CUTOFF_STATE_OF_CHARGE: q(0.15, ONE),
                **{
                    spec.name: getattr(build_limits(), spec.name)
                    for spec in ctx.LIMIT_SPECS
                },
            },
            state_of_charge=q(0.9, ONE),
            discharge_current=q(2.5, A),
            cell_temperature=q(298.15, K),
        )
    )
    named = {
        value
        for name, value in vars(ctx).items()
        if name.isupper()
        and isinstance(value, str)
        and value
        in {
            ctx.C_RATE,
            ctx.CONTINUOUS_C_RATE_UTILIZATION,
            ctx.PULSE_C_RATE_UTILIZATION,
            ctx.PULSE_DURATION_UTILIZATION,
            ctx.FINAL_STATE_OF_CHARGE,
            ctx.SOC_WINDOW_MARGIN,
            ctx.DISCHARGE_TEMPERATURE_POSITION,
            ctx.INTERNAL_RESISTANCE_DRIFT_RATIO,
            ctx.SELF_HEATING_RISE,
            ctx.SELF_HEATING_RISE_RATIO,
            ctx.POLARIZATION_SETTLING_RATIO,
            ctx.POLARIZATION_UNMODELLED_FRACTION,
            ctx.TERMINAL_VOLTAGE_RATIO,
            ctx.SOC_STEP_RESOLUTION_RATIO,
            ctx.CAPACITY_TEMPERATURE_DRIFT_RATIO,
            ctx.CUTOFF_CONSISTENCY_MARGIN,
            ctx.CUTOFF_REACHABILITY_MARGIN,
            ctx.PEUKERT_EXTRAPOLATION_RATIO,
            ctx.PEUKERT_CAPACITY_RATIO,
            ctx.PEUKERT_TEMPERATURE_DRIFT_RATIO,
        }
    }
    assert named == produced


def test_no_derivation_reads_a_declared_category():
    """Rule 8's second half, asserted over the source rather than the behaviour.

    A behavioural test can only show that today's categories change nothing.
    This shows that no derivation *could*: the assembler takes three keyword
    arguments, all Quantities, and reads its remaining inputs from a mapping
    whose category keys the problem builder never writes.
    """
    import ast
    import inspect

    categories = ("chemistry", "cooling_mode", "duty_type")

    # The *executable* body of the assembler, with its docstring removed: the
    # docstring names all three, because explaining that they are excluded is
    # part of the record. Only the code must be silent about them.
    tree = ast.parse(inspect.getsource(ctx.derived_cell_quantities))
    body = tree.body[0].body
    if isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body = body[1:]
    code = "\n".join(ast.unparse(node) for node in body)
    for category in categories:
        assert category not in code, category

    # And no *derivation* reads one either. The scan is over the functions that
    # produce derived quantities, not over the whole module: CellLimits.to_dict
    # and from_dict legitimately carry ``cooling_mode`` across a round trip,
    # which is the recording this domain wants. What must never happen is a
    # derivation looking one up.
    derivations = [
        value
        for name, value in vars(ctx).items()
        if inspect.isfunction(value) and not name.startswith("_")
    ]
    assert len(derivations) >= 15, "the scan must actually cover the derivations"
    for derivation in derivations:
        source = inspect.getsource(derivation)
        for category in categories:
            assert f'get("{category}")' not in source, derivation.__name__
            assert f"get('{category}')" not in source, derivation.__name__
            assert f'["{category}"]' not in source, derivation.__name__


def test_no_derived_quantity_is_ever_non_finite_from_finite_declarations():
    """Interpreted science may not carry NaN, and this domain cannot make one."""
    derived = ctx.derived_cell_quantities(
        {
            ctx.NOMINAL_CAPACITY: q(2.5, AH),
            ctx.INTERNAL_RESISTANCE: q(0.030, OHM),
            ctx.OCV_AT_FULL: q(4.2, V),
            ctx.OCV_AT_EMPTY: q(3.0, V),
            ctx.COULOMBIC_EFFICIENCY: q(0.99, ONE),
            ctx.DURATION: q(120.0, S),
            **{
                spec.name: getattr(build_limits(), spec.name)
                for spec in ctx.LIMIT_SPECS
            },
        },
        state_of_charge=q(0.9, ONE),
        discharge_current=q(2.5, A),
        cell_temperature=q(298.15, K),
    )
    assert all(math.isfinite(value.magnitude) for value in derived.values())
