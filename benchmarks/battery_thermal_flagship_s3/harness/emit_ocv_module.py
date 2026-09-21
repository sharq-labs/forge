"""Emit the frozen OCV authority as a production module.

The curve is a model artifact, not a run input: it cannot travel as a port
value, its identity must be versioned with the pack that executes it, and a
different curve is a different model. So it is generated once, from
``evidence/OCV_AUTHORITY.json``, into source, and a test pins the two together.
"""

from __future__ import annotations

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
BENCH = os.path.dirname(HERE)
ROOT = os.path.dirname(os.path.dirname(BENCH))
EVIDENCE = os.path.join(BENCH, "evidence")
TARGET = os.path.join(
    ROOT, "src", "engcore", "domains", "battery", "flagship_ocv.py"
)

HEADER = '''"""The frozen open-circuit voltage authority of the Sprint 3 flagship.

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
CHARGE_STATE_BASIS_AH = {basis!r}

#: Source record this table was generated from, and the archive behind it.
OCV_SOURCE_RECORD = "benchmarks/battery_thermal_flagship_s3/evidence/OCV_AUTHORITY.json"
OCV_ARCHIVE_SHA256 = "{archive}"

#: Calibration cells the curve was derived from. No validation or locked-holdout
#: cell contributed a single knot.
OCV_CALIBRATION_CELLS = {cells}

#: Charge/discharge pairs behind each knot, in knot order.
OCV_SUPPORT_PAIRS = {support}

#: Interquartile spread across those pairs at each knot, in volts. This is the
#: authority's own scatter and is carried into the uncertainty budget as an
#: open-circuit-voltage contribution; it is not a measurement uncertainty, which
#: this source does not state.
OCV_KNOT_SPREAD_V = {spreads}

#: (charge state, open-circuit voltage) in dimensionless and volt.
OCV_KNOTS = (
{knots}
)

OCV_LOWER = {lower!r}
OCV_UPPER = {upper!r}

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
        "Set, archive sha256 {archive_short}...; pseudo-OCV by charge/discharge "
        "branch averaging on calibration cells {cells_inline}"
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
'''


def main() -> int:
    with open(os.path.join(EVIDENCE, "OCV_AUTHORITY.json"), encoding="utf-8") as handle:
        record = json.load(handle)

    knots = record["knots"]
    values = record["values_v"]
    if len(knots) != len(values):
        raise SystemExit("knot and value counts disagree")

    lines = "\n".join(
        f"    ({z!r}, {v!r})," for z, v in zip(knots, values)
    )
    cells = tuple(record["calibration_cells"])
    text = HEADER.format(
        basis=record["charge_state_basis_ah"],
        archive=record["archive_sha256"],
        archive_short=record["archive_sha256"][:12],
        cells=repr(cells),
        cells_inline=", ".join(cells),
        support=repr(tuple(record["support_pairs_per_knot"])),
        spreads=repr(tuple(round(x, 6) for x in record["interquartile_spread_v"])),
        knots=lines,
        lower=record["interval"][0],
        upper=record["interval"][1],
    )
    with open(TARGET, "wb") as handle:
        handle.write(text.encode("utf-8"))
    print(f"wrote {TARGET} ({len(text)} chars, {len(knots)} knots)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
