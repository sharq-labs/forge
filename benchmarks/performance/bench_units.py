"""Unit normalisation, dimensionality and Quantity arithmetic.

**This module was added because measurement demanded it, not because the plan
listed it.** A reconnaissance profile of one real electro-thermal benchmark case
attributed roughly 61% of warm runtime to unit handling: `normalize_unit` called
65,520 times and pint's `format_unit` 78,020 times across 20 cases. Nothing else
in the profile came close, and none of it was solver arithmetic.

So the unit layer gets its own benchmark, and its own call counters. The counts
matter more than the milliseconds: "this path parses a unit string N times per
operation" is reproducible anywhere, and it is the statement that identifies
repeated work as repeated rather than merely slow.
"""

from __future__ import annotations

import common
from common import CallCounter, Measurement, measure


def run() -> list[Measurement]:
    from engcore.scientific.units import quantity as q
    from engcore.scientific.units.quantity import Quantity

    out: list[Measurement] = []

    # --- the two primitives everything else is built on -------------------
    out.append(measure(
        "units.normalize_unit", lambda: "watt/meter/kelvin",
        lambda u: q.normalize_unit(u),
        scale="TINY", size=1, samples=300, inner=50,
        note="one unit string, canonicalised",
    ))
    out.append(measure(
        "units.dimension_of", lambda: "watt/meter/kelvin",
        lambda u: q.dimension_of(u),
        scale="TINY", size=1, samples=300, inner=50,
        note="one unit string, to a comparable dimensionality",
    ))
    out.append(measure(
        "units.dimensionality", lambda: "watt/meter/kelvin",
        lambda u: q.dimensionality(u),
        scale="TINY", size=1, samples=200, inner=20,
        note="canonical string rendering",
    ))

    # --- the operations a domain actually performs -------------------------
    out.append(measure(
        "units.Quantity.construct", lambda: None,
        lambda _: Quantity(300.0, "kelvin"),
        scale="TINY", size=1, samples=300, inner=50,
    ))
    out.append(measure(
        "units.Quantity.is_compatible_with",
        lambda: (Quantity(300.0, "kelvin"), Quantity(1.0, "kelvin")),
        lambda pair: pair[0].is_compatible_with(pair[1]),
        scale="TINY", size=1, samples=300, inner=50,
    ))
    out.append(measure(
        "units.Quantity.to", lambda: Quantity(300.0, "kelvin"),
        lambda quantity: quantity.to("millikelvin"),
        scale="TINY", size=1, samples=300, inner=20,
    ))
    out.append(measure(
        "units.Quantity.magnitude_in", lambda: Quantity(300.0, "kelvin"),
        lambda quantity: quantity.magnitude_in("kelvin"),
        scale="TINY", size=1, samples=300, inner=20,
        note="same unit -- the common case, and the one worth being cheap",
    ))
    out.append(measure(
        "units.Quantity.add", lambda: (Quantity(1.0, "watt"), Quantity(2.0, "watt")),
        lambda pair: pair[0] + pair[1],
        scale="TINY", size=1, samples=300, inner=20,
    ))

    # --- a realistic mixed batch, at scale ---------------------------------
    for scale, size in (("SMALL", 100), ("MEDIUM", 1_000), ("LARGE", 10_000)):
        out.append(measure(
            "units.compat_check_batch",
            lambda size=size: [
                Quantity(1.0, u) for u in common.units_cycle(size)
            ],
            lambda qs: [x.is_compatible_with(x.units) for x in qs],
            scale=scale, size=size, samples=30, warmup=3,
            measure_memory=(size == 10_000),
            note="one compatibility check per quantity",
        ))

    return out


def call_counts() -> dict:
    """How many times the unit primitives run for one representative operation.

    Deterministic, machine-independent, and the basis of the scaling guard.
    """
    from engcore.scientific.units import quantity as q
    from engcore.scientific.units.quantity import Quantity

    counts: dict = {}

    a, b = Quantity(300.0, "kelvin"), Quantity(1.0, "kelvin")
    with CallCounter(q, "normalize_unit") as normalize, \
         CallCounter(q, "dimension_of") as dimension:
        a.is_compatible_with(b)
    counts["is_compatible_with"] = {
        "normalize_unit": normalize.count, "dimension_of": dimension.count
    }

    with CallCounter(q, "normalize_unit") as normalize:
        Quantity(300.0, "kelvin")
    counts["Quantity.__post_init__"] = {"normalize_unit": normalize.count}

    with CallCounter(q, "normalize_unit") as normalize:
        a.to("millikelvin")
    counts["Quantity.to"] = {"normalize_unit": normalize.count}

    with CallCounter(q, "normalize_unit") as normalize:
        a.magnitude_in("kelvin")
    counts["Quantity.magnitude_in"] = {"normalize_unit": normalize.count}

    return counts


if __name__ == "__main__":
    measurements = run()
    common.report("UNITS", measurements)
    print("\ncall counts per operation:")
    for operation, counted in call_counts().items():
        print(f"  {operation:32} {counted}")
    print("\nwrote", common.write_results("bench_units", measurements,
                                          extra={"call_counts": call_counts()}))
