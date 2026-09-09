"""Model applicability: assessing N validity conditions against a context.

The scale axis is the number of declared conditions. Two shapes are measured
separately because they stress different machinery:

FLAT     N independent conditions -- the ordinary case, and a pure measure of
         per-condition evaluation cost.
CHAINED  N conditions each depending on the previous, so the prerequisite graph
         has depth N. This is the worst shape for a topological sort and the
         one that would expose a quadratic ordering.

Both are also measured in the VIOLATED direction, because a failing condition
takes a different path (it builds a reason, and a chained failure short-circuits
every dependent) and a benchmark that only ever passed would miss it.
"""

from __future__ import annotations

import common
from common import Measurement, measure

SIZES = (("TINY", 10), ("SMALL", 100), ("MEDIUM", 1_000), ("LARGE", 10_000))


def run() -> list[Measurement]:
    from engcore.scientific.models.definition import ValidityDomain

    out: list[Measurement] = []

    for scale, size in SIZES:
        flat = ValidityDomain(conditions=common.range_conditions(size))
        satisfied = common.condition_context(size, satisfied=True)
        violated = common.condition_context(size, satisfied=False)

        out.append(measure(
            "applicability.assess.flat.satisfied",
            lambda flat=flat: flat, lambda d, c=satisfied: d.assess(c),
            scale=scale, size=size,
            samples=40 if size >= 1_000 else 150, warmup=5,
            measure_memory=(size == 10_000),
        ))
        out.append(measure(
            "applicability.assess.flat.violated",
            lambda flat=flat: flat, lambda d, c=violated: d.assess(c),
            scale=scale, size=size,
            samples=40 if size >= 1_000 else 150, warmup=5,
        ))

        # The chained shape is capped below LARGE: a depth-10,000 dependency
        # chain is not a scientifically plausible declaration, and running it
        # would be measuring a workload nobody will ever pose.
        if size <= 1_000:
            chained = ValidityDomain(
                conditions=common.range_conditions(size, chain=True)
            )
            out.append(measure(
                "applicability.assess.chained.satisfied",
                lambda chained=chained: chained,
                lambda d, c=satisfied: d.assess(c),
                scale=scale, size=size,
                samples=40 if size >= 1_000 else 150, warmup=5,
            ))
            out.append(measure(
                "applicability.assess.chained.violated",
                lambda chained=chained: chained,
                lambda d, c=violated: d.assess(c),
                scale=scale, size=size,
                samples=40 if size >= 1_000 else 150, warmup=5,
                note="first condition fails; every dependent is unmet",
            ))

    return out


if __name__ == "__main__":
    measurements = run()
    common.report("APPLICABILITY", measurements)
    print("\nwrote", common.write_results("bench_applicability", measurements))
