"""K3 holdout forward bridge.

Every predictive support value crosses the existing K1.5 CSTR inference
admissibility boundary before it is compacted for UQ.  Execution policy is
separate from scientific meaning, matching K2.
"""

from __future__ import annotations

import os
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from itertools import repeat
from typing import Callable, Mapping, Sequence

for _name in (
    "OMP_NUM_THREADS",
    "MKL_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
):
    os.environ.setdefault(_name, "1")

import numpy as np

from experiments.kinetics_k2.k2_config import (
    OBSERVABLE_NAMES,
    PARAMETER_NAMES,
    TRUTH_COORDINATES,
    chemistry_from_coordinates,
)
from experiments.kinetics_k2.k2_forward import ForwardBuildStats, resolve_worker_count
from src.engcore.domains.kinetics.cstr.inference import CSTRInferenceForwardAdapter
from src.engcore.inference import (
    AdmittedForwardRow,
    AdmittedForwardTable,
    GaussianObservation,
    InferenceAdmissibilityError,
    ObservationSet,
)
from src.engcore.scientific.units.quantity import Quantity

from .k3_config import (
    HOLDOUT_BY_ID,
    HOLDOUT_IDS,
    PRIMARY_HOLDOUT_SEED,
    sigma_for_observable,
)


@dataclass(frozen=True)
class HoldoutForwardTask:
    index: int
    coordinates: tuple[float, float]


@dataclass(frozen=True)
class HoldoutForwardTaskResult:
    row: AdmittedForwardRow
    condition_attempts: int
    condition_admitted: int
    condition_rejected: int


@dataclass(frozen=True)
class HoldoutForwardBuildResult:
    table: AdmittedForwardTable
    stats: ForwardBuildStats


def evaluate_holdout_truth_predictions(
    *, condition_ids: Sequence[str] = HOLDOUT_IDS,
) -> dict[str, object]:
    chemistry = chemistry_from_coordinates(*TRUTH_COORDINATES)
    adapter = CSTRInferenceForwardAdapter()
    predictions: dict[str, object] = {}
    for condition_id in condition_ids:
        condition = HOLDOUT_BY_ID[str(condition_id)]
        predictions[condition.condition_id] = adapter.evaluate(
            condition.build(chemistry),
            observable_names=OBSERVABLE_NAMES,
            run_id_prefix=f"k3-truth-{condition.condition_id}",
        )
    return predictions


def holdout_truth_means(
    *, condition_ids: Sequence[str] = HOLDOUT_IDS,
) -> dict[str, Quantity]:
    predictions = evaluate_holdout_truth_predictions(condition_ids=condition_ids)
    means: dict[str, Quantity] = {}
    for condition_id, prediction in predictions.items():
        for observable_name in OBSERVABLE_NAMES:
            means[f"{condition_id}:{observable_name}"] = prediction.value(observable_name)
    return means


def holdout_observation_set_from_truth_means(
    means: Mapping[str, Quantity],
    *,
    seed: int = PRIMARY_HOLDOUT_SEED,
    condition_ids: Sequence[str] = HOLDOUT_IDS,
    dataset_id: str | None = None,
) -> ObservationSet:
    rng = np.random.default_rng(int(seed))
    observations: list[GaussianObservation] = []
    for condition_id in condition_ids:
        condition_id = str(condition_id)
        for observable_name in OBSERVABLE_NAMES:
            key = f"{condition_id}:{observable_name}"
            if key not in means:
                raise ValueError(f"missing K3 truth mean {key!r}")
            mean = means[key]
            sigma = sigma_for_observable(observable_name).to(mean.units)
            noisy = mean.magnitude + float(rng.normal(0.0, sigma.magnitude))
            observations.append(
                GaussianObservation(
                    condition_id=condition_id,
                    observable_name=observable_name,
                    value=Quantity(noisy, mean.units),
                    sigma=sigma,
                    source_ref=f"k3-synthetic-holdout-seed:{int(seed)}:{key}",
                )
            )
    return ObservationSet(
        observations=tuple(observations),
        dataset_id=dataset_id or f"K3-holdout-seed-{int(seed)}",
    )


