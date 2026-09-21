"""The recovery's banded open-circuit voltage authority.

Generated from ``benchmarks/battery_voltage_s3_recovery/evidence/OCV_AUTHORITY_V2.json``
by ``benchmarks/battery_voltage_s3_recovery/harness/emit_ocv_v2.py``. Do not edit
the tables by hand: regenerate them, and let the test that compares this module
against that record catch the difference.

How this differs from :mod:`engcore.domains.battery.flagship_ocv`
------------------------------------------------------------------
**The charge-state axis.** Sprint 3's curve is against ``z = 1 - q / 2.0 Ah``,
the manufacturer's rating. These curves are against ``z = 1 - q / Q_available``,
with ``Q_available`` established per trajectory by
:mod:`engcore.domains.battery.capacity` from cycles that completed before it.
The rating is 20-33 % above what these cells deliver, depending on which of them: 22 % at the median over this corpus's own trajectories and 33 % over the whole retained archive and wrong by a different
amount for each, so pairs at different true depths of discharge landed on the
same knot of the old curve.

**Two bands, and no interpolation between them.** Conditioned on the median
measured cell temperature over the loaded discharge, the two bands differ by
80 mV at the median knot and 263 mV at the bottom -- far outside the frozen
50 mV acceptance tolerance. Pooling them collapses the admissible interval to
three knots, which is the evidence that they are two relations rather than one.
There is nothing measured between 13 and 23 degC in this archive, so the gap
between the bands carries no curve and the model refuses there.

**A measured charge-state shape on the ohmic resistance.** The
branch-difference resistance falls from 0.201 to 0.133 ohm across charge state
when warm and from 0.499 to 0.294 ohm when cold. That is a measurement with no
model in it, and it is carried as a multiplicative shape normalized to one at
charge state 0.5 so the fitted reference resistance keeps its meaning.
It adds no fitted parameter.

What promoted it was identifiability, not fit. Without the shape the cold
parameter unit leaves the ohmic reference resistance, the polarization reference
resistance and the polarization activation energy all unidentified, at a
normal-matrix condition number of 1.6e20 and a correlation of -0.9999 between R0
and its own activation energy: the fitter is absorbing a real charge-state trend
into a constant and its temperature slope. With the shape that unit is fully
identified and the condition number falls four orders of magnitude. The cold
unit is the one that predicts the locked holdout.

What these are not
------------------
Not equilibrium open-circuit voltages. Branch averaging cancels a linear
resistance exactly, whatever its size, but it does not cancel polarization that
is nonlinear in current, nor a resistance that differs between the charge and
discharge directions. At low temperature both are larger, so part of the
cold-to-warm offset may be that asymmetry rather than a temperature dependence
of the open-circuit voltage itself. The curves are what predicts these cells;
they are not a thermodynamic statement.

Outside its declared charge-state interval a curve returns
OUTSIDE_VALIDATED_DOMAIN and the kernel propagates that refusal rather than
reaching past it.
"""

from __future__ import annotations

from ...scientific.models.curves import (
    DeclaredCurve,
    Interpolation,
    TabulatedForm,
)
from . import context as ctx

#: Source record these tables were generated from, and the archive behind it.
OCV_V2_SOURCE_RECORD = (
    "benchmarks/battery_voltage_s3_recovery/evidence/OCV_AUTHORITY_V2.json"
)
OCV_V2_SOURCE_SHA256 = "9adcb29f8d69bc016f5f9de3032cf6c2aae6bf1423b7037ad31580c0db8bf779"
OCV_V2_ARCHIVE_SHA256 = "82302a7db4fc1b34e0b6676326610438d43b816bdf11a69d1d012a464ef2f92e"

#: Calibration cells behind the tables. No validation or holdout cell
#: contributed a knot, and the holdout cell's trajectories were never read.
OCV_V2_CALIBRATION_CELLS = ('B0005', 'B0018', 'B0033', 'B0038', 'B0042')

