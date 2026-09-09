"""Cross-solver consensus: comparison over R routes and Q required outputs.

Two independent axes, measured separately, because the comparison is pairwise
over routes and linear over quantities and conflating them would hide which one
grows badly:

  ROUTES    2 / 4 / 8 / 16 at a fixed quantity count. The pairwise inner loop
            is O(R^2) per quantity by construction -- that is what "every route
            agrees with every other" means -- so this axis is expected to grow
            quadratically and the benchmark exists to confirm the constant is
            small, not to be surprised.
  OUTPUTS   10 / 100 / 1,000 / 10,000 quantities at a fixed route count.

``missing_outputs`` is measured on its own: it is R x Q and is consulted by
``output_completeness``, ``reason`` and ``to_dict``.
"""

from __future__ import annotations

import common
from common import Measurement, measure

ROUTE_COUNTS = ((("TINY", 2), ("SMALL", 4), ("MEDIUM", 8), ("LARGE", 16)))
OUTPUT_COUNTS = (("TINY", 10), ("SMALL", 100), ("MEDIUM", 1_000), ("LARGE", 10_000))


def _thresholds():
    from engcore.scientific.results.thresholds import VerificationThresholds

    return VerificationThresholds(
        gate_id="perf.consensus", version="1",
        values={"rel_tol": 1e-9}, basis="performance fixture",
    )


def _routes(count: int):
    from engcore.scientific.consensus import (
        ComponentKind, SharedComponent, SolveRoute,
    )
    from engcore.scientific.solvers.protocol import SolverIdentity

    return tuple(
        SolveRoute(
            route_id=f"route_{i:03d}",
            solver=SolverIdentity(f"solver.{i}", "1.0"),
            components=frozenset(
                {SharedComponent(kind=ComponentKind.IMPLEMENTATION,
                                 name=f"impl_{i:03d}")}
            ),
        )
        for i in range(count)
    )


def _values(routes: int, outputs: int):
    return {
        f"route_{i:03d}": {f"q_{j:05d}": 1.0 + j for j in range(outputs)}
        for i in range(routes)
    }


def run() -> list[Measurement]:
    from engcore.scientific.consensus import CrossSolverConsensus

    thresholds = _thresholds()
    out: list[Measurement] = []

    def build(routes, values, required):
        return CrossSolverConsensus.over(
            consensus_id="perf", routes=routes, values=values,
            thresholds=thresholds, tolerance_key="rel_tol",
            required_outputs=required,
        )

    # --- route axis, quantities fixed at 10 -------------------------------
    for scale, count in ROUTE_COUNTS:
        routes = _routes(count)
        values = _values(count, 10)
        required = tuple(f"q_{j:05d}" for j in range(10))
        out.append(measure(
            "consensus.over.by_routes",
            lambda: None, lambda _: build(routes, values, required),
            scale=scale, size=count, samples=150, warmup=10,
            note="10 quantities; pairwise over routes",
        ))

    # --- quantity axis, routes fixed at 2 ---------------------------------
    for scale, count in OUTPUT_COUNTS:
        routes = _routes(2)
        values = _values(2, count)
        required = tuple(f"q_{j:05d}" for j in range(count))
        out.append(measure(
            "consensus.over.by_outputs",
            lambda: None, lambda _: build(routes, values, required),
            scale=scale, size=count,
            samples=40 if count >= 1_000 else 150, warmup=5,
            measure_memory=(count == 10_000),
            note="2 routes; linear over quantities",
        ))

        consensus = build(routes, values, required)
        out.append(measure(
            "consensus.missing_outputs",
            lambda consensus=consensus: consensus,
            lambda c: c.missing_outputs,
            scale=scale, size=count,
            samples=40 if count >= 1_000 else 200, warmup=5,
            note="routes x required outputs",
        ))
        out.append(measure(
            "consensus.establishes",
            lambda consensus=consensus: consensus,
            lambda c: c.establishes,
            scale=scale, size=count,
            samples=40 if count >= 1_000 else 200, warmup=5,
        ))

    return out


if __name__ == "__main__":
    measurements = run()
    common.report("CONSENSUS", measurements)
    print("\nwrote", common.write_results("bench_consensus", measurements))
