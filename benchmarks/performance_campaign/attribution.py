"""Where does the time go: scientific work, or the framework around it?

The sprint's question is a ratio, and a ratio needs every millisecond assigned
to exactly one bucket. This runs a workload under ``cProfile`` and attributes
**tottime** — time in the function itself, excluding its callees — to a
category chosen by where the function's code lives.

``tottime`` rather than ``cumtime``, deliberately. Cumulative time
double-counts: a solve's cumulative time contains its unit conversions, its
freezes and its validation, so summing categories by ``cumtime`` produces a
total several times the wall clock and a percentage that means nothing. Total
time over all functions sums to the run, so the percentages are shares of one
thing.

The categories are deliberately coarse and are matched on the *defining
module's path*, so a function is attributed to the layer that owns it rather
than to whichever layer called it. A unit conversion inside a solver is unit
work: that is the point of asking.
"""

from __future__ import annotations

import cProfile
import pstats
import sys
from dataclasses import dataclass
from typing import Any, Callable, Iterable

#: ``(category, marker)`` in priority order — the first marker found in a
#: function's filename wins, so narrower paths must precede wider ones.
CATEGORIES: tuple[tuple[str, str], ...] = (
    # --- the framework's own layers -------------------------------------
    ("units", "engcore\\scientific\\units"),
    ("units", "engcore/scientific/units"),
    ("freeze", "results\\immutable"),
    ("freeze", "results/immutable"),
    ("provenance", "results\\provenance"),
    ("provenance", "results/provenance"),
    ("validation", "results\\validation"),
    ("validation", "results/validation"),
    ("thresholds", "results\\thresholds"),
    ("thresholds", "results/thresholds"),
    ("serialization", "scientific\\serialization"),
    ("serialization", "scientific/serialization"),
    ("data_reference", "results\\data_reference"),
    ("data_reference", "results/data_reference"),
    ("result_record", "results\\result"),
    ("result_record", "results/result"),
    ("fields", "engcore\\scientific\\fields"),
    ("fields", "engcore/scientific/fields"),
    ("runtime_data", "engcore\\data"),
    ("runtime_data", "engcore/data"),
    ("evidence", "engcore\\adequacy"),
    ("evidence", "engcore/adequacy"),
    ("inference", "engcore\\inference"),
    ("inference", "engcore/inference"),
    ("registry", "solvers\\registry"),
    ("registry", "solvers/registry"),
    ("solver_protocol", "solvers\\protocol"),
    ("solver_protocol", "solvers/protocol"),
    ("consensus", "scientific\\consensus"),
    ("consensus", "scientific/consensus"),
    ("models", "engcore\\scientific\\models"),
    ("models", "engcore/scientific/models"),
    ("ir", "engcore\\scientific\\ir"),
    ("ir", "engcore/scientific/ir"),
    ("core_other", "engcore\\scientific"),
    ("core_other", "engcore/scientific"),
    ("sweep", "engcore\\execution"),
    ("sweep", "engcore/execution"),
    ("domain", "engcore\\domains"),
    ("domain", "engcore/domains"),
    ("mcp", "engcore\\mcp"),
    ("mcp", "engcore/mcp"),
    ("engcore_other", "engcore"),
    # --- numerical work, split because the split is the finding -----------
    #
    # `scipy.sparse._lil.__setitem__` is a Python call per matrix element. It
    # lives in scipy and it is not linear algebra: it is the cost of the data
    # structure an assembly loop chose. Counting it as "numerical work" would
    # answer this sprint's question wrongly, so it gets its own bucket and the
    # factorisation gets another.
    ("factorization", r"scipy\sparse\linalg"),
    ("factorization", "scipy/sparse/linalg"),
    ("sparse_structure", r"scipy\sparse"),
    ("sparse_structure", "scipy/sparse"),
    ("numerics", "scipy"),
    ("numerics", "numpy"),
    ("units_backend", "pint"),
    # --- the interpreter itself -------------------------------------------
    ("hashing", "hashlib"),
    ("json", "json"),
    ("stdlib", "lib\\"),
    ("stdlib", "lib/"),
)

#: Categories that are scientific computation rather than framework.
NUMERICAL = frozenset({"numerics", "factorization"})

#: Neither framework nor linear algebra: the per-element cost of the sparse
#: container an assembly loop writes into. Reported on its own line because
#: attributing it to either side would misstate the answer.
STRUCTURE = frozenset({"sparse_structure"})

