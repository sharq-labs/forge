"""Shared declarations for the battery domain's tests.

One cell and one load, fully declared and at a benign operating point, from
which every test builds by replacing exactly what it is about. Each builder
returns a fresh record, so no test can mutate what another reads.

**Deliberately not a ``conftest.py``.** ``tests/test_tier_classification.py``
imports the *root* ``conftest`` by module name, and pytest prepends each test
file's own directory to ``sys.path``; a second file called ``conftest.py``
anywhere under ``tests/`` shadows the root one and breaks that import. The
module basename is unique for the same reason the test modules' are: the
suite's parallel-safety audit records "duplicate module basenames: none", and
that is a property worth keeping true.

The baseline is arranged so that **every condition in all four models is
decidable and satisfied**. That is what makes an OUTSIDE test meaningful: it
pushes exactly one condition out of its own model's domain, and asserts the
violated tuple, so a threshold moved by accident cannot hide behind a
neighbour's failure.

The numbers, and what each is chosen to make true
-------------------------------------------------
A 2.5 Ah cell with 30 mOhm of series resistance, discharged at 2.5 A (1C) from
90 % state of charge for two minutes at 25 degC::

    c_rate                            2.5 / 2.5              = 1.0 /h
    continuous_c_rate_utilization     1.0 / 2.0              = 0.50
    pulse_c_rate_utilization          (8/2.5) / 10           = 0.32
    pulse_duration_utilization        5 / 10                 = 0.50
    final_state_of_charge   0.9 - 0.99*2.5*(1/30)/2.5        = 0.867
    soc_window_margin       min(0.767, 0.05) / 0.85          = 0.0588
    discharge_temperature_position  (298.15-253.15)/80       = 0.5625
    internal_resistance_drift_ratio  |298.15-298.15| / 50    = 0.0
    self_heating_rise       2.5^2 * 0.03 / 0.15              = 1.25 K
    self_heating_rise_ratio           1.25 / 15              = 0.0833
    polarization_settling_ratio       120 / 30               = 4.0
    polarization_unmodelled_fraction  1 - (1-exp(-4))        = 0.0183
    terminal_voltage_ratio  (4.0404 - 0.075) / 4.0404        = 0.981
    soc_step_resolution_ratio         0.033 / 0.10           = 0.33
    capacity_temperature_drift_ratio |298.15-293.15| / 20     = 0.25
    cutoff_consistency_margin  0.15 - (3.0+0.075-3.0)/1.2    = 0.0875
    peukert_extrapolation_ratio  |log10(2.5/0.5)| / 1        = 0.699
    peukert_capacity_ratio       (0.5/2.5)^0.05              = 0.923
    peukert_temperature_drift_ratio  |298.15-298.15| / 50    = 0.0

The resistance and Peukert temperature spans are deliberately wide (50 K) so
that a test raising the cell temperature past the *discharge range* does not
also trip the drift conditions. The drift tests narrow the span instead, which
is the same excursion expressed the other way round and keeps one condition per
test.
"""

from __future__ import annotations

from src.engcore.domains.battery import cell as bat
from src.engcore.domains.battery import context as ctx
from src.engcore.scientific.units.quantity import Quantity

K = "kelvin"
S = "second"
A = "ampere"
V = "volt"
AH = "ampere_hour"
OHM = "ohm"
ONE = "dimensionless"
C_RATE = "1/hour"