#: Declared cell-temperature bands, in degrees Celsius, and the rule that
#: decides which band a run is predicted in. The rule reads the chamber ambient
#: and the nominal load, both known before the run, so the curve a trajectory is
#: predicted with never depends on the prediction.
CELL_TEMPERATURE_BANDS = (('cold', -40.0, 20.0), ('warm', 20.0, 120.0))
COLD_AMBIENT_CEILING_C = 10.0
COLD_CURRENT_CEILING_A = 2.0

#: Charge state the ohmic shape is normalized at.
R0_SHAPE_REFERENCE_Z = 0.5


def band_for(ambient_temperature_c: float, nominal_current_a: float) -> str:
    """Which declared band a run belongs to, from its declared condition.

    Ambient alone will not do: at 4 degC a 1 A discharge stays near 10 degC while
    a 4 A discharge self-heats past 40 degC, so the nominal load is part of the
    condition that decides the band.
    """
    if (
        ambient_temperature_c <= COLD_AMBIENT_CEILING_C
        and abs(nominal_current_a) <= COLD_CURRENT_CEILING_A
    ):
        return "cold"
    return "warm"


# ---------------------------------------------------------------------------
# cold band
# ---------------------------------------------------------------------------

#: Charge/discharge pairs behind each knot, in knot order.
COLD_SUPPORT_PAIRS = (22, 22, 22, 22, 22, 22, 22, 22, 22, 22, 22, 22, 22, 22, 22, 22, 22, 22, 22, 22)

#: Interquartile spread across those pairs at each knot, in volts. The
#: authority's own scatter, carried into the uncertainty budget as an
#: open-circuit-voltage contribution. It is not a measurement uncertainty, which
#: this source does not state.
COLD_KNOT_SPREAD_V = (0.026107, 0.034048, 0.019731, 0.008864, 0.01348, 0.02016, 0.021017, 0.011949, 0.007843, 0.005067, 0.007545, 0.007637, 0.013343, 0.012055, 0.013108, 0.009488, 0.010234, 0.014837, 0.01756, 0.003307)

#: (charge state, open-circuit voltage) in dimensionless and volt.
COLD_KNOTS = (
    (0.05, 3.212006),
    (0.1, 3.383302),
    (0.15, 3.487991),
    (0.2, 3.562823),
    (0.25, 3.613714),
    (0.3, 3.659823),
    (0.35, 3.69045),
    (0.4, 3.718311),
    (0.45, 3.741529),
    (0.5, 3.760397),
    (0.55, 3.78389),
    (0.6, 3.80798),
    (0.65, 3.837703),
    (0.7, 3.874048),
    (0.75, 3.908219),
    (0.8, 3.947686),
    (0.85, 3.991123),
    (0.9, 4.05098),
    (0.95, 4.132828),
    (1.0, 4.176629),
)

COLD_LOWER = 0.05
COLD_UPPER = 1.0

COLD_OCV_CURVE = DeclaredCurve(
    quantity="open_circuit_voltage",
    against=ctx.STATE_OF_CHARGE,
    against_unit=ctx.DIMENSIONLESS,
    unit=ctx.VOLTAGE_UNIT,
    lower=COLD_LOWER,
    upper=COLD_UPPER,
    form=TabulatedForm(samples=COLD_KNOTS, interpolation=Interpolation.LINEAR),
    source=(
        "NASA Ames Prognostics Center of Excellence Li-ion Battery Aging Data "
        "Set, archive sha256 82302a7db4fc...; pseudo-OCV by charge/discharge "
        "branch averaging on calibration cells B0005, B0018, B0033, B0038, B0042, at a median cell "
        "temperature in the cold band"
    ),
    description=(
        "Pseudo-OCV against charge state on a measured available-charge basis, "
        "conditioned on the cold cell-temperature band (-40.0 to "
        "20.0 degC). Not an equilibrium open-circuit voltage."
    ),
)

