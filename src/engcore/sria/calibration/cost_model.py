"""Realized-cost model — transparent by choice.

Predicts ``p(cost | structure, environment, solver/config, covariates)`` with a
hierarchical median-in-log-space estimator and explicit backoff:

    structure x environment x solver  ->  structure x solver
      ->  structure x environment  ->  structure  ->  global

Why a median in log space rather than a regressor on raw seconds: observed
costs in this repository span four orders of magnitude (0.008 s to 144 s).
A squared-error fit on raw seconds would be dominated entirely by the slowest
configuration and would predict nonsense for the fastest. The log transform
makes the error scale-free, and the median makes it robust to the occasional
pathological run.

Why not something stronger: a model that cannot be read cannot be audited, and
M2's job is to be *trustworthy* about computational behaviour, not to win a
benchmark. If the transparent estimator does not beat its baselines, that is a
finding to report, not a reason to reach for gradient boosting.

**Censoring is not a runtime.** A right-censored observation says "at least
this long". Including it as if it were the completed duration biases every
estimate downward, which is precisely the direction that makes a scheduler
over-commit. Censored rows therefore never enter the median; they are counted,
and a cell whose censoring fraction is material is reported as a *lower bound*
so the Calibration Critic can degrade it.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from ...scientific.serialization import require_schema, schema_string
from ..outcomes import CensoringType
from .learning_record import ComputationalLearningRecord

COST_MODEL_SCHEMA = schema_string("sria_cost_model")
COST_PREDICTION_SCHEMA = schema_string("sria_cost_prediction")

COST_MODEL_VERSION = "cost/hierarchical-log-median/1"

#: A cell needs at least this many observed costs before it is used; below it
#: the estimator backs off rather than trusting one or two runs.
MIN_CELL_SUPPORT = 3

#: Above this censored fraction a cell's estimate is flagged as a lower bound.
CENSORING_FLAG_FRACTION = 0.2

#: Nominal coverage the predicted interval claims, and the MAD multiplier that
#: delivers it. For a roughly normal residual, MAD ~ 0.6745 sigma, so a +/-1 MAD
#: band is a ~50% interval — not the ~80% one a consumer would assume. The
#: multiplier converts to the stated level (z_0.90 / 0.6745). Stating the level
#: and emitting a different one is how interval coverage quietly becomes
#: decorative.
NOMINAL_INTERVAL_COVERAGE = 0.80
MAD_TO_NOMINAL_INTERVAL = 1.2816 / 0.6745    # ~1.900


@dataclass(frozen=True)
class CostPrediction:
    """A cost prediction with its provenance and its honesty flags."""

    point: float                     # seconds
    lower: float
    upper: float
    log10_point: float
    cell: str
    support: int
    is_lower_bound: bool = False
    model_version: str = COST_MODEL_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": COST_PREDICTION_SCHEMA,
            "point": self.point,
            "lower": self.lower,
            "upper": self.upper,
            "log10_point": self.log10_point,
            "cell": self.cell,
            "support": self.support,
            "is_lower_bound": self.is_lower_bound,
            "model_version": self.model_version,
        }


@dataclass(frozen=True)
class CostCell:
    """One fitted calibration cell."""

    key: str
    level: str
    median_log10: float
    mad_log10: float
    support: int
    censored: int = 0

    @property
    def censoring_fraction(self) -> float:
        total = self.support + self.censored
        return self.censored / total if total else 0.0

    @property
    def is_lower_bound(self) -> bool:
        return self.censoring_fraction > CENSORING_FLAG_FRACTION


def _log10_cost(record: ComputationalLearningRecord) -> float | None:
    if record.realized_cost is None:
        return None
    # Guard the zero/sub-tick case: sub-millisecond timings are real here.
    return math.log10(max(record.realized_cost, 1e-6))


class CostModel:
    """Hierarchical median-in-log-space cost estimator."""

    def __init__(self, *, interval_multiplier: float = MAD_TO_NOMINAL_INTERVAL) -> None:
        self._cells: dict[str, CostCell] = {}
        self._interval_z = float(interval_multiplier)
        self._training_provenance: dict[str, Any] = {}
        self._fitted = False

    # ---- keys -----------------------------------------------------------
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

    # ---- fit ------------------------------------------------------------
    def fit(
        self,
        records: Sequence[ComputationalLearningRecord],
        *,
        dataset_id: str = "",
    ) -> "CostModel":
        buckets: dict[str, list[float]] = {}
        levels: dict[str, str] = {}
        censored: dict[str, int] = {}

        used = 0
        censored_total = 0
        for record in records:
            if record.realized_cost is None:
                continue
            keys = self._keys(record)
            if record.cost_censoring is not CensoringType.NONE:
                censored_total += 1
                for key, _ in keys:
                    censored[key] = censored.get(key, 0) + 1
                continue    # a lower bound is not a runtime
            value = _log10_cost(record)
            if value is None:
                continue
            used += 1
            for key, level in keys:
                buckets.setdefault(key, []).append(value)
                levels[key] = level

        self._cells = {}
        for key, values in buckets.items():
            median = statistics.median(values)
            deviations = [abs(v - median) for v in values]
            mad = statistics.median(deviations) if deviations else 0.0
            self._cells[key] = CostCell(
                key=key,
                level=levels[key],
                median_log10=median,
                mad_log10=mad,
                support=len(values),
                censored=censored.get(key, 0),
            )

        self._training_provenance = {
            "dataset_id": dataset_id,
            "records_seen": len(records),
            "observed_costs_used": used,
            "censored_excluded": censored_total,
            "cells_fitted": len(self._cells),
            "model_version": COST_MODEL_VERSION,
            "min_cell_support": MIN_CELL_SUPPORT,
        }
        self._fitted = True
        return self

    # ---- predict --------------------------------------------------------
    def predict(self, record: ComputationalLearningRecord) -> CostPrediction:
        if not self._fitted:
            raise RuntimeError("CostModel.predict called before fit")

        for key, _level in self._keys(record):
            cell = self._cells.get(key)
            if cell is None or cell.support < MIN_CELL_SUPPORT:
                continue
            spread = cell.mad_log10 * self._interval_z
            return CostPrediction(
                point=10.0 ** cell.median_log10,
                lower=10.0 ** (cell.median_log10 - spread),
                upper=10.0 ** (cell.median_log10 + spread),
                log10_point=cell.median_log10,
                cell=f"{cell.key} [{cell.level}]",
                support=cell.support,
                is_lower_bound=cell.is_lower_bound,
            )

        raise RuntimeError(
            "no cell reached minimum support, not even the global one; the "
            "model was fitted on effectively no observed costs"
        )

    # ---- introspection --------------------------------------------------
    @property
    def training_provenance(self) -> Mapping[str, Any]:
        return dict(self._training_provenance)

    @property
    def model_version(self) -> str:
        return COST_MODEL_VERSION

    def cells(self) -> tuple[CostCell, ...]:
        return tuple(sorted(self._cells.values(), key=lambda c: c.key))

    def summary(self) -> dict[str, Any]:
        return {
            "schema": COST_MODEL_SCHEMA,
            "model_version": COST_MODEL_VERSION,
            "cells": len(self._cells),
            "training_provenance": dict(self._training_provenance),
        }


# =====================================================================
# Baselines — the bar the learned model must clear
# =====================================================================

class _MedianBaseline:
    """Median-in-log-space over a fixed grouping."""

    def __init__(self, level: str) -> None:
        self.level = level
        self._by_key: dict[str, float] = {}
        self._global = 0.0

    def _key(self, record: ComputationalLearningRecord) -> str:
        s = record.structure.digest[:12]
        e = record.environment.digest[:12]
        if self.level == "global":
            return "global"
        if self.level == "structure":
            return f"struct={s}"
        if self.level == "structure_environment":
            return f"struct={s}|env={e}"
        raise ValueError(f"unknown baseline level {self.level!r}")

    def fit(self, records: Sequence[ComputationalLearningRecord]) -> "_MedianBaseline":
        buckets: dict[str, list[float]] = {}
        everything: list[float] = []
        for record in records:
            if not record.cost_is_observed:
                continue
            value = _log10_cost(record)
            if value is None:
                continue
            buckets.setdefault(self._key(record), []).append(value)
            everything.append(value)
        self._by_key = {k: statistics.median(v) for k, v in buckets.items()}
        self._global = statistics.median(everything) if everything else 0.0
        return self

    def predict_log10(self, record: ComputationalLearningRecord) -> float:
        return self._by_key.get(self._key(record), self._global)


def cost_baselines() -> dict[str, _MedianBaseline]:
    return {
        "global_median": _MedianBaseline("global"),
        "structure_median": _MedianBaseline("structure"),
        "structure_environment_median": _MedianBaseline("structure_environment"),
    }


@dataclass(frozen=True)
class CostEvaluation:
    """Held-out cost performance, in log10 units (a scale-free error)."""

    name: str
    mae_log10: float
    median_ae_log10: float
    n: int
    coverage: float | None = None

    @property
    def fold_error(self) -> float:
        """MAE expressed as a multiplicative factor, which is readable."""
        return 10.0 ** self.mae_log10

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "mae_log10": self.mae_log10,
            "median_ae_log10": self.median_ae_log10,
            "fold_error": self.fold_error,
            "n": self.n,
            "coverage": self.coverage,
        }


def evaluate_cost(
    name: str,
    predictions_log10: Iterable[float],
    records: Sequence[ComputationalLearningRecord],
    *,
    intervals: Sequence[tuple[float, float]] | None = None,
) -> CostEvaluation:
    """Score predictions against observed (uncensored) costs only."""
    errors: list[float] = []
    covered = 0
    counted = 0
    preds = list(predictions_log10)

    for index, record in enumerate(records):
        if not record.cost_is_observed:
            continue
        actual = _log10_cost(record)
        if actual is None:
            continue
        errors.append(abs(preds[index] - actual))
        if intervals is not None:
            low, high = intervals[index]
            counted += 1
            if low <= record.realized_cost <= high:
                covered += 1

    if not errors:
        raise ValueError(f"no observed costs to evaluate for {name!r}")

    return CostEvaluation(
        name=name,
        mae_log10=sum(errors) / len(errors),
        median_ae_log10=statistics.median(errors),
        n=len(errors),
        coverage=(covered / counted) if counted else None,
    )
