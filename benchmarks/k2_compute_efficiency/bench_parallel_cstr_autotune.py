"""Hardware-adaptive K2 CSTR parallelism characterization.

Engineering telemetry only — NOT scientific evidence and NOT a K2 scored run.

This benchmark answers a different question from ``bench_parallel_cstr.py``.
The baseline benchmark measures a fixed list of process counts.  This one asks
what process count and task chunking are appropriate for *this machine and this
representative CSTR workload* without hard-coding an i7, an EPYC, or any core
count into scientific code.

It deliberately remains a benchmark/autotuner, not a production scheduler.
K2 may consume the measurements later, but scientific meaning never depends on
which hardware configuration wins this timing exercise.

Principles
----------
* Discover hardware capacity at runtime; never branch on CPU/GPU product names.
* Tune against sustained throughput after a process-pool warm-up, because a K2
  inference campaign should reuse a pool rather than pay Windows spawn cost for
  every posterior point.
* Keep BLAS/OpenMP threads at one inside each process so process-level
  parallelism is the only CPU fan-out being measured.
* Compare deterministic solver work and scientific usability against the
  1-worker reference for every measured configuration.  A faster configuration
  that changes nfev/njev/nlu, accepted steps, convergence, or usability is
  rejected as an invalid speedup.
* Choose by measured throughput, not by ``os.cpu_count()`` alone.  Logical CPU
  count is a capacity hint, not a performance prediction.
* Tune batching as part of the workload signature.  The best configuration for
  50 ms solves need not be the best configuration for 5 s solves.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import platform
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import geometric_mean

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

for _name in (
    "OMP_NUM_THREADS",
    "MKL_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
):
    os.environ.setdefault(_name, "1")

from benchmarks.k2_compute_efficiency.bench_parallel_cstr import (  # noqa: E402
    ScalingRow,
    _regime,
    _row,
    _scientific_signature,
    _solve_one,
)


@dataclass(frozen=True)
class TuneMeasurement:
    regime_id: str
    tasks: int
    workers: int
    chunksize: int
    warmup_tasks: int
    wall_s: float
    solves_per_s: float
    speedup_vs_one: float
    parallel_efficiency: float
    succeeded: int
    usable: int
    rhs_evaluations: int
    scipy_nfev: int
    scipy_njev: int
    scipy_nlu: int
    accepted_steps: int


@dataclass(frozen=True)
class Recommendation:
    scope: str
    workers: int
    chunksize: int
    score: float
    reason: str


def _physical_cpu_count() -> int | None:
    """Best-effort physical-core count without making psutil a dependency."""
    try:
        import psutil  # type: ignore

        value = psutil.cpu_count(logical=False)
        return int(value) if value else None
    except Exception:
        return None


def _worker_candidates(logical: int, physical: int | None) -> list[int]:
    """Sparse hardware-derived candidate set, not a hard-coded machine table."""
    candidates = {1}

    power = 2
    while power <= logical:
        candidates.add(power)
        power *= 2

    for fraction in (0.25, 0.5, 0.75, 1.0):
        candidates.add(max(1, int(round(logical * fraction))))

    if physical:
        candidates.add(max(1, physical))
        candidates.add(max(1, physical - 1))

    return sorted(v for v in candidates if 1 <= v <= logical)


def _chunk_candidates(tasks: int, workers: int) -> list[int]:
    """Candidate map chunks derived from work per worker.

    ``chunksize`` reduces scheduler/IPC bookkeeping but overly large chunks can
    starve workers near the tail.  Search a small logarithmic set around the
    amount of work each process would receive rather than pinning a value for a
    particular CPU.
    """
    per_worker = max(1, math.ceil(tasks / max(workers, 1)))
    candidates = {1, 2, 4, 8, 16}
    for divisor in (8, 4, 2, 1):
        candidates.add(max(1, math.ceil(per_worker / divisor)))
    return sorted(v for v in candidates if 1 <= v <= tasks)


def _aggregate(rows, field: str) -> int:
    return sum(int(getattr(row, field)) for row in rows)


def _measure_with_reused_pool(
    regime_id: str,
    *,
    tasks: int,
    workers: int,
    chunksize: int,
    reference_signature: tuple,
    reference_wall: float,
):
    payloads = [(regime_id, i) for i in range(tasks)]
    warmup_tasks = min(tasks, max(4, workers * 2))
    warmup_payloads = [
        (regime_id, tasks + 1_000_000 + i) for i in range(warmup_tasks)
    ]

    if workers == 1:
        for payload in warmup_payloads:
            _solve_one(payload)
        started = time.perf_counter()
        rows = [_solve_one(payload) for payload in payloads]
        wall = time.perf_counter() - started
    else:
        # One pool per configuration, reused for warm-up and measurement.  This
        # approximates a real K2 evaluator much better than recreating workers
        # for each small inference batch while still measuring each candidate
        # configuration independently.
        with ProcessPoolExecutor(max_workers=workers) as executor:
            list(executor.map(_solve_one, warmup_payloads, chunksize=chunksize))
            started = time.perf_counter()
            rows = list(executor.map(_solve_one, payloads, chunksize=chunksize))
            wall = time.perf_counter() - started

    signature = _scientific_signature(rows)
    if signature != reference_signature:
        raise RuntimeError(
            f"scientific/work-count mismatch for {regime_id}: workers={workers} "
            f"chunksize={chunksize}; timing result rejected"
        )

    row: ScalingRow = _row(
        regime_id,
        tasks,
        workers,
        wall,
        rows,
        reference_wall,
    )
    return TuneMeasurement(
        regime_id=regime_id,
        tasks=tasks,
        workers=workers,
        chunksize=chunksize,
        warmup_tasks=warmup_tasks,
        wall_s=row.wall_s,
        solves_per_s=row.solves_per_s,
        speedup_vs_one=row.speedup_vs_one,
        parallel_efficiency=row.parallel_efficiency,
        succeeded=row.succeeded,
        usable=row.usable,
        rhs_evaluations=row.rhs_evaluations,
        scipy_nfev=row.scipy_nfev,
        scipy_njev=row.scipy_njev,
        scipy_nlu=row.scipy_nlu,
        accepted_steps=row.accepted_steps,
    )


def _reference(regime_id: str, tasks: int):
    # Warm the Python/SciPy path before timing the serial reference too.
    for i in range(min(tasks, 4)):
        _solve_one((regime_id, tasks + 2_000_000 + i))

    payloads = [(regime_id, i) for i in range(tasks)]
    started = time.perf_counter()
    rows = [_solve_one(payload) for payload in payloads]
    wall = time.perf_counter() - started
    return wall, rows, _scientific_signature(rows)


def _top_worker_counts(
    measurements: list[TuneMeasurement], regimes: list[str], limit: int = 3
) -> list[int]:
    """Rank workers by geometric-mean normalized throughput across regimes."""
    by_worker: dict[int, list[float]] = {}
    for regime_id in regimes:
        subset = [m for m in measurements if m.regime_id == regime_id]
        baseline = next(m.solves_per_s for m in subset if m.workers == 1)
        for item in subset:
            by_worker.setdefault(item.workers, []).append(
                item.solves_per_s / baseline if baseline else 0.0
            )

    scored = []
    for workers, ratios in by_worker.items():
        if len(ratios) != len(regimes) or any(v <= 0.0 for v in ratios):
            continue
        scored.append((geometric_mean(ratios), workers))
    scored.sort(reverse=True)
    return [workers for _score, workers in scored[:limit]]


def _recommend(
    measurements: list[TuneMeasurement], regimes: list[str]
) -> list[Recommendation]:
    recommendations: list[Recommendation] = []

    for regime_id in regimes:
        subset = [m for m in measurements if m.regime_id == regime_id]
        best = max(subset, key=lambda m: m.solves_per_s)
        recommendations.append(
            Recommendation(
                scope=regime_id,
                workers=best.workers,
                chunksize=best.chunksize,
                score=best.solves_per_s,
                reason="maximum measured sustained solves/second",
            )
        )

    # Balanced recommendation: geometric mean of each configuration's
    # throughput relative to that regime's serial reference.  This avoids an
    # easy regime with higher absolute solve/s dominating a mixed workload.
    configurations = sorted({(m.workers, m.chunksize) for m in measurements})
    balanced: list[tuple[float, int, int]] = []
    for workers, chunksize in configurations:
        ratios: list[float] = []
        complete = True
        for regime_id in regimes:
            subset = [
                m
                for m in measurements
                if m.regime_id == regime_id
                and m.workers == workers
                and m.chunksize == chunksize
            ]
            serial = next(
                m for m in measurements
                if m.regime_id == regime_id and m.workers == 1
            )
            if not subset:
                complete = False
                break
            ratios.append(subset[0].solves_per_s / serial.solves_per_s)
        if complete and ratios and all(v > 0.0 for v in ratios):
            balanced.append((geometric_mean(ratios), workers, chunksize))

    if balanced:
        score, workers, chunksize = max(balanced)
        recommendations.append(
            Recommendation(
                scope="balanced",
                workers=workers,
                chunksize=chunksize,
                score=score,
                reason=(
                    "maximum geometric-mean speedup across representative "
                    "regimes; workload-specific recommendations remain preferred"
                ),
            )
        )

    return recommendations


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--regimes", default="R1,R2")
    parser.add_argument(
        "--tasks",
        type=int,
        default=128,
        help="Measured solves per regime/configuration; use enough work to amortize IPC.",
    )
    parser.add_argument(
        "--workers",
        default="auto",
        help="'auto' or comma-separated worker counts. Auto derives candidates from this CPU.",
    )
    parser.add_argument(
        "--top-workers",
        type=int,
        default=3,
        help="How many best worker counts advance to chunk-size tuning.",
    )
    parser.add_argument(
        "--output",
        default="benchmarks/k2_compute_efficiency/parallel_cstr_autotune_results.json",
    )
    args = parser.parse_args()

    if args.tasks < 8:
        raise ValueError("--tasks must be >= 8 for sustained-throughput tuning")

    regimes = [item.strip() for item in args.regimes.split(",") if item.strip()]
    for regime_id in regimes:
        _regime(regime_id)

    logical = os.cpu_count() or 1
    physical = _physical_cpu_count()
    if args.workers.strip().lower() == "auto":
        workers = _worker_candidates(logical, physical)
    else:
        workers = sorted(
            {
                int(token.strip())
                for token in args.workers.split(",")
                if token.strip()
            }
        )
        workers = [v for v in workers if 1 <= v <= logical]
        if 1 not in workers:
            workers.insert(0, 1)

    print("=" * 104)
    print("K2 COMPUTE EFFICIENCY — HARDWARE-ADAPTIVE CSTR AUTOTUNE")
    print("Engineering telemetry only; recommendations are machine/workload specific")
    print(f"Logical CPUs : {logical}")
    print(f"Physical CPUs: {physical if physical is not None else 'unknown'}")
    print(f"Tasks        : {args.tasks}")
    print(f"Regimes      : {regimes}")
    print(f"Worker scan  : {workers}")
    print("=" * 104)

    references = {}
    measurements: list[TuneMeasurement] = []

    # Stage 1: worker-count scan with minimal scheduler batching.
    for regime_id in regimes:
        wall, rows, signature = _reference(regime_id, args.tasks)
        references[regime_id] = (wall, signature)
        serial_row: ScalingRow = _row(
            regime_id, args.tasks, 1, wall, rows, wall
        )
        measurements.append(
            TuneMeasurement(
                regime_id=regime_id,
                tasks=args.tasks,
                workers=1,
                chunksize=1,
                warmup_tasks=min(args.tasks, 4),
                wall_s=serial_row.wall_s,
                solves_per_s=serial_row.solves_per_s,
                speedup_vs_one=1.0,
                parallel_efficiency=1.0,
                succeeded=serial_row.succeeded,
                usable=serial_row.usable,
                rhs_evaluations=serial_row.rhs_evaluations,
                scipy_nfev=serial_row.scipy_nfev,
                scipy_njev=serial_row.scipy_njev,
                scipy_nlu=serial_row.scipy_nlu,
                accepted_steps=serial_row.accepted_steps,
            )
        )

        for worker_count in workers:
            if worker_count == 1:
                continue
            measurements.append(
                _measure_with_reused_pool(
                    regime_id,
                    tasks=args.tasks,
                    workers=worker_count,
                    chunksize=1,
                    reference_signature=signature,
                    reference_wall=wall,
                )
            )

    advancing = _top_worker_counts(
        measurements, regimes, limit=max(1, args.top_workers)
    )

    # Stage 2: scheduler chunk tuning only for promising worker counts.  Avoid a
    # huge benchmark matrix: evidence pulls the search outward, not vice versa.
    for worker_count in advancing:
        if worker_count == 1:
            continue
        for regime_id in regimes:
            reference_wall, signature = references[regime_id]
            existing = {
                m.chunksize
                for m in measurements
                if m.regime_id == regime_id and m.workers == worker_count
            }
            for chunksize in _chunk_candidates(args.tasks, worker_count):
                if chunksize in existing:
                    continue
                measurements.append(
                    _measure_with_reused_pool(
                        regime_id,
                        tasks=args.tasks,
                        workers=worker_count,
                        chunksize=chunksize,
                        reference_signature=signature,
                        reference_wall=reference_wall,
                    )
                )

    measurements.sort(key=lambda m: (m.regime_id, m.workers, m.chunksize))
    recommendations = _recommend(measurements, regimes)

    print(
        f"{'Regime':>7} {'Workers':>7} {'Chunk':>6} {'Wall(s)':>10} "
        f"{'solve/s':>11} {'speedup':>9} {'eff%':>8} {'RHS':>12}"
    )
    for row in measurements:
        print(
            f"{row.regime_id:>7} {row.workers:7d} {row.chunksize:6d} "
            f"{row.wall_s:10.3f} {row.solves_per_s:11.2f} "
            f"{row.speedup_vs_one:9.2f} "
            f"{100.0 * row.parallel_efficiency:8.1f} "
            f"{row.rhs_evaluations:12,d}"
        )

    print("\nRecommendations")
    for rec in recommendations:
        unit = "solve/s" if rec.scope != "balanced" else "x geo-mean"
        print(
            f"  {rec.scope:>10}: workers={rec.workers:<3d} "
            f"chunksize={rec.chunksize:<4d} score={rec.score:.3f} {unit}"
        )

    payload = {
        "kind": "k2_parallel_cstr_hardware_adaptive_autotune",
        "scientific_evidence": False,
        "machine": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "logical_cpu_count": logical,
            "physical_cpu_count": physical,
            "thread_environment": {
                name: os.environ.get(name)
                for name in (
                    "OMP_NUM_THREADS",
                    "MKL_NUM_THREADS",
                    "OPENBLAS_NUM_THREADS",
                    "NUMEXPR_NUM_THREADS",
                )
            },
        },
        "workload_signature": {
            "domain": "kinetics.cstr",
            "regimes": regimes,
            "tasks_per_measurement": args.tasks,
            "solver_semantics": "existing K1 public solve_reactor lifecycle",
        },
        "search": {
            "worker_candidates": workers,
            "chunk_tuning_worker_candidates": advancing,
            "selection_metric": "sustained solves_per_s with scientific-work invariance",
        },
        "measurements": [asdict(row) for row in measurements],
        "recommendations": [asdict(rec) for rec in recommendations],
        "policy_boundary": {
            "not_a_scheduler": True,
            "hardware_names_used_for_selection": False,
            "scientific_semantics_depend_on_recommendation": False,
            "note": (
                "A future K2 evaluator may reuse a measured recommendation for a matching "
                "workload/environment signature, but must retain deterministic scientific "
                "parity checks and a safe serial fallback."
            ),
        },
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(f"\nSaved: {output}")


if __name__ == "__main__":
    main()
