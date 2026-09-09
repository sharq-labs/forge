"""Measurement machinery and deterministic workloads for the Forge Core performance suite.

WHAT THIS IS FOR, AND WHAT IT IS NOT FOR
-----------------------------------------
The scientific benchmarks in ``benchmarks/hard`` ask **"is the answer right?"**
This suite asks **"how expensive is Forge itself?"** They are kept apart on
purpose: a scientific benchmark whose numbers move is a correctness event, and a
performance benchmark whose numbers move is a machine event, and mixing them
would make both unreadable.

Nothing here may import from ``benchmarks/hard`` or read a case file. A
performance suite that drifted into re-scoring cases would start reporting a
verdict, and the first time the two disagreed nobody would know which was
authoritative.

WHY NOT ONE AVERAGE
-------------------
A mean hides the distribution that actually matters. This machine is a mobile
i7 on the Balanced power scheme, so clocks move under thermal and turbo control
and a single wall-clock number is not reproducible even against itself. Every
measurement therefore reports P50/P95/P99, min, max and the sample count, and
:func:`stability` reports the observed spread so a reader can tell a real change
from this machine breathing.

COLD vs WARM
------------
``COLD`` is the first meaningful invocation in a fresh process -- what a caller
pays once. ``WARM`` is steady state after imports and first-touch work.
Interpreter import time is never inside a warm number; it is measured
separately, once, by :func:`import_cost`.
"""

from __future__ import annotations

import gc
import json
import os
import pathlib
import platform
import statistics
import subprocess
import sys
import time
import tracemalloc
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Iterable, Sequence

HERE = pathlib.Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent
RESULTS = HERE / "results"

if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))


# ===================================================================== scales

#: The five scale classes. Each subsystem maps them onto its own axis, because
#: "large" for a dependency graph and "large" for a provenance record are not
#: the same number of anything.
SCALES = ("TINY", "SMALL", "MEDIUM", "LARGE", "STRESS")

#: The default axis: counts of whatever the subsystem is measured over. STRESS
#: is deliberately past anything scientifically plausible -- it exists to expose
#: a growth curve, not to represent a real workload, and the report says so.
DEFAULT_SIZES = {
    "TINY": 10,
    "SMALL": 100,
    "MEDIUM": 1_000,
    "LARGE": 10_000,
    "STRESS": 50_000,
}


# ================================================================ measurement


@dataclass(frozen=True)
class Measurement:
    """One benchmark's timing distribution, in milliseconds."""

    name: str
    scale: str
    size: int
    samples: int
    p50_ms: float
    p95_ms: float
    p99_ms: float
    min_ms: float
    max_ms: float
    mean_ms: float
    ops_per_sec: float
    cold_ms: float | None = None
    peak_kib: float | None = None
    note: str = ""

    def row(self) -> str:
        cold = f"{self.cold_ms:9.3f}" if self.cold_ms is not None else "        -"
        peak = f"{self.peak_kib:9.1f}" if self.peak_kib is not None else "        -"
        return (
            f"{self.name:34} {self.scale:7} {self.size:>7} {cold} "
            f"{self.p50_ms:9.4f} {self.p95_ms:9.4f} {self.p99_ms:9.4f} "
            f"{self.ops_per_sec:>12,.0f} {peak}"
        )


HEADER = (
    f"{'benchmark':34} {'scale':7} {'size':>7} {'cold ms':>9} "
    f"{'p50 ms':>9} {'p95 ms':>9} {'p99 ms':>9} {'ops/sec':>12} {'peak KiB':>9}"
)


def _percentile(values: Sequence[float], q: float) -> float:
    """Nearest-rank percentile. Explicit, so the number is reproducible.

    `statistics.quantiles` interpolates and needs n > 1; nearest-rank is what a
    latency percentile normally means and is defined for any non-empty sample.
    """
    ordered = sorted(values)
    if not ordered:
        return float("nan")
    rank = max(1, min(len(ordered), int(round(q * len(ordered) + 0.5))))
    return ordered[rank - 1]


