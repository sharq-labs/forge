"""Computational success-probability model.

Learns ``P(computational success | structure, environment, solver/config)``
with a Laplace-smoothed rate and the same backoff ladder as the cost model.

Three admission rules, all enforced rather than documented:

1. **Only ``informative_for_pf`` records train it.** An infrastructure failure
   says something about the cluster, not the solver. Letting one in shifts the
   estimate for every problem that happened to run on a bad node.
2. **``UNATTRIBUTED`` rows are structurally excluded.** They arrive from the
   bridge already marked ineligible; :meth:`fit` re-checks rather than trusting
   the upstream flag, because this is the exact place where a mislabeled row
   does lasting damage.
3. **A degenerate target is not a model.** If the eligible data contains no
   variance — all successes or all failures — the model reports
   ``INSUFFICIENT_DATA`` instead of a confident constant. A 100%-success
   estimator fitted on 1,320 successes and zero failures would be perfectly
   calibrated on its training set and worthless in every way that matters.

The target is deliberately binary success, not multi-class cause attribution.
V0.1 does not have the labelled data to separate numerical from coupling from
scope failure, and a four-way classifier fitted on guesses would be worse than
no classifier.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from ...scientific.serialization import schema_string
from ..outcomes import AttributedCause
from .learning_record import ComputationalLearningRecord

FAILURE_MODEL_SCHEMA = schema_string("sria_failure_model")
FAILURE_MODEL_VERSION = "failure/smoothed-rate-backoff/1"

MIN_CELL_SUPPORT = 5
LAPLACE_ALPHA = 1.0


class InsufficientFailureData(Exception):
    """The eligible corpus cannot support a failure model."""


@dataclass(frozen=True)
class FailurePrediction:
    probability_success: float
    cell: str
    support: int
    model_version: str = FAILURE_MODEL_VERSION

    @property
    def probability_failure(self) -> float:
        return 1.0 - self.probability_success


@dataclass(frozen=True)
class FailureCell:
    key: str
    level: str
    successes: int
    trials: int

    @property
    def rate(self) -> float:
        return (self.successes + LAPLACE_ALPHA) / (self.trials + 2 * LAPLACE_ALPHA)


def eligible_records(
    records: Iterable[ComputationalLearningRecord],
) -> tuple[ComputationalLearningRecord, ...]:
    """Rows that may legitimately train a *computational* failure model.

    Delegates to the record's own eligibility so there is exactly one
    definition. Excluded: infrastructure loss (exogenous), unattributed causes
    (unknown), and — added in M2.1 — **infeasibility**, which is a property of
    the design point rather than of the numerics. An infeasible candidate whose
    solve ran perfectly is evidence about the feasible region, and training
    solver reliability on it would make every well-explored infeasible region
    look like a broken solver.
    """
    return tuple(
        r for r in records if r.eligible_for_computational_failure_learning
    )


def feasibility_records(
    records: Iterable[ComputationalLearningRecord],
) -> tuple[ComputationalLearningRecord, ...]:
    """Rows eligible for a *feasibility* model.

    M2 does not implement feasibility learning. This exists so infeasible rows
    have a declared destination instead of being silently dropped or, worse,
    folded into the solver-failure target.
    """
    return tuple(r for r in records if r.eligible_for_feasibility_learning)


class FailureModel:
    """Smoothed success-rate estimator with structure/environment backoff."""

    def __init__(self) -> None:
        self._cells: dict[str, FailureCell] = {}
        self._training_provenance: dict[str, Any] = {}
        self._fitted = False

    @staticmethod
    def _keys(record: ComputationalLearningRecord) -> tuple[tuple[str, str], ...]:
        s = record.structure.digest[:12]
        e = record.environment.digest[:12]
        v = record.solver_identity[0]
        return (
            (f"struct={s}|env={e}|solver={v}", "structure x environment x solver"),
            (f"struct={s}|solver={v}", "structure x solver"),
            (f"struct={s}|env={e}", "structure x environment"),
            (f"struct={s}", "structure"),
            ("global", "global"),
        )

    def fit(
        self,
        records: Sequence[ComputationalLearningRecord],
        *,
        dataset_id: str = "",
    ) -> "FailureModel":
        usable = eligible_records(records)
        excluded = len(records) - len(usable)

        outcomes = [r.computational_success for r in usable]
        successes = sum(1 for o in outcomes if o)
        failures = len(outcomes) - successes

        self._training_provenance = {
            "dataset_id": dataset_id,
            "records_seen": len(records),
            "eligible": len(usable),
            "excluded_ineligible": excluded,
            "successes": successes,
            "failures": failures,
            "model_version": FAILURE_MODEL_VERSION,
        }

        if not usable:
            raise InsufficientFailureData(
                "no records are eligible for supervised failure learning"
            )
        if failures == 0 or successes == 0:
            raise InsufficientFailureData(
                f"target has no variance ({successes} successes, {failures} "
                f"failures); a constant predictor is not a calibrated model and "
                f"would report perfect training accuracy while knowing nothing"
            )

        buckets: dict[str, list[bool]] = {}
        levels: dict[str, str] = {}
        for record in usable:
            for key, level in self._keys(record):
                buckets.setdefault(key, []).append(record.computational_success)
                levels[key] = level

        self._cells = {
            key: FailureCell(
                key=key,
                level=levels[key],
                successes=sum(1 for v in values if v),
                trials=len(values),
            )
            for key, values in buckets.items()
        }
        self._fitted = True
        return self

    def predict(self, record: ComputationalLearningRecord) -> FailurePrediction:
        if not self._fitted:
            raise RuntimeError("FailureModel.predict called before fit")
        for key, _level in self._keys(record):
            cell = self._cells.get(key)
            if cell is None or cell.trials < MIN_CELL_SUPPORT:
                continue
            return FailurePrediction(
                probability_success=cell.rate,
                cell=f"{cell.key} [{cell.level}]",
                support=cell.trials,
            )
        raise RuntimeError("no cell reached minimum support")

    @property
    def training_provenance(self) -> Mapping[str, Any]:
        return dict(self._training_provenance)

    @property
    def model_version(self) -> str:
        return FAILURE_MODEL_VERSION

    def summary(self) -> dict[str, Any]:
        return {
            "schema": FAILURE_MODEL_SCHEMA,
            "model_version": FAILURE_MODEL_VERSION,
            "cells": len(self._cells),
            "training_provenance": dict(self._training_provenance),
        }


# =====================================================================
# Calibration metrics
# =====================================================================

@dataclass(frozen=True)
class FailureEvaluation:
    name: str
    brier: float
    log_loss: float
    n: int
    base_rate: float
    reliability_bins: tuple[tuple[float, float, int], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "brier": self.brier,
            "log_loss": self.log_loss,
            "n": self.n,
            "base_rate": self.base_rate,
            "reliability_bins": [list(b) for b in self.reliability_bins],
        }


def evaluate_failure(
    name: str,
    probabilities: Sequence[float],
    records: Sequence[ComputationalLearningRecord],
    *,
    bins: int = 5,
) -> FailureEvaluation:
    """Brier score, log loss and a reliability table.

    Accuracy is deliberately absent: on an imbalanced target it rewards a
    model for ignoring the minority class, which is the class that matters.
    """
    actuals = [1.0 if r.computational_success else 0.0 for r in records]
    if not actuals:
        raise ValueError(f"no records to evaluate for {name!r}")

    eps = 1e-12
    brier = sum((p - a) ** 2 for p, a in zip(probabilities, actuals)) / len(actuals)
    log_loss = -sum(
        a * math.log(max(p, eps)) + (1 - a) * math.log(max(1 - p, eps))
        for p, a in zip(probabilities, actuals)
    ) / len(actuals)

    table: list[tuple[float, float, int]] = []
    for index in range(bins):
        low, high = index / bins, (index + 1) / bins
        members = [
            (p, a)
            for p, a in zip(probabilities, actuals)
            if (low <= p < high) or (index == bins - 1 and p == 1.0)
        ]
        if members:
            table.append(
                (
                    statistics.mean(p for p, _ in members),
                    statistics.mean(a for _, a in members),
                    len(members),
                )
            )

    return FailureEvaluation(
        name=name,
        brier=brier,
        log_loss=log_loss,
        n=len(actuals),
        base_rate=statistics.mean(actuals),
        reliability_bins=tuple(table),
    )


def base_rate_baseline(
    train: Sequence[ComputationalLearningRecord],
) -> float:
    usable = eligible_records(train)
    if not usable:
        return 0.5
    return statistics.mean(
        1.0 if r.computational_success else 0.0 for r in usable
    )
