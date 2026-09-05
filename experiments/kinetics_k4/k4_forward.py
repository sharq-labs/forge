"""K4 forward-table execution for the constant-rate CSTR competitor.

Scientific interpretation stays in ``ConstantRateCSTRInferenceForwardAdapter``.
This module owns only K4's frozen one-dimensional grid, condition selection,
process-level execution policy and compaction into ``AdmittedForwardTable``.

Training (C1/C2/C3) and prediction (H1/H2) use the same model-specific adapter;
only the declared condition set changes.
"""

from __future__ import annotations

import os
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from itertools import repeat
from typing import Callable, Sequence

for _name in (
    "OMP_NUM_THREADS",
    "MKL_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
):
    os.environ.setdefault(_name, "1")

import numpy as np

from experiments.kinetics_k2.k2_config import CONDITION_BY_ID, OBSERVABLE_NAMES
from experiments.kinetics_k2.k2_forward import ForwardBuildStats, resolve_worker_count
from experiments.kinetics_k3.k3_config import HOLDOUT_BY_ID
from src.engcore.domains.kinetics.cstr.alternative_inference import (
    ConstantRateCSTRInferenceForwardAdapter,
)
from src.engcore.inference import (
    AdmittedForwardRow,
    AdmittedForwardTable,
    InferenceAdmissibilityError,
    ObservationSet,
)

from .k4_config import chemistry_from_log_k_const

CONSTANT_RATE_PARAMETER_NAMES = ("log_k_const",)


@dataclass(frozen=True)
class ConstantRateForwardTask:
    index: int
    log_k_const: float


@dataclass(frozen=True)
class ConstantRateForwardTaskResult:
    row: AdmittedForwardRow
    condition_attempts: int
    condition_admitted: int
    condition_rejected: int


@dataclass(frozen=True)
class ConstantRateForwardBuildResult:
    table: AdmittedForwardTable
    stats: ForwardBuildStats


def _resolve_condition(condition_id: str):
    if condition_id in CONDITION_BY_ID:
        return CONDITION_BY_ID[condition_id]
    if condition_id in HOLDOUT_BY_ID:
        return HOLDOUT_BY_ID[condition_id]
    raise ValueError(f"unknown K4 condition id {condition_id!r}")


def _evaluate_task(
    task: ConstantRateForwardTask,
    observations: ObservationSet,
    condition_ids: tuple[str, ...],
    source_commit: str | None,
) -> ConstantRateForwardTaskResult:
    chemistry = chemistry_from_log_k_const(task.log_k_const)
    adapter = ConstantRateCSTRInferenceForwardAdapter()
    predictions: dict[str, object] = {}
    rejections: list[str] = []
    admitted = 0

    for condition_id in condition_ids:
        condition = _resolve_condition(condition_id)
        try:
            predictions[condition_id] = adapter.evaluate(
                condition.build(chemistry),
                observable_names=OBSERVABLE_NAMES,
                run_id_prefix=f"k4-m2-grid-{task.index}-{condition_id}",
                source_commit=source_commit,
                environment={
                    "purpose": "k4-model-competition-forward",
                    "model_family": "constant_rate_first_order",
                },
            )
            admitted += 1
        except InferenceAdmissibilityError as exc:
            rejections.append(f"{condition_id}: {exc}")

    attempts = len(condition_ids)
    rejected = attempts - admitted
    coordinates = (float(task.log_k_const),)
    if rejections:
        row = AdmittedForwardRow.rejected(
            coordinates,
            observations,
            "; ".join(rejections),
        )
    else:
        row = AdmittedForwardRow.from_predictions(
            coordinates,
            observations,
            predictions,
        )
    return ConstantRateForwardTaskResult(
        row=row,
        condition_attempts=attempts,
        condition_admitted=admitted,
        condition_rejected=rejected,
    )


def build_constant_rate_forward_table_with_stats(
    points: np.ndarray,
    observations: ObservationSet,
    *,
    condition_ids: Sequence[str],
    workers: str | int = "auto",
    source_commit: str | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
) -> ConstantRateForwardBuildResult:
    points = np.asarray(points, dtype=np.float64)
    if points.ndim != 2 or points.shape[1] != 1:
        raise ValueError("K4 constant-rate points must have shape (N, 1)")
    condition_ids = tuple(str(value) for value in condition_ids)
    if not condition_ids:
        raise ValueError("K4 constant-rate forward table requires conditions")
    for condition_id in condition_ids:
        _resolve_condition(condition_id)

    tasks = [
        ConstantRateForwardTask(i, float(row[0]))
        for i, row in enumerate(points)
    ]
    n_workers = resolve_worker_count(workers, len(tasks))
    results: list[ConstantRateForwardTaskResult] = []

    if n_workers == 1:
        iterator = (
            _evaluate_task(task, observations, condition_ids, source_commit)
            for task in tasks
        )
        for completed, result in enumerate(iterator, 1):
            results.append(result)
            if progress_callback is not None:
                progress_callback(completed, len(tasks))
    else:
        with ProcessPoolExecutor(max_workers=n_workers) as executor:
            iterator = executor.map(
                _evaluate_task,
                tasks,
                repeat(observations),
                repeat(condition_ids),
                repeat(source_commit),
                chunksize=1,
            )
            for completed, result in enumerate(iterator, 1):
                results.append(result)
                if progress_callback is not None:
                    progress_callback(completed, len(tasks))

    table = AdmittedForwardTable.from_rows(
        CONSTANT_RATE_PARAMETER_NAMES,
        observations,
        [item.row for item in results],
    )
    stats = ForwardBuildStats(
        parameter_points=len(results),
        condition_attempts=sum(item.condition_attempts for item in results),
        condition_admitted=sum(item.condition_admitted for item in results),
        condition_rejected=sum(item.condition_rejected for item in results),
        point_admitted=sum(1 for item in results if item.row.admissible),
        point_rejected=sum(1 for item in results if not item.row.admissible),
        workers=n_workers,
    )
    return ConstantRateForwardBuildResult(table=table, stats=stats)