def holdout_template_observations(
    means: Mapping[str, Quantity],
    *,
    condition_ids: Sequence[str] = HOLDOUT_IDS,
) -> ObservationSet:
    """Stable key/unit template for the predictive forward table.

    Values equal the admitted truth means only to define the observation schema;
    they are never used to fit the K2 posterior or score the predictive UQ.
    """
    observations: list[GaussianObservation] = []
    for condition_id in condition_ids:
        condition_id = str(condition_id)
        for observable_name in OBSERVABLE_NAMES:
            key = f"{condition_id}:{observable_name}"
            mean = means[key]
            observations.append(
                GaussianObservation(
                    condition_id=condition_id,
                    observable_name=observable_name,
                    value=mean,
                    sigma=sigma_for_observable(observable_name).to(mean.units),
                    source_ref=f"k3-holdout-schema:{key}",
                )
            )
    return ObservationSet(tuple(observations), dataset_id="K3-holdout-schema")


def _evaluate_holdout_task(
    task: HoldoutForwardTask,
    observations: ObservationSet,
    condition_ids: tuple[str, ...],
) -> HoldoutForwardTaskResult:
    chemistry = chemistry_from_coordinates(*task.coordinates)
    adapter = CSTRInferenceForwardAdapter()
    predictions: dict[str, object] = {}
    rejections: list[str] = []
    admitted = 0

    for condition_id in condition_ids:
        condition = HOLDOUT_BY_ID[condition_id]
        try:
            predictions[condition_id] = adapter.evaluate(
                condition.build(chemistry),
                observable_names=OBSERVABLE_NAMES,
                run_id_prefix=f"k3-grid-{task.index}-{condition_id}",
            )
            admitted += 1
        except InferenceAdmissibilityError as exc:
            rejections.append(f"{condition_id}: {exc}")

    attempts = len(condition_ids)
    rejected = attempts - admitted
    if rejections:
        row = AdmittedForwardRow.rejected(
            task.coordinates,
            observations,
            "; ".join(rejections),
        )
    else:
        row = AdmittedForwardRow.from_predictions(
            task.coordinates,
            observations,
            predictions,
        )
    return HoldoutForwardTaskResult(row, attempts, admitted, rejected)


def build_holdout_forward_table_with_stats(
    points: np.ndarray,
    observations: ObservationSet,
    *,
    condition_ids: Sequence[str] = HOLDOUT_IDS,
    workers: str | int = "auto",
    progress_callback: Callable[[int, int], None] | None = None,
) -> HoldoutForwardBuildResult:
    points = np.asarray(points, dtype=np.float64)
    if points.ndim != 2 or points.shape[1] != 2:
        raise ValueError("K3 points must have shape (N, 2)")
    condition_ids = tuple(str(value) for value in condition_ids)
    if not condition_ids:
        raise ValueError("K3 holdout table requires at least one condition")
    unknown = [value for value in condition_ids if value not in HOLDOUT_BY_ID]
    if unknown:
        raise ValueError(f"unknown K3 holdout condition ids: {unknown!r}")

    tasks = [
        HoldoutForwardTask(i, (float(row[0]), float(row[1])))
        for i, row in enumerate(points)
    ]
    n_workers = resolve_worker_count(workers, len(tasks))
    results: list[HoldoutForwardTaskResult] = []

    if n_workers == 1:
        iterator = (
            _evaluate_holdout_task(task, observations, condition_ids)
            for task in tasks
        )
        for completed, result in enumerate(iterator, 1):
            results.append(result)
            if progress_callback is not None:
                progress_callback(completed, len(tasks))
    else:
        with ProcessPoolExecutor(max_workers=n_workers) as executor:
            iterator = executor.map(
                _evaluate_holdout_task,
                tasks,
                repeat(observations),
                repeat(condition_ids),
                chunksize=1,
            )
            for completed, result in enumerate(iterator, 1):
                results.append(result)
                if progress_callback is not None:
                    progress_callback(completed, len(tasks))

    table = AdmittedForwardTable.from_rows(
        PARAMETER_NAMES,
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
    return HoldoutForwardBuildResult(table, stats)