def measure(
    name: str,
    setup: Callable[[], Any],
    operation: Callable[[Any], Any],
    *,
    scale: str = "SMALL",
    size: int = 0,
    samples: int = 200,
    warmup: int = 20,
    inner: int = 1,
    measure_memory: bool = False,
    note: str = "",
) -> Measurement:
    """Time ``operation(subject)`` repeatedly and report its distribution.

    ``setup`` builds the subject ONCE and is never timed: a benchmark that
    rebuilt its input inside the measured block would be reporting the
    constructor it was not trying to measure. Where construction IS the subject,
    the operation builds and the setup returns the ingredients.

    ``inner`` repeats the operation inside one timed block, for operations too
    fast to time individually against the clock's resolution. The reported
    latency is per operation, not per block.

    Garbage collection is disabled across the measured region and collected
    explicitly before it. A collection landing inside one sample is exactly the
    kind of event that produces a P99 nobody can reproduce.
    """
    subject = setup()

    for _ in range(warmup):
        operation(subject)

    peak_kib = None
    if measure_memory:
        gc.collect()
        tracemalloc.start()
        operation(subject)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        peak_kib = peak / 1024.0

    durations: list[float] = []
    gc.collect()
    gc_was_enabled = gc.isenabled()
    gc.disable()
    try:
        for _ in range(samples):
            start = time.perf_counter()
            for _ in range(inner):
                operation(subject)
            durations.append((time.perf_counter() - start) / inner)
    finally:
        if gc_was_enabled:
            gc.enable()

    ms = [d * 1000.0 for d in durations]
    p50 = _percentile(ms, 0.50)
    return Measurement(
        name=name,
        scale=scale,
        size=size,
        samples=len(ms),
        p50_ms=p50,
        p95_ms=_percentile(ms, 0.95),
        # P99 is only reported where the sample supports it. With 200 samples
        # the 99th percentile is the second-largest observation, which is a
        # statement about two data points; below 100 samples it is noise
        # wearing a percentile's name.
        p99_ms=_percentile(ms, 0.99) if len(ms) >= 100 else float("nan"),
        min_ms=min(ms),
        max_ms=max(ms),
        mean_ms=statistics.fmean(ms),
        ops_per_sec=(1000.0 / p50) if p50 > 0 else float("inf"),
        peak_kib=peak_kib,
        note=note,
    )


def cold_measure(module_source: str) -> float:
    """Milliseconds for one operation in a FRESH interpreter, imports included.

    Runs a subprocess, because "cold" cannot be simulated in a process that has
    already imported the thing being measured. This is the number a caller pays
    on first use, and it is reported separately from every warm number for that
    reason.
    """
    completed = subprocess.run(
        [sys.executable, "-c", module_source],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"cold measurement failed:\n{completed.stdout}\n{completed.stderr}"
        )
    return float(completed.stdout.strip().splitlines()[-1])


def stability(operation: Callable[[], Any], *, rounds: int = 7, samples: int = 60) -> dict:
    """How much this machine's own answer moves when nothing changes.

    Runs the same measurement several times and reports the spread of the
    per-round P50. **This is the number that decides whether a timing-based
    regression gate is honest here.** A threshold tighter than the machine's own
    round-to-round variation is a generator of false alarms, and one loose
    enough to survive it may be too loose to catch anything.
    """
    medians = []
    for _ in range(rounds):
        durations = []
        gc.collect()
        for _ in range(samples):
            start = time.perf_counter()
            operation()
            durations.append((time.perf_counter() - start) * 1000.0)
        medians.append(_percentile(durations, 0.50))
    best, worst = min(medians), max(medians)
    return {
        "rounds": rounds,
        "samples_per_round": samples,
        "p50_min_ms": best,
        "p50_max_ms": worst,
        "p50_median_ms": statistics.median(medians),
        "spread_pct": ((worst - best) / best * 100.0) if best > 0 else float("nan"),
        "medians_ms": medians,
    }


# =================================================================== counting


class CallCounter:
    """Counts calls to a function by wrapping it on its own module.

    **The basis of every deterministic guard in this suite.** A call count does
    not move with the weather: "this path parses a unit string 3,276 times per
    case" is reproducible on any machine, in CI, under a debugger, and it is
    the statement that actually characterises a scaling defect. A wall-clock
    number characterises the machine that produced it.
    """

    def __init__(self, module: Any, name: str) -> None:
        self.module = module
        self.name = name
        self.count = 0
        self._original = getattr(module, name)

    def __enter__(self) -> "CallCounter":
        original = self._original

        def counted(*args: Any, **kwargs: Any) -> Any:
            self.count += 1
            return original(*args, **kwargs)

        setattr(self.module, self.name, counted)
        return self

    def __exit__(self, *exc: Any) -> None:
        setattr(self.module, self.name, self._original)


# ================================================================ environment


def machine_record() -> dict:
    """Everything a reader needs to know before believing a number here."""
    record = {
        "python": sys.version.split()[0],
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "logical_cpus": os.cpu_count(),
        "commit": _git("rev-parse", "HEAD"),
        "branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
        "tree_clean": _git("status", "--porcelain") == "",
    }
    return record