#: Categories that are the framework doing trust work rather than arithmetic.
FRAMEWORK = frozenset({
    "units", "freeze", "provenance", "validation", "thresholds",
    "serialization", "data_reference", "result_record", "fields",
    "runtime_data", "evidence", "inference", "registry", "solver_protocol",
    "consensus", "models", "ir", "core_other", "sweep", "domain", "mcp",
    "engcore_other", "units_backend", "hashing", "json",
})


def classify(filename: str, funcname: str) -> str:
    """The category owning a profiled function."""
    if filename in ("~", "", None):
        return "builtin"
    lowered = filename.lower()
    for category, marker in CATEGORIES:
        if marker.lower() in lowered:
            return category
    return "other"


@dataclass(frozen=True)
class Row:
    category: str
    calls: int
    seconds: float

    @property
    def milliseconds(self) -> float:
        return self.seconds * 1e3


@dataclass(frozen=True)
class Attribution:
    """One workload's time, split by who spent it."""

    name: str
    total_seconds: float
    rows: tuple[Row, ...]
    hot: tuple[tuple[str, int, float], ...]

    @property
    def numerical_seconds(self) -> float:
        return sum(r.seconds for r in self.rows if r.category in NUMERICAL)

    @property
    def framework_seconds(self) -> float:
        return sum(r.seconds for r in self.rows if r.category in FRAMEWORK)

    @property
    def framework_share(self) -> float:
        total = self.numerical_seconds + self.framework_seconds
        return self.framework_seconds / total if total else 0.0

    def table(self, limit: int = 18) -> str:
        lines = [f"{'category':<18}{'calls':>12}{'ms':>12}{'% total':>10}"]
        lines.append("-" * 52)
        for row in self.rows[:limit]:
            share = 100.0 * row.seconds / self.total_seconds if self.total_seconds else 0
            lines.append(
                f"{row.category:<18}{row.calls:>12,}{row.milliseconds:>12.2f}{share:>9.1f}%"
            )
        lines.append("-" * 52)
        lines.append(
            f"{'TOTAL':<18}{sum(r.calls for r in self.rows):>12,}"
            f"{self.total_seconds * 1e3:>12.2f}{100.0:>9.1f}%"
        )
        lines.append("")
        lines.append(
            f"framework {self.framework_share * 100:5.1f}%   "
            f"numerical {(1 - self.framework_share) * 100:5.1f}%   "
            f"(of framework+numerical, excluding interpreter builtins)"
        )
        return "\n".join(lines)

    def hot_table(self, limit: int = 15) -> str:
        lines = [f"{'function':<62}{'calls':>10}{'ms':>10}"]
        for name, calls, seconds in self.hot[:limit]:
            lines.append(f"{name[:60]:<62}{calls:>10,}{seconds * 1e3:>10.2f}")
        return "\n".join(lines)


def attribute(name: str, operation: Callable[[], Any], *, repeat: int = 1) -> Attribution:
    """Profile ``operation`` and split its self-time by category."""
    profiler = cProfile.Profile()
    profiler.enable()
    for _ in range(repeat):
        operation()
    profiler.disable()

    stats = pstats.Stats(profiler)
    totals: dict[str, list[float]] = {}
    hot: list[tuple[str, int, float]] = []
    grand = 0.0
    for (filename, line, funcname), entry in stats.stats.items():  # noqa: SLF001
        calls, _, tottime, _cumtime, _callers = entry
        grand += tottime
        category = classify(str(filename), funcname)
        bucket = totals.setdefault(category, [0.0, 0.0])
        bucket[0] += calls
        bucket[1] += tottime
        short = f"{pathlib_name(filename)}:{funcname}"
        hot.append((short, calls, tottime))

    rows = tuple(
        sorted(
            (Row(c, int(v[0]), v[1]) for c, v in totals.items()),
            key=lambda r: r.seconds,
            reverse=True,
        )
    )
    hot.sort(key=lambda item: item[2], reverse=True)
    return Attribution(name=name, total_seconds=grand, rows=rows, hot=tuple(hot))


def pathlib_name(filename: Any) -> str:
    text = str(filename)
    if text in ("~", ""):
        return "<builtin>"
    return text.replace("\\", "/").rsplit("/", 1)[-1]


def report(attribution: Attribution, *, hot: bool = True) -> None:
    print(f"\n===== {attribution.name} =====")
    print(attribution.table())
    if hot:
        print("\nhottest functions by self-time:")
        print(attribution.hot_table())


def counted(operations: Iterable[tuple[str, Callable[[], Any]]], repeat: int = 1):
    """Attribute several workloads and return them in order."""
    return [attribute(name, op, repeat=repeat) for name, op in operations]