#: Multiplicative shape for the ohmic resistance against charge state, from the
#: measured charge/discharge branch difference divided by the current sum,
#: normalized to one at R0_SHAPE_REFERENCE_Z. It carries no fitted parameter:
#: every measured value is a median of calibration measurements.
#:
#: The branch-difference method measures a resistance only where the two
#: branches overlap in charge state, and that is the interval below. Outside it
#: the shape is HELD at its end value -- visible here as a repeated value at the
#: table's edge. Holding is a declared approximation; extrapolating the trend
#: would invent a resistance the branches never saw, and refusing would refuse
#: most of every trajectory.
COLD_R0_SHAPE_MEASURED_INTERVAL = (0.05, 0.5)

COLD_R0_SHAPE_KNOTS = (
    (0.05, 1.699552),
    (0.1, 1.542431),
    (0.15, 1.452293),
    (0.2, 1.390327),
    (0.25, 1.308149),
    (0.3, 1.246196),
    (0.35, 1.180715),
    (0.4, 1.118599),
    (0.45, 1.066438),
    (0.5, 1.0),
    (1.0, 1.0),
)

COLD_R0_SHAPE = DeclaredCurve(
    quantity="ohmic_resistance_charge_state_shape",
    against=ctx.STATE_OF_CHARGE,
    against_unit=ctx.DIMENSIONLESS,
    unit=ctx.DIMENSIONLESS,
    lower=0.05,
    upper=1.0,
    form=TabulatedForm(
        samples=COLD_R0_SHAPE_KNOTS, interpolation=Interpolation.LINEAR
    ),
    source=(
        "measured charge/discharge branch difference divided by the current "
        "sum, on calibration cells only; a measurement, not a fitted parameter"
    ),
    description=(
        "Ohmic resistance against charge state relative to its value at charge "
        "state 0.5, in the cold cell-temperature band."
    ),
)


# ---------------------------------------------------------------------------
# warm band
# ---------------------------------------------------------------------------

#: Charge/discharge pairs behind each knot, in knot order.
WARM_SUPPORT_PAIRS = (177, 177, 178, 178, 178, 178, 178, 178, 178, 178, 178, 178, 178, 178, 178, 178, 178, 178, 178)

#: Interquartile spread across those pairs at each knot, in volts. The
#: authority's own scatter, carried into the uncertainty budget as an
#: open-circuit-voltage contribution. It is not a measurement uncertainty, which
#: this source does not state.
WARM_KNOT_SPREAD_V = (0.036969, 0.025297, 0.017965, 0.017952, 0.015122, 0.012582, 0.01203, 0.01782, 0.022929, 0.023546, 0.021799, 0.017675, 0.02588, 0.032549, 0.033015, 0.028754, 0.030127, 0.028631, 0.004996)

#: (charge state, open-circuit voltage) in dimensionless and volt.
WARM_KNOTS = (
    (0.1, 3.646438),
    (0.15, 3.691172),
    (0.2, 3.720488),
    (0.25, 3.74081),
    (0.3, 3.759516),
    (0.35, 3.777179),
    (0.4, 3.795728),
    (0.45, 3.816189),
    (0.5, 3.840946),
    (0.55, 3.86968),
    (0.6, 3.897041),
    (0.65, 3.927175),
    (0.7, 3.94972),
    (0.75, 3.962136),
    (0.8, 3.994644),
    (0.85, 4.036589),
    (0.9, 4.085687),
    (0.95, 4.146164),
    (1.0, 4.18772),
)

WARM_LOWER = 0.1
WARM_UPPER = 1.0

WARM_OCV_CURVE = DeclaredCurve(
    quantity="open_circuit_voltage",
    against=ctx.STATE_OF_CHARGE,
    against_unit=ctx.DIMENSIONLESS,
    unit=ctx.VOLTAGE_UNIT,
    lower=WARM_LOWER,
    upper=WARM_UPPER,
    form=TabulatedForm(samples=WARM_KNOTS, interpolation=Interpolation.LINEAR),
    source=(
        "NASA Ames Prognostics Center of Excellence Li-ion Battery Aging Data "
        "Set, archive sha256 82302a7db4fc...; pseudo-OCV by charge/discharge "
        "branch averaging on calibration cells B0005, B0018, B0033, B0038, B0042, at a median cell "
        "temperature in the warm band"
    ),
    description=(
        "Pseudo-OCV against charge state on a measured available-charge basis, "
        "conditioned on the warm cell-temperature band (20.0 to "
        "120.0 degC). Not an equilibrium open-circuit voltage."
    ),
)