#: Every optional limit, declared. A cell built from this supports a verdict on
#: every condition in the domain; a cell built from ``ctx.CellLimits()``
#: supports none, which is what the UNKNOWN tests exercise.
FULL_LIMITS: dict[str, object] = {
    ctx.CONTINUOUS_DISCHARGE_C_RATE: Quantity(2.0, C_RATE),
    ctx.PULSE_DISCHARGE_C_RATE: Quantity(10.0, C_RATE),
    ctx.RATED_PULSE_DURATION: Quantity(10.0, S),
    ctx.USABLE_SOC_MINIMUM: Quantity(0.10, ONE),
    ctx.USABLE_SOC_MAXIMUM: Quantity(0.95, ONE),
    ctx.MINIMUM_DISCHARGE_TEMPERATURE: Quantity(253.15, K),
    ctx.MAXIMUM_DISCHARGE_TEMPERATURE: Quantity(333.15, K),
    ctx.RESISTANCE_REFERENCE_TEMPERATURE: Quantity(298.15, K),
    ctx.RESISTANCE_TEMPERATURE_SPAN: Quantity(50.0, K),
    ctx.CELL_THERMAL_CONDUCTANCE: Quantity(0.15, "watt/kelvin"),
    ctx.SELF_HEATING_RISE_BOUND: Quantity(15.0, K),
    ctx.POLARIZATION_TIME_CONSTANT: Quantity(30.0, S),
    ctx.SOC_STEP_RESOLUTION: Quantity(0.10, ONE),
    ctx.CAPACITY_REFERENCE_TEMPERATURE: Quantity(293.15, K),
    ctx.CAPACITY_TEMPERATURE_SPAN: Quantity(20.0, K),
    ctx.PEUKERT_EXPONENT: Quantity(1.05, ONE),
    ctx.PEUKERT_REFERENCE_CURRENT: Quantity(0.5, A),
    ctx.PEUKERT_FIT_DECADES: Quantity(1.0, ONE),
    ctx.PEUKERT_REFERENCE_TEMPERATURE: Quantity(298.15, K),
    ctx.PEUKERT_TEMPERATURE_SPAN: Quantity(50.0, K),
}

CELL_DEFAULTS: dict[str, object] = {
    "cell_id": "CELL-1",
    ctx.NOMINAL_CAPACITY: Quantity(2.5, AH),
    ctx.INTERNAL_RESISTANCE: Quantity(0.030, OHM),
    ctx.OCV_AT_FULL: Quantity(4.2, V),
    ctx.OCV_AT_EMPTY: Quantity(3.0, V),
    ctx.COULOMBIC_EFFICIENCY: Quantity(0.99, ONE),
}

LOAD_DEFAULTS: dict[str, object] = {
    "load_id": "LOAD-1",
    "current": Quantity(2.5, A),
    "initial_state_of_charge": Quantity(0.90, ONE),
    ctx.CELL_TEMPERATURE: Quantity(298.15, K),
    ctx.DURATION: Quantity(120.0, S),
    ctx.PULSE_CURRENT: Quantity(8.0, A),
    ctx.PULSE_DURATION: Quantity(5.0, S),
    ctx.CUTOFF_VOLTAGE: Quantity(3.0, V),
    ctx.CUTOFF_STATE_OF_CHARGE: Quantity(0.15, ONE),
}


def build_limits(**overrides) -> ctx.CellLimits:
    """The fully declared limits, with named fields replaced or removed.

    Passing ``None`` for a field *removes* the declaration, which is how every
    UNKNOWN test is written: the omission is explicit at the call site rather
    than buried in a second fixture.
    """
    fields = dict(FULL_LIMITS)
    fields.update(overrides)
    return ctx.CellLimits(**fields)


def build_cell(limits: ctx.CellLimits | None = None, **overrides):
    fields = dict(CELL_DEFAULTS)
    fields.update(overrides)
    return bat.CellSpecification(
        limits=build_limits() if limits is None else limits, **fields
    )


def build_load(**overrides):
    fields = dict(LOAD_DEFAULTS)
    fields.update(overrides)
    return bat.DischargeLoad(**fields)


def assess(cell, load, **operating_point):
    """Every model's verdict for this cell under this load.

    The operating point defaults to what the load declares, and any of the
    three may be overridden — including to ``None``, which is how the
    "missing operating point" tests are written.
    """
    point = {
        "state_of_charge": load.initial_state_of_charge,
        "discharge_current": load.current,
        "cell_temperature": load.cell_temperature,
    }
    point.update(operating_point)
    return bat.assess_all(bat.build_battery_problem(cell, load), **point)
