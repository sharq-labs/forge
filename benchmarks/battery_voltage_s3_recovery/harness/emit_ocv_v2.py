"""Emit the recovery's banded open-circuit voltage authority as a module.

Same reason as Sprint 3's emitter: a curve is a model artifact, it cannot
travel as a port value, and a different curve is a different model. So it is
generated once from ``evidence/OCV_AUTHORITY_V2.json`` into source and a test
pins the two together.

One thing is emitted that Sprint 3 had no need for: **two curves**, one per
declared cell-temperature band. Pooling them widens the spread past the frozen
acceptance tolerance -- they differ by 80 mV at the median knot and 263 mV at
the bottom -- so one curve cannot serve both.

    python benchmarks/battery_voltage_s3_recovery/harness/emit_ocv_v2.py
"""

from __future__ import annotations

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
BENCH = os.path.dirname(HERE)
ROOT = os.path.dirname(os.path.dirname(BENCH))
EVIDENCE = os.path.join(BENCH, "evidence")
TARGET = os.path.join(
    ROOT, "src", "engcore", "domains", "battery", "flagship_ocv_v2.py"
)

HEADER = '''"""The recovery's banded open-circuit voltage authority.

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
OCV_V2_SOURCE_SHA256 = "{source_sha256}"
OCV_V2_ARCHIVE_SHA256 = "{archive_sha256}"

#: Calibration cells behind the tables. No validation or holdout cell
#: contributed a knot, and the holdout cell's trajectories were never read.
OCV_V2_CALIBRATION_CELLS = {calibration_cells}

#: Declared cell-temperature bands, in degrees Celsius, and the rule that
#: decides which band a run is predicted in. The rule reads the chamber ambient
#: and the nominal load, both known before the run, so the curve a trajectory is
#: predicted with never depends on the prediction.
CELL_TEMPERATURE_BANDS = {bands}
COLD_AMBIENT_CEILING_C = {cold_ambient_ceiling}
COLD_CURRENT_CEILING_A = {cold_current_ceiling}


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
'''

CURVE_TEMPLATE = '''

# ---------------------------------------------------------------------------
# {band} band
# ---------------------------------------------------------------------------

#: Charge/discharge pairs behind each knot, in knot order.
{upper}_SUPPORT_PAIRS = {support}

#: Interquartile spread across those pairs at each knot, in volts. The
#: authority's own scatter, carried into the uncertainty budget as an
#: open-circuit-voltage contribution. It is not a measurement uncertainty, which
#: this source does not state.
{upper}_KNOT_SPREAD_V = {spread}

#: (charge state, open-circuit voltage) in dimensionless and volt.
{upper}_KNOTS = {knots}

{upper}_LOWER = {lower}
{upper}_UPPER = {upper_bound}

{upper}_OCV_CURVE = DeclaredCurve(
    quantity="open_circuit_voltage",
    against=ctx.STATE_OF_CHARGE,
    against_unit=ctx.DIMENSIONLESS,
    unit=ctx.VOLTAGE_UNIT,
    lower={upper}_LOWER,
    upper={upper}_UPPER,
    form=TabulatedForm(samples={upper}_KNOTS, interpolation=Interpolation.LINEAR),
    source=(
        "NASA Ames Prognostics Center of Excellence Li-ion Battery Aging Data "
        "Set, archive sha256 {archive_short}...; pseudo-OCV by charge/discharge "
        "branch averaging on calibration cells {cells_text}, at a median cell "
        "temperature in the {band} band"
    ),
    description=(
        "Pseudo-OCV against charge state on a measured available-charge basis, "
        "conditioned on the {band} cell-temperature band ({band_low} to "
        "{band_high} degC). Not an equilibrium open-circuit voltage."
    ),
)
'''


def sha256_file(path: str) -> str:
    import hashlib

    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 22), b""):
            h.update(block)
    return h.hexdigest()


def main() -> int:
    source = os.path.join(EVIDENCE, "OCV_AUTHORITY_V2.json")
    with open(source, encoding="utf-8") as handle:
        record = json.load(handle)

    bands = {
        item["band"]: (item["low"], item["high"])
        for item in record["cell_temperature_bands_c"]
    }
    cells = tuple(record["calibration_cells"])
    text = HEADER.format(
        source_sha256=sha256_file(source),
        archive_sha256=record["archive_sha256"],
        calibration_cells=repr(cells),
        bands=repr(tuple((k, v[0], v[1]) for k, v in sorted(bands.items()))),
        cold_ambient_ceiling=10.0,
        cold_current_ceiling=2.0,
    )

    exported: list[str] = [
        "CELL_TEMPERATURE_BANDS",
        "COLD_AMBIENT_CEILING_C",
        "COLD_CURRENT_CEILING_A",
        "OCV_V2_ARCHIVE_SHA256",
        "OCV_V2_CALIBRATION_CELLS",
        "OCV_V2_SOURCE_RECORD",
        "OCV_V2_SOURCE_SHA256",
        "band_for",
    ]
    for band in ("cold", "warm"):
        curve = record["curves"].get(band)
        if curve is None:
            raise SystemExit(f"the record carries no {band} curve")
        upper = band.upper()
        text += CURVE_TEMPLATE.format(
            band=band,
            upper=upper,
            support=repr(tuple(curve["support_pairs_per_knot"])),
            spread=repr(tuple(curve["interquartile_spread_v"])),
            knots=_tuple_block(list(zip(curve["knots"], curve["values_v"]))),
            lower=curve["knots"][0],
            upper_bound=curve["knots"][-1],
            archive_short=record["archive_sha256"][:12],
            cells_text=", ".join(cells),
            band_low=bands[band][0],
            band_high=bands[band][1],
        )
        exported.extend(
            [
                f"{upper}_KNOTS",
                f"{upper}_KNOT_SPREAD_V",
                f"{upper}_LOWER",
                f"{upper}_OCV_CURVE",
                f"{upper}_SUPPORT_PAIRS",
                f"{upper}_UPPER",
            ]
        )

    text += "\n\n#: The curve per declared band, for a caller that has a band.\n"
    text += "OCV_V2_CURVES = {\n"
    for band in ("cold", "warm"):
        text += f'    "{band}": {band.upper()}_OCV_CURVE,\n'
    text += "}\n"
    exported.append("OCV_V2_CURVES")

    text += "\n__all__ = [\n"
    for name in sorted(exported):
        text += f'    "{name}",\n'
    text += "]\n"

    with open(TARGET, "wb") as handle:
        handle.write(text.encode("utf-8"))
    print(f"wrote {TARGET} ({len(text)} chars)")
    for band in ("cold", "warm"):
        curve = record["curves"][band]
        print(
            f"  {band}: {len(curve['knots'])} knots over "
            f"[{curve['knots'][0]}, {curve['knots'][-1]}]"
        )
    return 0


def _tuple_block(pairs) -> str:
    lines = ["("]
    for a, b in pairs:
        lines.append(f"    ({a}, {b}),")
    lines.append(")")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
