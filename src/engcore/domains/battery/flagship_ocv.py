"""The frozen open-circuit voltage authority of the Sprint 3 flagship.

Generated from ``benchmarks/battery_thermal_flagship_s3/evidence/OCV_AUTHORITY.json``
by ``benchmarks/battery_thermal_flagship_s3/harness/emit_ocv_module.py``. Do not
edit the table by hand: regenerate it, and let the test that compares this
module against that record catch the difference.

Why the curve lives in source rather than in a run
---------------------------------------------------
It is a model artifact. A port carries a Quantity, so a curve cannot travel as
one; and it should not, because replacing the open-circuit voltage relation
replaces the model. Freezing it here makes it versioned with the pack that
executes it, and its digest is part of that pack's identity.

What it is
----------
A pseudo-OCV, from the charge and discharge branches of single calibration
cells at 22-24 degC ambient, averaged so the ohmic and polarization drops
cancel to first order. Its top knot, at full charge, is a directly measured
relaxed voltage rather than a reconstruction.

What it is not
--------------
Not an equilibrium open-circuit voltage: branch averaging does not cancel the
hysteresis between the two directions, and the branches are not at identical
temperature. It carries no temperature axis and does not claim one. Outside its
declared charge-state interval it returns OUTSIDE_VALIDATED_DOMAIN and the
flagship kernel propagates that refusal rather than reaching past it.
"""

from __future__ import annotations

from ...scientific.models.curves import (
    DeclaredCurve,
    Interpolation,
    TabulatedForm,
)
from . import context as ctx

#: The declared charge-state basis: ``z = 1 - q / CHARGE_STATE_BASIS_AH``, with
#: ``q`` the measured charge removed. The manufacturer's rating, not a fit.
CHARGE_STATE_BASIS_AH = 2.0

#: Source record this table was generated from, and the archive behind it.
OCV_SOURCE_RECORD = "benchmarks/battery_thermal_flagship_s3/evidence/OCV_AUTHORITY.json"
OCV_ARCHIVE_SHA256 = "82302a7db4fc1b34e0b6676326610438d43b816bdf11a69d1d012a464ef2f92e"

#: Calibration cells the curve was derived from. No validation or locked-holdout
#: cell contributed a single knot.
OCV_CALIBRATION_CELLS = ('B0005', 'B0018', 'B0033', 'B0038', 'B0042')

#: Charge/discharge pairs behind each knot, in knot order.
OCV_SUPPORT_PAIRS = (7, 14, 22, 23, 23, 23, 23, 24, 26, 27, 27, 27, 27, 27, 27, 27, 27, 27, 27, 27, 27)

#: Interquartile spread across those pairs at each knot, in volts. This is the
#: authority's own scatter and is carried into the uncertainty budget as an
#: open-circuit-voltage contribution; it is not a measurement uncertainty, which
#: this source does not state.
OCV_KNOT_SPREAD_V = (0.138456, 0.130566, 0.126786, 0.068424, 0.042138, 0.029976, 0.026801, 0.024056, 0.022271, 0.022861, 0.023549, 0.027092, 0.031324, 0.032455, 0.034747, 0.040474, 0.035541, 0.034921, 0.032643, 0.033648, 0.012611)

#: (charge state, open-circuit voltage) in dimensionless and volt.
OCV_KNOTS = (
    (0.092169, 3.322819),
    (0.137561, 3.550152),
    (0.182952, 3.601401),
    (0.228344, 3.671574),
    (0.273736, 3.709501),
    (0.319127, 3.736364),
    (0.364519, 3.757603),
    (0.40991, 3.77609),
    (0.455302, 3.792327),
    (0.500693, 3.811906),
    (0.546085, 3.836547),
    (0.591476, 3.864281),
    (0.636868, 3.894139),
    (0.682259, 3.924321),
    (0.727651, 3.934381),
    (0.773042, 3.954324),
    (0.818434, 3.984922),
    (0.863825, 4.028428),
    (0.909217, 4.082983),
    (0.954608, 4.14309),
    (1.0, 4.188513),
)

OCV_LOWER = 0.092169
OCV_UPPER = 1.0

FLAGSHIP_OCV_CURVE = DeclaredCurve(
    quantity="open_circuit_voltage",
    against=ctx.STATE_OF_CHARGE,
    against_unit=ctx.DIMENSIONLESS,
    unit=ctx.VOLTAGE_UNIT,
    lower=OCV_LOWER,
    upper=OCV_UPPER,
    form=TabulatedForm(samples=OCV_KNOTS, interpolation=Interpolation.LINEAR),
    source=(
        "NASA Ames Prognostics Center of Excellence Li-ion Battery Aging Data "
        "Set, archive sha256 82302a7db4fc...; pseudo-OCV by charge/discharge "
        "branch averaging on calibration cells B0005, B0018, B0033, B0038, B0042"
    ),
    description=(
        "Pseudo-OCV against charge state on a declared 2 Ah basis, at 22-24 "
        "degC ambient. Not an equilibrium open-circuit voltage: it carries the "
        "hysteresis between the charge and discharge directions and has no "
        "temperature axis."
    ),
)

__all__ = [
    "CHARGE_STATE_BASIS_AH",
    "FLAGSHIP_OCV_CURVE",
    "OCV_ARCHIVE_SHA256",
    "OCV_CALIBRATION_CELLS",
    "OCV_KNOTS",
    "OCV_KNOT_SPREAD_V",
    "OCV_LOWER",
    "OCV_SOURCE_RECORD",
    "OCV_SUPPORT_PAIRS",
    "OCV_UPPER",
]
