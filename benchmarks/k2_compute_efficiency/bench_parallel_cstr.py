"""K2 compute-efficiency baseline: independent CSTR solve scaling.

Engineering telemetry only — NOT scientific evidence and NOT a K2 scored run.

Purpose
-------
Measure whether independent, scientifically identical CSTR forward evaluations
scale usefully across CPU processes before K2 builds inference abstractions on
top of them. The benchmark deliberately uses the existing K1 frozen regimes and
the existing public ``solve_reactor`` lifecycle; it changes no equations,
tolerances, validation rules, solver identities, or scientific semantics.

The primary signals are deterministic work counts plus throughput:

- solve count
- RHS evaluations (domain counter)
- SciPy nfev / njev / nlu
- successful + usable result counts
- wall-clock throughput
- parallel efficiency relative to the 1-worker measurement

Wall-clock is machine-specific engineering telemetry. The work counters are
recorded and asserted invariant across worker settings so a faster run cannot
hide extra numerical work or a changed scientific outcome.

Important threading rule
------------------------
Each worker performs tiny 2-state stiff solves. Process-level parallelism is the
intended axis; nested BLAS/OpenMP fan-out would oversubscribe a laptop CPU. The
thread limits below are therefore installed before NumPy/SciPy are imported in
this process (and again when spawned workers import this module).
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

# Allow direct execution via
#   py .\benchmarks\k2_compute_efficiency\bench_parallel_cstr.py
# by adding the repository root to sys.path before importing project packages.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Must precede NumPy/SciPy imports in this module and in Windows spawn workers.
for _name in (
    "OMP_NUM_THREADS",
    "MKL_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
):
    os.environ.setdefault(_name, "1")

from experiments.kinetics_k1.k1_config import REGIMES  # noqa: E402
from src.engcore.domains.kinetics.cstr import solve_reactor  # noqa: E402
from src.engcore.scientific.solvers.protocol import ConvergenceState  # noqa: E402


@dataclass(frozen=True)
class SolveTelemetry:
    regime_id: str
    task_index: int
    succeeded: bool
    usable: bool
    convergence: str
    rhs_evaluations: int
    scipy_nfev: int
    scipy_njev: int
    scipy_nlu: int
    accepted_steps: int
    solver_wall_s: float


@dataclass(frozen=True)
class ScalingRow:
    regime_id: str
    tasks: int
    workers: int
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
    solver_wall_s_sum: float


def _regime(regime_id: str):
    for spec in REGIMES:
        if spec.regime_id == regime_id:
            return spec
    available = ", ".join(spec.regime_id for spec in REGIMES)
    raise ValueError(f"unknown regime {regime_id!r}; available: {available}")


def _solve_one(payload: tuple[str, int]) -> SolveTelemetry:
    """One top-level picklable worker operation."""

    regime_id, task_index = payload
    run = _regime(regime_id).build()
    result = solve_reactor(
        run,
        run_id=f"k2-perf-{regime_id.lower()}-{task_index:06d}",
        software_version="k2-compute-efficiency-benchmark/0.1.1",
        source_commit=None,
        core_baseline_commit=None,
        environment={
            "purpose": "engineering-performance-telemetry-only",
            "workers_thread_limit": "1",
        },
    )

    numerics = dict(result.metadata.get("numerics", {}))
    convergence = getattr(result.convergence, "value", str(result.convergence))
    return SolveTelemetry(
        regime_id=regime_id,
        task_index=task_index,
        succeeded=(result.convergence is ConvergenceState.CONVERGED),
        usable=bool(result.is_usable),
        convergence=str(convergence),
        rhs_evaluations=int(numerics.get("rhs_evaluations", 0)),
        scipy_nfev=int(numerics.get("scipy_nfev", 0)),
        scipy_njev=int(numerics.get("scipy_njev", 0)),
        scipy_nlu=int(numerics.get("scipy_nlu", 0)),
        accepted_steps=int(numerics.get("accepted_steps", 0)),
        solver_wall_s=float(result.metadata.get("wall_seconds_telemetry", 0.0)),
    )


def _run_batch(regime_id: str, tasks: int, workers: int) -> tuple[float, list[SolveTelemetry]]:
    payloads = [(regime_id, i) for i in range(tasks)]
    started = time.perf_counter()

    if workers == 1:
        rows = [_solve_one(payload) for payload in payloads]
    else:
        # map() preserves input order and has lower bookkeeping overhead than
        # one future object per result. chunksize=1 is intentional for the
        # first characterization: K2 needs the true per-solve granularity before
        # any task batching policy is introduced.
        with ProcessPoolExecutor(max_workers=workers) as executor:
            rows = list(executor.map(_solve_one, payloads, chunksize=1))

    return time.perf_counter() - started, rows


def _sum(rows: Iterable[SolveTelemetry], field: str) -> int:
    return sum(int(getattr(row, field)) for row in rows)


def _scientific_signature(rows: list[SolveTelemetry]) -> tuple:
    return tuple(
        (
            row.task_index,
            row.succeeded,
            row.usable,
            row.convergence,
            row.rhs_evaluations,
            row.scipy_nfev,
            row.scipy_njev,
            row.scipy_nlu,
            row.accepted_steps,
        )
        for row in rows
    )


def _row(regime_id: str, tasks: int, workers: int, wall: float, rows: list[SolveTelemetry], baseline_wall: float) -> ScalingRow:
    speedup = baseline_wall / wall if wall > 0.0 else 0.0
    return ScalingRow(
        regime_id=regime_id,
        tasks=tasks,
        workers=workers,
        wall_s=wall,
        solves_per_s=(tasks / wall if wall > 0.0 else 0.0),
        speedup_vs_one=speedup,
        parallel_efficiency=(speedup / workers if workers > 0 else 0.0),
        succeeded=sum(row.succeeded for row in rows),
        usable=sum(row.usable for row in rows),
        rhs_evaluations=_sum(rows, "rhs_evaluations"),
        scipy_nfev=_sum(rows, "scipy_nfev"),
        scipy_njev=_sum(rows, "scipy_njev"),
        scipy_nlu=_sum(rows, "scipy_nlu"),
        accepted_steps=_sum(rows, "accepted_steps"),
        solver_wall_s_sum=sum(row.solver_wall_s for row in rows),
    )


def _parse_workers(raw: str) -> list[int]:
    values: list[int] = []
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        value = int(token)
        if value < 1:
            raise ValueError("worker counts must be >= 1")
        if value not in values:
            values.append(value)
    if 1 not in values:
        values.insert(0, 1)
    return values


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--regimes",
        default="R1,R2",
        help="Comma-separated existing K1 regimes. R1=easy, R2=stiff.",
    )
    parser.add_argument(
        "--tasks",
        type=int,
        default=64,
        help="Independent solves per regime and worker setting.",
    )
    parser.add_argument(
        "--workers",
        default="1,2,4,8",
        help="Comma-separated process counts; 1 is always measured first.",
    )
    parser.add_argument(
        "--output",
        default="benchmarks/k2_compute_efficiency/parallel_cstr_results.json",
    )
    args = parser.parse_args()

    if args.tasks < 1:
        raise ValueError("--tasks must be >= 1")

    regimes = [item.strip() for item in args.regimes.split(",") if item.strip()]
    workers = _parse_workers(args.workers)
    cpu_count = os.cpu_count() or 1
    workers = [value for value in workers if value <= cpu_count]

    all_rows: list[ScalingRow] = []

    print("=" * 92)
    print("K2 COMPUTE EFFICIENCY — PARALLEL CSTR BASELINE")
    print("Engineering telemetry only; not scientific evidence")
    print(f"CPU count : {cpu_count}")
    print(f"Tasks     : {args.tasks} / regime / worker setting")
    print(f"Workers   : {workers}")
    print("=" * 92)

    for regime_id in regimes:
        _regime(regime_id)  # fail before measuring anything
        baseline_wall, baseline_rows = _run_batch(regime_id, args.tasks, 1)
        baseline_signature = _scientific_signature(baseline_rows)
        all_rows.append(
            _row(regime_id, args.tasks, 1, baseline_wall, baseline_rows, baseline_wall)
        )

        for worker_count in workers:
            if worker_count == 1:
                continue
            wall, rows = _run_batch(regime_id, args.tasks, worker_count)
            if _scientific_signature(rows) != baseline_signature:
                raise RuntimeError(
                    f"scientific/work-count mismatch for {regime_id} at "
                    f"{worker_count} workers; parallel execution changed more "
                    f"than wall time, so this speedup is invalid"
                )
            all_rows.append(
                _row(regime_id, args.tasks, worker_count, wall, rows, baseline_wall)
            )

    print(
        f"{'Regime':>7} {'Workers':>7} {'Wall(s)':>10} {'solve/s':>11} "
        f"{'speedup':>9} {'eff%':>8} {'RHS':>12} {'usable':>8}"
    )
    for row in all_rows:
        print(
            f"{row.regime_id:>7} {row.workers:7d} {row.wall_s:10.3f} "
            f"{row.solves_per_s:11.2f} {row.speedup_vs_one:9.2f} "
            f"{100.0 * row.parallel_efficiency:8.1f} "
            f"{row.rhs_evaluations:12,d} {row.usable:8d}"
        )

    payload = {
        "kind": "k2_parallel_cstr_engineering_telemetry",
        "scientific_evidence": False,
        "machine": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "cpu_count": cpu_count,
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
        "config": {
            "regimes": regimes,
            "tasks": args.tasks,
            "workers": workers,
        },
        "rows": [asdict(row) for row in all_rows],
        "interpretation": {
            "multiprocessing_kill_criterion": (
                "do not make process parallelism a K2 default if 4 workers "
                "deliver <1.5x speedup on representative K2 solve granularity, "
                "or if 8-worker parallel efficiency is <0.40"
            ),
            "scientific_guard": (
                "for one regime, deterministic work counts and usable/success "
                "counts must remain identical across worker settings; only wall "
                "time/order of process execution may differ"
            ),
        },
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(f"\nSaved: {output}")


if __name__ == "__main__":
    main()
