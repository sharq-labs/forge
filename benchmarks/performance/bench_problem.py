"""ScientificProblem construction: the validation a problem pays once, up front.

``__post_init__`` runs a series of whole-problem cross-checks -- unique names,
condition targets, condition dimensions, objective metrics, metric coherence --
each of which walks the declaration. The axis here is the number of declared
variables, parameters and constraints together, so the growth of that stack of
passes is visible as one curve.

Serialization is measured separately: a problem is built once and serialized
whenever it crosses a boundary, so the two have different call frequencies and
deserve different numbers.
"""

from __future__ import annotations

import common
from common import Measurement, measure

SIZES = (("TINY", 10), ("SMALL", 100), ("MEDIUM", 1_000), ("LARGE", 5_000))


def _parts(size: int):
    from engcore.scientific.ir.constraints import (
        ConstraintDefinition,
        ConstraintOperator,
    )
    from engcore.scientific.ir.variables import (
        ScientificParameter,
        ScientificVariable,
    )
    from engcore.scientific.units.quantity import Quantity

    units = common.units_cycle(size)
    variables = tuple(
        ScientificVariable(name=f"var_{i:05d}", unit=units[i]) for i in range(size)
    )
    parameters = tuple(
        ScientificParameter(f"param_{i:05d}", Quantity(float(i) + 1.0, units[i]))
        for i in range(size)
    )
    constraints = tuple(
        ConstraintDefinition(
            name=f"constraint_{i:05d}",
            metric=f"var_{i:05d}",
            operator=ConstraintOperator.LESS_EQUAL,
            bound=Quantity(1e6, units[i]),
        )
        for i in range(size)
    )
    return variables, parameters, constraints


def run() -> list[Measurement]:
    from engcore.scientific.ir.problem import ScientificProblem

    out: list[Measurement] = []
    for scale, size in SIZES:
        variables, parameters, constraints = _parts(size)

        out.append(measure(
            "problem.construct",
            lambda p=(variables, parameters, constraints): p,
            lambda p: ScientificProblem(
                problem_id="perf", name="performance problem",
                variables=p[0], parameters=p[1], constraints=p[2],
            ),
            scale=scale, size=size,
            samples=30 if size >= 1_000 else 100, warmup=5,
            measure_memory=(size == 5_000),
            note="variables + parameters + constraints, each of `size`",
        ))

        problem = ScientificProblem(
            problem_id="perf", name="performance problem",
            variables=variables, parameters=parameters, constraints=constraints,
        )
        out.append(measure(
            "problem.to_dict",
            lambda problem=problem: problem, lambda p: p.to_dict(),
            scale=scale, size=size,
            samples=30 if size >= 1_000 else 100, warmup=5,
        ))
        out.append(measure(
            "problem.parameter_values",
            lambda problem=problem: problem, lambda p: p.parameter_values(),
            scale=scale, size=size,
            samples=30 if size >= 1_000 else 150, warmup=5,
        ))

    return out


if __name__ == "__main__":
    measurements = run()
    common.report("PROBLEM", measurements)
    print("\nwrote", common.write_results("bench_problem", measurements))
