"""K2 domain execution bridge.

Scientific meaning stays in the CSTR adapter. This module only constructs the
frozen K2 parameterized reactor declarations, asks the adapter for admitted
predictions, and compacts those predictions into K2's shared forward-row type.

Execution telemetry is deliberately kept separate from scientific meaning.
Worker count, batching and timing may change; the admitted rows may not.
"""

from __future__ import annotations

import os
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from itertools import repeat
from typing import Callable, Mapping, Sequence

# Avoid nested BLAS/OpenMP fan-out when K2 uses process-level parallelism.
for _name in (
    "OMP_NUM_THREADS",
    "MKL_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
):
    os.environ.setdefault(_name, "1")

import numpy as np

from src.engcore.domains.kinetics.cstr.inference import CSTRInferenceForwardAdapter
from src.engcore.domains.kinetics.cstr.problem import CA_FINAL_METRIC, T_FINAL_METRIC
from src.engcore.inference import (
    AdmittedForwardRow,
    AdmittedForwardTable,
    GaussianObservation,
    InferenceAdmissibilityError,
    ObservationSet,
)
from src.engcore.scientific.units.quantity import Quantity

from .k2_config import (
    CONDITION_BY_ID,
    MULTI_CONDITION_IDS,
    OBSERVABLE_NAMES,
    PARAMETER_NAMES,
    PRIMARY_SEED,
    SIGMA_CONCENTRATION,
    SIGMA_TEMPERATURE,
    TRUTH_COORDINATES,
    chemistry_from_coordinates,
)


@dataclass(frozen=True)
class ForwardTask:
    index: int
    coordinates: tuple[float, float]


@dataclass(frozen=True)
class ForwardTaskResult:
    """One parameter point plus execution counts for its required conditions."""

    row: AdmittedForwardRow
    condition_attempts: int
    condition_admitted: int
    condition_rejected: int


@dataclass(frozen=True)
class ForwardBuildStats:
    """Deterministic counts plus execution-policy telemetry for one grid build."""

    parameter_points: int
    condition_attempts: int
    condition_admitted: int
    condition_rejected: int
    point_admitted: int
    point_rejected: int
    workers: int

    def to_dict(self) -> dict[str, int]:
        return {
            "parameter_points": self.parameter_points,
            "condition_attempts": self.condition_attempts,
            "condition_admitted": self.condition_admitted,
            "condition_rejected": self.condition_rejected,
            "point_admitted": self.point_admitted,
            "point_rejected": self.point_rejected,
            "workers": self.workers,
        }


@dataclass(frozen=True)
class ForwardBuildResult:
    table: AdmittedForwardTable
    stats: ForwardBuildStats


def _sigma_for(observable_name: str) -> Quantity:
    if observable_name == CA_FINAL_METRIC:
        return SIGMA_CONCENTRATION
    if observable_name == T_FINAL_METRIC:
        return SIGMA_TEMPERATURE
    raise ValueError(f"K2 has no noise declaration for observable {observable_name!r}")


def evaluate_truth_predictions(
    *, condition_ids: Sequence[str] = MULTI_CONDITION_IDS
) -> dict[str, object]:
    """Evaluate the frozen synthetic truth through the full K1.5 boundary."""
    chemistry = chemistry_from_coordinates(*TRUTH_COORDINATES)
    adapter = CSTRInferenceForwardAdapter()
    predictions: dict[str, object] = {}
    for condition_id in condition_ids:
        condition = CONDITION_BY_ID[str(condition_id)]
        predictions[condition.condition_id] = adapter.evaluate(
            condition.build(chemistry),
            observable_names=OBSERVABLE_NAMES,
            run_id_prefix=f"k2-truth-{condition.condition_id}",
        )
    return predictions


def truth_means(
    *, condition_ids: Sequence[str] = MULTI_CONDITION_IDS
) -> dict[str, Quantity]:
    predictions = evaluate_truth_predictions(condition_ids=condition_ids)
    means: dict[str, Quantity] = {}
    for condition_id, prediction in predictions.items():
        for observable_name in OBSERVABLE_NAMES:
            means[f"{condition_id}:{observable_name}"] = prediction.value(observable_name)
    return means


def observation_set_from_truth_means(
    means: Mapping[str, Quantity],
    *,
    seed: int = PRIMARY_SEED,
    condition_ids: Sequence[str] = MULTI_CONDITION_IDS,
    dataset_id: str | None = None,
) -> ObservationSet:
    """Generate seeded synthetic measurements from already-admitted truth means."""
    rng = np.random.default_rng(int(seed))
    observations: list[GaussianObservation] = []
    for condition_id in condition_ids:
        condition_id = str(condition_id)
        for observable_name in OBSERVABLE_NAMES:
            key = f"{condition_id}:{observable_name}"
            if key not in means:
                raise ValueError(f"missing truth mean {key!r}")
            mean = means[key]
            sigma = _sigma_for(observable_name).to(mean.units)
            noisy = mean.magnitude + float(rng.normal(0.0, sigma.magnitude))
            observations.append(
                GaussianObservation(
                    condition_id=condition_id,
                    observable_name=observable_name,
                    value=Quantity(noisy, mean.units),
                    sigma=sigma,
                    source_ref=f"synthetic-truth-seed:{int(seed)}:{key}",
                )
            )
    return ObservationSet(
        observations=tuple(observations),
        dataset_id=dataset_id or f"K2-seed-{int(seed)}",
    )


