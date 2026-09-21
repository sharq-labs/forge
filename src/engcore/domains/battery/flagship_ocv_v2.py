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
The rating is about 30 % above what these cells deliver and wrong by a different
amount for each, so pairs at different true depths of discharge landed on the
same knot of the old curve.

**Two bands, and no interpolation between them.** Conditioned on the median
measured cell temperature over the loaded discharge, the two bands differ by
80 mV at the median knot and 263 mV at the bottom -- far outside the frozen
50 mV acceptance tolerance. Pooling them collapses the admissible interval to
three knots, which is the evidence that they are two relations rather than one.
There is nothing measured between 13 and 23 degC in this archive, so the gap
between the bands carries no curve and the model refuses there.

**No charge-state axis on the ohmic resistance.** The branch-difference
resistance does fall from 0.201 to 0.133 ohm across charge state when warm and
from 0.499 to 0.294 ohm when cold, and that measurement is published in the
source record. A candidate carrying it as a multiplicative shape was fitted and
judged on validation and was **not** selected: with one parameter set per
declared calibration block it bought 2.4 mV of mean absolute error and gave back
2.1 mV of 95th percentile, which is not an independent improvement. So the
selected model has no charge-state axis on the ohmic resistance, and the
measurement stays where an unpromoted measurement belongs.

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


#: The curve per declared band, for a caller that has a band.
OCV_V2_CURVES = {
    "cold": COLD_OCV_CURVE,
    "warm": WARM_OCV_CURVE,
}

__all__ = [
    "CELL_TEMPERATURE_BANDS",
    "COLD_AMBIENT_CEILING_C",
    "COLD_CURRENT_CEILING_A",
    "COLD_KNOTS",
    "COLD_KNOT_SPREAD_V",
    "COLD_LOWER",
    "COLD_OCV_CURVE",
    "COLD_SUPPORT_PAIRS",
    "COLD_UPPER",
    "OCV_V2_ARCHIVE_SHA256",
    "OCV_V2_CALIBRATION_CELLS",
    "OCV_V2_CURVES",
    "OCV_V2_SOURCE_RECORD",
    "OCV_V2_SOURCE_SHA256",
    "WARM_KNOTS",
    "WARM_KNOT_SPREAD_V",
    "WARM_LOWER",
    "WARM_OCV_CURVE",
    "WARM_SUPPORT_PAIRS",
    "WARM_UPPER",
    "band_for",
]
