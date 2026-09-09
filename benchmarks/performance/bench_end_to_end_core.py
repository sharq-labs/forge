"""THE HEADLINE BENCHMARK: one full core verdict path, no external solver.

The shape a real request takes through the core, with nothing outside it:

    ScientificProblem
      -> model applicability (ValidityDomain.assess)
      -> validity assessment record
      -> result construction (values, uncertainty, validity coverage)
      -> validation report and its attained levels
      -> cross-solver consensus
      -> provenance
      -> canonical serialization

**No solver runs here, and that is the point.** This number is Forge's own
overhead for turning a computed answer into an attributable, checked, serialized
scientific record. It is the figure to quote when asking whether the core is the
bottleneck, and it is deliberately not comparable to a benchmark case time,
which includes the fixed-point solve.

The stages are also measured individually at one scale, so the total can be
attributed rather than just reported.
"""

from __future__ import annotations

import common
from common import Measurement, measure

#: Sizes here are "conditions / values / checks per request", which is the axis
#: a real request grows along. MEDIUM (50) is roughly what a coupled
#: electro-thermal report carries; LARGE and STRESS are past anything currently
#: posed and exist to show the curve.
SIZES = (("TINY", 5), ("SMALL", 20), ("MEDIUM", 50), ("LARGE", 200), ("STRESS", 1_000))


def _fixture(size: int):
    """Everything the path consumes, built once and never timed."""
    from engcore.scientific.consensus import (
        ComponentKind, SharedComponent, SolveRoute,
    )
    from engcore.scientific.models.definition import ValidityDomain
    from engcore.scientific.results.thresholds import VerificationThresholds
    from engcore.scientific.solvers.protocol import SolverIdentity

    domain = ValidityDomain(conditions=common.range_conditions(size))
    context = common.condition_context(size)
    values = common.quantities(size)
    checks = common.validation_checks(size)
    inputs = common.provenance_inputs(size)
    thresholds = VerificationThresholds(
        gate_id="perf.e2e", version="1", values={"rel_tol": 1e-9},
        basis="performance fixture",
    )
    routes = tuple(
        SolveRoute(
            route_id=f"route_{i}",
            solver=SolverIdentity(f"solver.{i}", "1.0"),
            components=frozenset(
                {SharedComponent(kind=ComponentKind.IMPLEMENTATION, name=f"impl_{i}")}
            ),
        )
        for i in range(2)
    )
    quantity_names = tuple(sorted(values))
    route_values = {
        f"route_{i}": {name: float(j) + 0.5 for j, name in enumerate(quantity_names)}
        for i in range(2)
    }
    return {
        "domain": domain, "context": context, "values": values,
        "checks": checks, "inputs": inputs, "thresholds": thresholds,
        "routes": routes, "route_values": route_values,
        "required": quantity_names,
    }


def core_path(f) -> str:
    """One complete request through the core. Returns the serialized record."""
    from engcore.scientific.consensus import CrossSolverConsensus
    from engcore.scientific.results.provenance import ProvenanceRecord
    from engcore.scientific.results.result import ScientificResult
    from engcore.scientific.results.validation import ValidationReport
    from engcore.scientific.serialization import to_json

    assessment = f["domain"].assess(f["context"])

    consensus = CrossSolverConsensus.over(
        consensus_id="perf-e2e", routes=f["routes"], values=f["route_values"],
        thresholds=f["thresholds"], tolerance_key="rel_tol",
        required_outputs=f["required"],
    )

    report = ValidationReport(checks=(*f["checks"], consensus.to_check()))
    levels = report.attained_levels

    provenance = ProvenanceRecord(run_id="perf-e2e", inputs=f["inputs"])
    result = ScientificResult(
        result_id="perf-e2e", values=f["values"], provenance=provenance,
        validation=report,
    )
    assert levels is not None and assessment is not None
    return to_json(result)


def run() -> list[Measurement]:
    out: list[Measurement] = []
    for scale, size in SIZES:
        out.append(measure(
            "e2e.core_verdict_path",
            lambda size=size: _fixture(size),
            core_path,
            scale=scale, size=size,
            samples=30 if size >= 200 else 100, warmup=5,
            measure_memory=True,
            note="no external solver; Forge-owned work only",
        ))

    # Stage attribution at MEDIUM, so the total above can be explained.
    f = _fixture(50)
    from engcore.scientific.consensus import CrossSolverConsensus
    from engcore.scientific.results.provenance import ProvenanceRecord
    from engcore.scientific.results.result import ScientificResult
    from engcore.scientific.results.validation import ValidationReport
    from engcore.scientific.serialization import to_json

    stages = [
        ("e2e.stage.applicability", lambda f: f["domain"].assess(f["context"])),
        ("e2e.stage.consensus", lambda f: CrossSolverConsensus.over(
            consensus_id="s", routes=f["routes"], values=f["route_values"],
            thresholds=f["thresholds"], tolerance_key="rel_tol",
            required_outputs=f["required"])),
        ("e2e.stage.validation_report", lambda f: ValidationReport(
            checks=f["checks"]).attained_levels),
        ("e2e.stage.provenance", lambda f: ProvenanceRecord(
            run_id="s", inputs=f["inputs"])),
        ("e2e.stage.result", lambda f: ScientificResult(
            result_id="s", values=f["values"],
            provenance=ProvenanceRecord(run_id="s"))),
        ("e2e.stage.serialize", lambda f: to_json(ScientificResult(
            result_id="s", values=f["values"],
            provenance=ProvenanceRecord(run_id="s")))),
    ]
    for name, operation in stages:
        out.append(measure(
            name, lambda f=f: f, operation,
            scale="MEDIUM", size=50, samples=100, warmup=10,
        ))

    return out


COLD_SOURCE = """
import sys, time, pathlib
sys.path.insert(0, str(pathlib.Path('src').resolve()))
sys.path.insert(0, str(pathlib.Path('benchmarks/performance').resolve()))
start = time.perf_counter()
import bench_end_to_end_core as b
f = b._fixture(50)
b.core_path(f)
print((time.perf_counter() - start) * 1000.0)
"""

IMPORT_SOURCE = """
import sys, time, pathlib
sys.path.insert(0, str(pathlib.Path('src').resolve()))
start = time.perf_counter()
import engcore.scientific.results.result
import engcore.scientific.consensus
print((time.perf_counter() - start) * 1000.0)
"""


if __name__ == "__main__":
    measurements = run()
    cold = common.cold_measure(COLD_SOURCE)
    import_ms = common.cold_measure(IMPORT_SOURCE)
    common.report("END-TO-END CORE", measurements)
    print(f"\nCOLD (fresh process, imports + one MEDIUM request): {cold:.1f} ms")
    print(f"  of which interpreter import of the core:          {import_ms:.1f} ms")
    print(f"  first-request work after imports:                 {cold - import_ms:.1f} ms")
    print("\nwrote", common.write_results(
        "bench_end_to_end_core", measurements,
        extra={"cold_total_ms": cold, "import_ms": import_ms},
    ))
