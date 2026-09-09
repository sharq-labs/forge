"""Deep immutability: ``freeze`` on construction and ``detach`` on serialization.

Every scientific record in the core pays ``freeze`` once per mutable container
it is handed, and every ``to_dict`` pays ``detach``. Breadth and depth are
separate axes because the recursion costs differently along each, and a single
"big structure" benchmark would report their sum without saying which dominated.

Re-freezing an already-frozen container is measured on its own: it is supposed
to be a type check rather than a second full pass, and that claim is worth
holding to a number.
"""

from __future__ import annotations

import common
from common import Measurement, measure


def run() -> list[Measurement]:
    from engcore.scientific.results.immutable import detach, freeze

    out: list[Measurement] = []

    for scale, breadth in (("TINY", 10), ("SMALL", 100),
                           ("MEDIUM", 1_000), ("LARGE", 10_000)):
        flat = {f"key_{i:05d}": float(i) for i in range(breadth)}
        out.append(measure(
            "freeze.flat_mapping", lambda flat=flat: flat, lambda m: freeze(m),
            scale=scale, size=breadth,
            samples=40 if breadth >= 1_000 else 200, warmup=5,
            measure_memory=(breadth == 10_000),
        ))
        frozen = freeze(flat)
        out.append(measure(
            "freeze.already_frozen",
            lambda frozen=frozen: frozen, lambda m: freeze(m),
            scale=scale, size=breadth,
            samples=200, warmup=10, inner=10,
            note="must be a type check, not a second pass",
        ))
        out.append(measure(
            "freeze.detach_flat",
            lambda frozen=frozen: frozen, lambda m: detach(m),
            scale=scale, size=breadth,
            samples=40 if breadth >= 1_000 else 200, warmup=5,
        ))

    for label, breadth, depth in (
        ("wide", 5_000, 1), ("deep", 5, 400), ("both", 100, 50),
    ):
        nested = common.nested_metadata(breadth, depth)
        out.append(measure(
            f"freeze.nested_{label}",
            lambda nested=nested: nested, lambda m: freeze(m),
            scale="MEDIUM", size=breadth * max(depth, 1),
            samples=40, warmup=5, measure_memory=True,
            note=f"breadth={breadth} depth={depth}",
        ))

    return out


if __name__ == "__main__":
    measurements = run()
    common.report("FREEZE / DETACH", measurements)
    print("\nwrote", common.write_results("bench_freeze", measurements))