#: Multiplicative shape for the ohmic resistance against charge state, from the
#: measured charge/discharge branch difference divided by the current sum,
#: normalized to one at R0_SHAPE_REFERENCE_Z. It carries no fitted parameter:
#: every measured value is a median of calibration measurements.
#:
#: The branch-difference method measures a resistance only where the two
#: branches overlap in charge state, and that is the interval below. Outside it
#: the shape is HELD at its end value -- visible here as a repeated value at the
#: table's edge. Holding is a declared approximation; extrapolating the trend
#: would invent a resistance the branches never saw, and refusing would refuse
#: most of every trajectory.
WARM_R0_SHAPE_MEASURED_INTERVAL = (0.05, 0.8)

WARM_R0_SHAPE_KNOTS = (
    (0.05, 1.261313),
    (0.1, 1.042953),
    (0.15, 1.002342),
    (0.2, 0.999849),
    (0.25, 0.997921),
    (0.3, 0.995303),
    (0.35, 0.998298),
    (0.4, 0.999962),
    (0.45, 1.004107),
    (0.5, 1.0),
    (0.55, 1.004245),
    (0.6, 1.010544),
    (0.65, 0.997664),
    (0.7, 0.970969),
    (0.75, 0.904529),
    (0.8, 0.831929),
    (1.0, 0.831929),
)

WARM_R0_SHAPE = DeclaredCurve(
    quantity="ohmic_resistance_charge_state_shape",
    against=ctx.STATE_OF_CHARGE,
    against_unit=ctx.DIMENSIONLESS,
    unit=ctx.DIMENSIONLESS,
    lower=0.05,
    upper=1.0,
    form=TabulatedForm(
        samples=WARM_R0_SHAPE_KNOTS, interpolation=Interpolation.LINEAR
    ),
    source=(
        "measured charge/discharge branch difference divided by the current "
        "sum, on calibration cells only; a measurement, not a fitted parameter"
    ),
    description=(
        "Ohmic resistance against charge state relative to its value at charge "
        "state 0.5, in the warm cell-temperature band."
    ),
)


#: Curve and ohmic shape per declared band, for a caller with a band.
OCV_V2_CURVES = {
    "cold": COLD_OCV_CURVE,
    "warm": WARM_OCV_CURVE,
}

R0_V2_SHAPES = {
    "cold": COLD_R0_SHAPE,
    "warm": WARM_R0_SHAPE,
}

__all__ = [
    "CELL_TEMPERATURE_BANDS",
    "COLD_AMBIENT_CEILING_C",
    "COLD_CURRENT_CEILING_A",
    "COLD_KNOTS",
    "COLD_KNOT_SPREAD_V",
    "COLD_LOWER",
    "COLD_OCV_CURVE",
    "COLD_R0_SHAPE",
    "COLD_R0_SHAPE_KNOTS",
    "COLD_R0_SHAPE_MEASURED_INTERVAL",
    "COLD_SUPPORT_PAIRS",
    "COLD_UPPER",
    "OCV_V2_ARCHIVE_SHA256",
    "OCV_V2_CALIBRATION_CELLS",
    "OCV_V2_CURVES",
    "OCV_V2_SOURCE_RECORD",
    "OCV_V2_SOURCE_SHA256",
    "R0_SHAPE_REFERENCE_Z",
    "R0_V2_SHAPES",
    "WARM_KNOTS",
    "WARM_KNOT_SPREAD_V",
    "WARM_LOWER",
    "WARM_OCV_CURVE",
    "WARM_R0_SHAPE",
    "WARM_R0_SHAPE_KNOTS",
    "WARM_R0_SHAPE_MEASURED_INTERVAL",
    "WARM_SUPPORT_PAIRS",
    "WARM_UPPER",
    "band_for",
]
