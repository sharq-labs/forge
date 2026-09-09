"""Run the whole Forge Core performance suite, sequentially, into one report.

Sequential on purpose. Running benchmark modules in parallel would have them
compete for the same cores and turbo budget, and every number in the result
would then describe the scheduler rather than the code.

    python benchmarks/performance/run_suite.py            # everything
    python benchmarks/performance/run_suite.py units freeze
    python benchmarks/performance/run_suite.py --stability
"""

from __future__ import annotations

import importlib
import pathlib
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import common  # noqa: E402

MODULES = (
    "bench_units",
    "bench_problem",
    "bench_applicability",
    "bench_dependency_dag",
    "bench_validity",
    "bench_evidence",
    "bench_consensus",
    "bench_provenance",
    "bench_serialization",
    "bench_freeze",
    "bench_end_to_end_core",
)


def stability_report() -> None:
    """What this machine's own answer does when nothing changes.

    Run this before believing any before/after comparison. It is the number
    that decides whether a timing threshold is a guard or a coin flip.
    """
    from engcore.scientific.models.definition import ValidityDomain
    from engcore.scientific.units.quantity import Quantity

    domain = ValidityDomain(conditions=common.range_conditions(100))
    context = common.condition_context(100)

    print("\nMACHINE STABILITY (same work, repeated rounds)")
    print(f"{'operation':34} {'p50 min':>10} {'p50 max':>10} {'spread %':>10}")
    print("-" * 68)
    for name, operation in (
        ("units.normalize_unit", lambda: __import__(
            "engcore.scientific.units.quantity", fromlist=["x"]
        ).normalize_unit("watt/meter/kelvin")),
        ("Quantity.construct", lambda: Quantity(1.0, "kelvin")),
        ("applicability.assess(100)", lambda: domain.assess(context)),
    ):
        s = common.stability(operation, rounds=7, samples=60)
        print(f"{name:34} {s['p50_min_ms']:10.5f} {s['p50_max_ms']:10.5f} "
              f"{s['spread_pct']:10.1f}")


def main(argv: list[str]) -> int:
    selected = [a for a in argv if not a.startswith("--")]
    names = [
        m for m in MODULES
        if not selected or any(s in m for s in selected)
    ]

    machine = common.machine_record()
    print("FORGE CORE PERFORMANCE SUITE")
    print(f"  commit      {machine['commit'][:12]} ({machine['branch']})")
    print(f"  tree clean  {machine['tree_clean']}")
    print(f"  python      {machine['python']} on {machine['platform']}")
    print(f"  logical cpu {machine['logical_cpus']}")

    if "--stability" in argv:
        stability_report()
        return 0

    every = []
    for name in names:
        module = importlib.import_module(name)
        start = time.perf_counter()
        measurements = module.run()
        elapsed = time.perf_counter() - start
        common.report(f"{name}  ({elapsed:.1f}s)", measurements)
        extra = {}
        if hasattr(module, "call_counts"):
            extra["call_counts"] = module.call_counts()
        common.write_results(name, measurements, extra=extra or None)
        every.extend(measurements)

    # ONLY a full run writes the combined record. A selective run
    # (`run_suite.py units`) that overwrote `_suite.json` would replace the
    # whole-suite baseline with a fragment of it, and the next before/after
    # comparison would compare against that fragment without saying so --
    # which is exactly what happened once while this round was being run, and
    # was caught only because the comparison reported 20 rows instead of 166.
    if len(names) == len(MODULES):
        common.write_results("_suite", every)
    else:
        print(f"\npartial run ({len(names)} of {len(MODULES)} modules): "
              f"_suite.json left untouched")
    print(f"{len(every)} measurements written to {common.RESULTS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
