"""The prerequisite dependency graph: topological ordering and cycle detection.

Measured on its own, separately from applicability, because ordering is a
distinct algorithm with a distinct growth curve and burying it inside an
assessment would make a quadratic sort look like an expensive condition.

Three shapes, chosen to bracket the possibilities:

CHAIN   each node depends on the previous. Depth N, width 1. Worst case for a
        naive repeated-scan ordering.
FAN     every node depends on one root. Depth 2, width N.
FLAT    no dependencies at all. The baseline the other two are read against.
"""

from __future__ import annotations

import common
from common import Measurement, measure

SIZES = (("TINY", 10), ("SMALL", 100), ("MEDIUM", 1_000), ("LARGE", 5_000))


def _conditions(size: int, shape: str):
    from engcore.scientific.models.definition import RangeCondition
    from engcore.scientific.units.quantity import Quantity

    bounds = dict(
        minimum=Quantity(0.0, "dimensionless"),
        maximum=Quantity(1.0, "dimensionless"),
    )
    conditions = []
    for i in range(size):
        if shape == "chain":
            requires = (f"condition_{i - 1:05d}",) if i else ()
        elif shape == "fan":
            requires = ("condition_00000",) if i else ()
        else:
            requires = ()
        conditions.append(
            RangeCondition(name=f"condition_{i:05d}", requires=requires, **bounds)
        )
    return tuple(conditions)


def run() -> list[Measurement]:
    from engcore.scientific.models import definition as d

    out: list[Measurement] = []
    for shape in ("flat", "chain", "fan"):
        for scale, size in SIZES:
            conditions = _conditions(size, shape)
            out.append(measure(
                f"dag.order.{shape}",
                lambda conditions=conditions: conditions,
                lambda c: d._dependency_order(c),
                scale=scale, size=size,
                samples=40 if size >= 1_000 else 200, warmup=5,
                measure_memory=(size == 5_000),
                note=f"{shape} graph, {size} nodes",
            ))
    return out


if __name__ == "__main__":
    measurements = run()
    common.report("DEPENDENCY DAG", measurements)
    print("\nwrote", common.write_results("bench_dependency_dag", measurements))