def generate_observation_set(
    *,
    seed: int = PRIMARY_SEED,
    condition_ids: Sequence[str] = MULTI_CONDITION_IDS,
) -> ObservationSet:
    """Convenience path for one-off studies; scored runs should reuse truth means."""
    means = truth_means(condition_ids=condition_ids)
    return observation_set_from_truth_means(
        means,
        seed=seed,
        condition_ids=condition_ids,
    )


def _evaluate_task(
    task: ForwardTask,
    observations: ObservationSet,
    condition_ids: tuple[str, ...],
) -> ForwardTaskResult:
    """Evaluate every required condition so K2 can report exact attempt counts.

    Once one condition is rejected the parameter point will receive zero
    posterior mass, but the remaining declared conditions are still evaluated.
    That costs some extra work on rejected points and gives the scored run exact
    parameter-condition admission/rejection counts rather than inferred counts.
    """
    log_k0, e_over_r_k = task.coordinates
    chemistry = chemistry_from_coordinates(log_k0, e_over_r_k)
    adapter = CSTRInferenceForwardAdapter()

    predictions: dict[str, object] = {}
    rejections: list[str] = []
    admitted = 0
    for condition_id in condition_ids:
        condition = CONDITION_BY_ID[condition_id]
        try:
            predictions[condition_id] = adapter.evaluate(
                condition.build(chemistry),
                observable_names=OBSERVABLE_NAMES,
                run_id_prefix=f"k2-grid-{task.index}-{condition_id}",
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
    return ForwardTaskResult(
        row=row,
        condition_attempts=attempts,
        condition_admitted=admitted,
        condition_rejected=rejected,
    )


def resolve_worker_count(requested: str | int, tasks: int) -> int:
    """Resolve a capability-based process count without hardware-name tables."""
    if isinstance(requested, int):
        if requested < 1:
            raise ValueError("workers must be at least one")
        return min(requested, max(tasks, 1))
    text = str(requested).strip().lower()
    if text != "auto":
        return resolve_worker_count(int(text), tasks)
    logical = max(1, int(os.cpu_count() or 1))
    # For small batches Windows spawn/IPC can exceed the scientific work. The
    # cutoff is workload-derived from available task count, not a CPU model.
    if tasks < logical:
        return 1
    return min(logical, tasks)


def build_forward_table_with_stats(
    points: np.ndarray,
    observations: ObservationSet,
    *,
    condition_ids: Sequence[str] = MULTI_CONDITION_IDS,
    workers: str | int = "auto",
    progress_callback: Callable[[int, int], None] | None = None,
) -> ForwardBuildResult:
    """Evaluate a complete parameter grid once and return exact work counts."""
    points = np.asarray(points, dtype=np.float64)
    if points.ndim != 2 or points.shape[1] != 2:
        raise ValueError("K2 points must have shape (N, 2)")
    condition_ids = tuple(str(value) for value in condition_ids)
    if not condition_ids:
        raise ValueError("K2 forward table requires at least one condition")
    unknown = [value for value in condition_ids if value not in CONDITION_BY_ID]
    if unknown:
        raise ValueError(f"unknown K2 condition ids: {unknown!r}")

    tasks = [
        ForwardTask(index=i, coordinates=(float(row[0]), float(row[1])))
        for i, row in enumerate(points)
    ]
    n_workers = resolve_worker_count(workers, len(tasks))

    results: list[ForwardTaskResult] = []
    if n_workers == 1:
        iterator = (
            _evaluate_task(task, observations, condition_ids)
            for task in tasks
        )
        for completed, result in enumerate(iterator, 1):
            results.append(result)
            if progress_callback is not None:
                progress_callback(completed, len(tasks))
    else:
        # Candidate rows vary materially in solver work. chunksize=1 is the
        # correctness-neutral baseline measured to work well for this class of
        # workload; later feedback tuning may change it without changing science.
        with ProcessPoolExecutor(max_workers=n_workers) as executor:
            iterator = executor.map(
                _evaluate_task,
                tasks,
                repeat(observations),
                repeat(condition_ids),
                chunksize=1,
            )
            for completed, result in enumerate(iterator, 1):
                results.append(result)
                if progress_callback is not None:
                    progress_callback(completed, len(tasks))

    rows = [result.row for result in results]
    table = AdmittedForwardTable.from_rows(PARAMETER_NAMES, observations, rows)
    stats = ForwardBuildStats(
        parameter_points=len(results),
        condition_attempts=sum(item.condition_attempts for item in results),
        condition_admitted=sum(item.condition_admitted for item in results),
        condition_rejected=sum(item.condition_rejected for item in results),
        point_admitted=sum(1 for item in results if item.row.admissible),
        point_rejected=sum(1 for item in results if not item.row.admissible),
        workers=n_workers,
    )
    return ForwardBuildResult(table=table, stats=stats)


def build_forward_table(
    points: np.ndarray,
    observations: ObservationSet,
    *,
    condition_ids: Sequence[str] = MULTI_CONDITION_IDS,
    workers: str | int = "auto",
) -> AdmittedForwardTable:
    """Compatibility wrapper returning only the admitted forward table."""
    return build_forward_table_with_stats(
        points,
        observations,
        condition_ids=condition_ids,
        workers=workers,
    ).table