def _git(*args: str) -> str:
    try:
        return subprocess.run(
            ["git", *args], capture_output=True, text=True,
            cwd=str(REPO_ROOT), check=True,
        ).stdout.strip()
    except Exception:
        return "unknown"


def write_results(name: str, measurements: Iterable[Measurement], extra: dict | None = None) -> pathlib.Path:
    """Machine-readable output beside the human-readable table."""
    RESULTS.mkdir(parents=True, exist_ok=True)
    payload = {
        "benchmark": name,
        "machine": machine_record(),
        "measurements": [asdict(m) for m in measurements],
    }
    if extra:
        payload["extra"] = extra
    path = RESULTS / f"{name}.json"
    path.write_bytes(
        (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    )
    return path


def report(title: str, measurements: Sequence[Measurement]) -> None:
    print(f"\n{title}")
    print(HEADER)
    print("-" * len(HEADER))
    for measurement in measurements:
        print(measurement.row())


# ==================================================================== fixtures
#
# Deterministic by construction: no RNG, no clock, no case files. The same
# workload is built on every machine and in every run, so two result files are
# comparable without anyone having to check what was measured.


def units_cycle(count: int) -> list[str]:
    """Unit strings a real run actually mixes, cycled to the requested count."""
    vocabulary = [
        "kelvin", "watt", "volt", "ampere", "ohm", "second", "meter",
        "joule/kelvin", "watt/kelvin", "watt/meter/kelvin", "meter**2",
        "meter**3", "1/kelvin", "dimensionless", "watt/meter**2/kelvin",
    ]
    return [vocabulary[i % len(vocabulary)] for i in range(count)]


def quantities(count: int):
    from engcore.scientific.units.quantity import Quantity

    return {
        f"metric_{i:05d}": Quantity(float(i) + 0.5, unit)
        for i, unit in enumerate(units_cycle(count))
    }


def range_conditions(count: int, *, chain: bool = False):
    """``count`` range conditions over dimensionless derived quantities.

    ``chain`` links each condition to the previous one through ``requires``,
    producing a dependency graph of depth ``count`` -- the worst shape for a
    topological sort, and the one that would expose a quadratic ordering.
    """
    from engcore.scientific.models.definition import RangeCondition
    from engcore.scientific.units.quantity import Quantity

    conditions = []
    for i in range(count):
        conditions.append(
            RangeCondition(
                name=f"condition_{i:05d}",
                minimum=Quantity(0.0, "dimensionless"),
                maximum=Quantity(1.0, "dimensionless"),
                requires=(f"condition_{i - 1:05d}",) if chain and i else (),
            )
        )
    return tuple(conditions)


def condition_context(count: int, *, satisfied: bool = True):
    from engcore.scientific.units.quantity import Quantity

    value = 0.5 if satisfied else 5.0
    return {
        f"condition_{i:05d}": Quantity(value, "dimensionless")
        for i in range(count)
    }


def validation_checks(count: int):
    """``count`` passing checks, each carrying a residual, tolerance and evidence."""
    from engcore.scientific.results.validation import (
        ValidationCheck,
        ValidationOutcome,
    )

    return tuple(
        ValidationCheck(
            name=f"check_{i:05d}",
            outcome=ValidationOutcome.PASS,
            detail=f"check {i} compared a residual against a tolerance",
            residual=1e-12,
            tolerance=1e-6,
            evidence=(f"evidence:{i}", f"threshold:{i}=1e-06"),
        )
        for i in range(count)
    )


def provenance_inputs(count: int):
    """A mix of every ScientificValue kind, so encoding cost is representative."""
    from engcore.scientific.ir.values import (
        BooleanValue,
        CategoricalValue,
        IntegerValue,
    )
    from engcore.scientific.units.quantity import Quantity

    inputs: dict[str, Any] = {}
    for i, unit in enumerate(units_cycle(count)):
        kind = i % 4
        name = f"input_{i:05d}"
        if kind == 0:
            inputs[name] = Quantity(float(i) + 0.5, unit)
        elif kind == 1:
            inputs[name] = IntegerValue(i)
        elif kind == 2:
            inputs[name] = BooleanValue(i % 2 == 0)
        else:
            inputs[name] = CategoricalValue(f"category_{i % 7}")
    return inputs


def nested_metadata(breadth: int, depth: int):
    """Breadth and depth as separate axes, because they cost differently."""
    node: Any = {f"leaf_{i}": i for i in range(breadth)}
    for level in range(depth):
        node = {f"level_{level}": node, f"sibling_{level}": [1, 2, 3]}
    return node
