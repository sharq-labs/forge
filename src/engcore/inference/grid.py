"""Small reusable grid-inference engine pulled by K2.

The important boundary is ingestion, not storage representation.  Domain
predictions must first be ``AdmissibleNumericalPrediction`` objects.  Only then
may this module compact their unit-bearing observable values into an immutable
numeric row for efficient likelihood arithmetic.  Likelihood code therefore
never accepts solver arrays, mappings, or ``ScientificResult`` directly.

This module deliberately implements only what K2 needs: Gaussian observations,
a precomputed forward table, and an exact discrete posterior on that table.  It
contains no CSTR semantics and no solver execution policy.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import numpy as np

from ..scientific.units.quantity import Quantity
from .admissibility import (
    AdmissibleNumericalPrediction,
    InferenceAdmissibilityError,
    require_admissible_numerical_prediction,
)


class InferenceProblemError(ValueError):
    """Raised when a declared inference problem is internally inconsistent."""


@dataclass(frozen=True)
class GaussianObservation:
    """One unit-bearing scalar observation with a declared Gaussian sigma."""

    condition_id: str
    observable_name: str
    value: Quantity
    sigma: Quantity
    source_ref: str

    def __post_init__(self) -> None:
        for label in ("condition_id", "observable_name", "source_ref"):
            text = str(getattr(self, label)).strip()
            if not text:
                raise InferenceProblemError(f"observation requires non-empty {label}")
            object.__setattr__(self, label, text)
        if not isinstance(self.value, Quantity) or not isinstance(self.sigma, Quantity):
            raise InferenceProblemError("observation value and sigma must be Quantity")
        self.value.require_compatible(self.sigma, context="observation sigma")
        if self.sigma.magnitude_in(self.value.units) <= 0.0:
            raise InferenceProblemError("observation sigma must be strictly positive")

    @property
    def key(self) -> str:
        return f"{self.condition_id}:{self.observable_name}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "condition_id": self.condition_id,
            "observable_name": self.observable_name,
            "value": self.value.to_dict(),
            "sigma": self.sigma.to_dict(),
            "source_ref": self.source_ref,
        }


@dataclass(frozen=True)
class ObservationSet:
    observations: tuple[GaussianObservation, ...]
    dataset_id: str

    def __post_init__(self) -> None:
        dataset_id = str(self.dataset_id).strip()
        if not dataset_id:
            raise InferenceProblemError("observation set requires dataset_id")
        object.__setattr__(self, "dataset_id", dataset_id)
        observations = tuple(self.observations)
        if not observations:
            raise InferenceProblemError("observation set must not be empty")
        if any(not isinstance(item, GaussianObservation) for item in observations):
            raise InferenceProblemError("observation set contains a non-observation")
        keys = [item.key for item in observations]
        if len(set(keys)) != len(keys):
            raise InferenceProblemError(f"duplicate observation keys: {keys!r}")
        object.__setattr__(self, "observations", observations)

    @property
    def keys(self) -> tuple[str, ...]:
        return tuple(item.key for item in self.observations)

    def subset(self, condition_ids: Sequence[str], *, dataset_id: str) -> "ObservationSet":
        wanted = {str(value) for value in condition_ids}
        return ObservationSet(
            observations=tuple(
                item for item in self.observations if item.condition_id in wanted
            ),
            dataset_id=dataset_id,
        )

    def numeric_vectors(self) -> tuple[np.ndarray, np.ndarray]:
        values = np.asarray([item.value.magnitude for item in self.observations], dtype=np.float64)
        sigmas = np.asarray(
            [item.sigma.magnitude_in(item.value.units) for item in self.observations],
            dtype=np.float64,
        )
        return values, sigmas

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_id": self.dataset_id,
            "observations": [item.to_dict() for item in self.observations],
        }


@dataclass(frozen=True)
class AdmittedForwardRow:
    """Compact row produced only after domain predictions cross K1.5 admission."""

    coordinates: tuple[float, ...]
    observation_keys: tuple[str, ...]
    values: tuple[float, ...]
    admission_refs: tuple[str, ...]
    admissible: bool = True
    rejection_reason: str = ""

    @classmethod
    def from_predictions(
        cls,
        coordinates: Sequence[float],
        observations: ObservationSet,
        predictions_by_condition: Mapping[str, AdmissibleNumericalPrediction],
    ) -> "AdmittedForwardRow":
        numeric: list[float] = []
        refs: list[str] = []
        for observation in observations.observations:
            if observation.condition_id not in predictions_by_condition:
                raise InferenceAdmissibilityError(
                    f"missing admitted prediction for condition {observation.condition_id!r}"
                )
            prediction = require_admissible_numerical_prediction(
                predictions_by_condition[observation.condition_id]
            )
            value = prediction.value(observation.observable_name)
            value.require_compatible(
                observation.value, context=f"forward observable {observation.key}"
            )
            numeric.append(value.magnitude_in(observation.value.units))
            refs.append(
                f"{prediction.prediction_id}|{prediction.verification_ref}|"
                f"{prediction.binding_ref}"
            )
        return cls(
            coordinates=tuple(float(v) for v in coordinates),
            observation_keys=observations.keys,
            values=tuple(numeric),
            admission_refs=tuple(refs),
            admissible=True,
            rejection_reason="",
        )

    @classmethod
    def rejected(
        cls,
        coordinates: Sequence[float],
        observations: ObservationSet,
        reason: str,
    ) -> "AdmittedForwardRow":
        text = str(reason).strip() or "forward prediction was not scientifically admissible"
        return cls(
            coordinates=tuple(float(v) for v in coordinates),
            observation_keys=observations.keys,
            values=tuple(0.0 for _ in observations.observations),
            admission_refs=(),
            admissible=False,
            rejection_reason=text,
        )


@dataclass(frozen=True)
class AdmittedForwardTable:
    """Immutable numeric table whose rows have already crossed domain admission."""

    parameter_names: tuple[str, ...]
    observation_keys: tuple[str, ...]
    points: np.ndarray
    values: np.ndarray
    admissible_mask: np.ndarray
    admission_refs: tuple[tuple[str, ...], ...]
    rejection_reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        names = tuple(str(v).strip() for v in self.parameter_names)
        keys = tuple(str(v).strip() for v in self.observation_keys)
        if not names or any(not value for value in names) or len(set(names)) != len(names):
            raise InferenceProblemError("parameter names must be unique and non-empty")
        if not keys or any(not value for value in keys) or len(set(keys)) != len(keys):
            raise InferenceProblemError("observation keys must be unique and non-empty")

        points = np.array(self.points, dtype=np.float64, copy=True)
        values = np.array(self.values, dtype=np.float64, copy=True)
        mask = np.array(self.admissible_mask, dtype=bool, copy=True)
        if points.ndim != 2 or points.shape[1] != len(names):
            raise InferenceProblemError("forward-table point shape does not match parameters")
        if values.shape != (points.shape[0], len(keys)):
            raise InferenceProblemError("forward-table value shape does not match observations")
        if mask.shape != (points.shape[0],):
            raise InferenceProblemError("forward-table mask shape is invalid")
        if not np.all(np.isfinite(points)):
            raise InferenceProblemError("parameter grid contains non-finite coordinates")
        if np.any(mask) and not np.all(np.isfinite(values[mask])):
            raise InferenceProblemError("admitted forward rows must contain finite values")
        if len(self.admission_refs) != points.shape[0] or len(self.rejection_reasons) != points.shape[0]:
            raise InferenceProblemError("forward-table audit vectors have wrong length")

        points.setflags(write=False)
        values.setflags(write=False)
        mask.setflags(write=False)
        object.__setattr__(self, "parameter_names", names)
        object.__setattr__(self, "observation_keys", keys)
        object.__setattr__(self, "points", points)
        object.__setattr__(self, "values", values)
        object.__setattr__(self, "admissible_mask", mask)
        object.__setattr__(self, "admission_refs", tuple(tuple(v) for v in self.admission_refs))
        object.__setattr__(self, "rejection_reasons", tuple(str(v) for v in self.rejection_reasons))

    @classmethod
    def from_rows(
        cls,
        parameter_names: Sequence[str],
        observations: ObservationSet,
        rows: Sequence[AdmittedForwardRow],
    ) -> "AdmittedForwardTable":
        rows = tuple(rows)
        if not rows:
            raise InferenceProblemError("cannot build an empty forward table")
        for row in rows:
            if row.observation_keys != observations.keys:
                raise InferenceProblemError("forward row observation order does not match dataset")
        return cls(
            parameter_names=tuple(parameter_names),
            observation_keys=observations.keys,
            points=np.asarray([row.coordinates for row in rows], dtype=np.float64),
            values=np.asarray([row.values for row in rows], dtype=np.float64),
            admissible_mask=np.asarray([row.admissible for row in rows], dtype=bool),
            admission_refs=tuple(row.admission_refs for row in rows),
            rejection_reasons=tuple(row.rejection_reason for row in rows),
        )

    def select_observations(self, observations: ObservationSet) -> tuple[np.ndarray, tuple[int, ...]]:
        index = {key: i for i, key in enumerate(self.observation_keys)}
        try:
            columns = tuple(index[key] for key in observations.keys)
        except KeyError as exc:
            raise InferenceProblemError(
                f"forward table does not contain observation {exc.args[0]!r}"
            ) from exc
        return self.values[:, columns], columns


@dataclass(frozen=True)
class PosteriorGrid:
    parameter_names: tuple[str, ...]
    points: np.ndarray
    weights: np.ndarray
    log_likelihood: np.ndarray
    admissible_mask: np.ndarray
    dataset_id: str

    def __post_init__(self) -> None:
        points = np.array(self.points, dtype=np.float64, copy=True)
        weights = np.array(self.weights, dtype=np.float64, copy=True)
        log_likelihood = np.array(self.log_likelihood, dtype=np.float64, copy=True)
        mask = np.array(self.admissible_mask, dtype=bool, copy=True)
        n = points.shape[0]
        if points.ndim != 2 or weights.shape != (n,) or log_likelihood.shape != (n,) or mask.shape != (n,):
            raise InferenceProblemError("posterior-grid arrays have inconsistent shapes")
        if not np.all(np.isfinite(points)) or not np.all(np.isfinite(weights)):
            raise InferenceProblemError("posterior points/weights must be finite")
        if np.any(weights < 0.0):
            raise InferenceProblemError("posterior weights cannot be negative")
        total = float(weights.sum())
        if not math.isfinite(total) or abs(total - 1.0) > 1.0e-12:
            raise InferenceProblemError(f"posterior weights must sum to one, got {total!r}")
        points.setflags(write=False)
        weights.setflags(write=False)
        log_likelihood.setflags(write=False)
        mask.setflags(write=False)
        object.__setattr__(self, "points", points)
        object.__setattr__(self, "weights", weights)
        object.__setattr__(self, "log_likelihood", log_likelihood)
        object.__setattr__(self, "admissible_mask", mask)

    @property
    def mean(self) -> np.ndarray:
        return np.sum(self.points * self.weights[:, None], axis=0)

    @property
    def covariance(self) -> np.ndarray:
        centered = self.points - self.mean
        return centered.T @ (centered * self.weights[:, None])

    @property
    def correlation(self) -> np.ndarray:
        covariance = self.covariance
        std = np.sqrt(np.maximum(np.diag(covariance), 0.0))
        denom = np.outer(std, std)
        with np.errstate(divide="ignore", invalid="ignore"):
            result = np.divide(covariance, denom, out=np.zeros_like(covariance), where=denom > 0.0)
        return result

    @property
    def map_point(self) -> np.ndarray:
        return self.points[int(np.argmax(self.weights))]

    def marginal_interval(self, parameter_index: int, mass: float = 0.95) -> tuple[float, float]:
        if not (0.0 < mass < 1.0):
            raise InferenceProblemError("credible mass must lie strictly between 0 and 1")
        values = self.points[:, int(parameter_index)]
        order = np.argsort(values, kind="stable")
        sorted_values = values[order]
        cumulative = np.cumsum(self.weights[order])
        tail = (1.0 - mass) / 2.0
        lower_i = min(int(np.searchsorted(cumulative, tail, side="left")), len(order) - 1)
        upper_i = min(int(np.searchsorted(cumulative, 1.0 - tail, side="left")), len(order) - 1)
        return float(sorted_values[lower_i]), float(sorted_values[upper_i])

    def summary(self) -> dict[str, Any]:
        covariance = self.covariance
        correlation = self.correlation
        return {
            "dataset_id": self.dataset_id,
            "parameter_names": list(self.parameter_names),
            "mean": self.mean.tolist(),
            "std": np.sqrt(np.maximum(np.diag(covariance), 0.0)).tolist(),
            "map": self.map_point.tolist(),
            "credible_95": [
                list(self.marginal_interval(i, 0.95))
                for i in range(len(self.parameter_names))
            ],
            "covariance": covariance.tolist(),
            "covariance_determinant": float(np.linalg.det(covariance)),
            "correlation": correlation.tolist(),
            "admissible_fraction": float(np.mean(self.admissible_mask)),
        }


def gaussian_grid_posterior(
    table: AdmittedForwardTable,
    observations: ObservationSet,
) -> PosteriorGrid:
    """Exact discrete posterior for a uniform prior over the supplied grid."""
    predictions, _columns = table.select_observations(observations)
    observed, sigma = observations.numeric_vectors()
    residual = (predictions - observed[None, :]) / sigma[None, :]
    log_norm = np.log(2.0 * math.pi * sigma * sigma)
    log_like = -0.5 * np.sum(residual * residual + log_norm[None, :], axis=1)
    log_like = np.asarray(log_like, dtype=np.float64)
    log_like[~table.admissible_mask] = -np.inf

    finite = np.isfinite(log_like)
    if not np.any(finite):
        raise InferenceProblemError("no scientifically admissible grid point has finite likelihood")
    pivot = float(np.max(log_like[finite]))
    unnormalized = np.zeros_like(log_like)
    unnormalized[finite] = np.exp(log_like[finite] - pivot)
    total = float(np.sum(unnormalized))
    if not math.isfinite(total) or total <= 0.0:
        raise InferenceProblemError("posterior normalization has zero/non-finite mass")
    weights = unnormalized / total
    # Normalize once more in float64 so the stored vector satisfies the strict
    # contract even if the first division accumulated a last-bit sum error.
    weights = weights / float(np.sum(weights))
    return PosteriorGrid(
        parameter_names=table.parameter_names,
        points=table.points,
        weights=weights,
        log_likelihood=log_like,
        admissible_mask=table.admissible_mask,
        dataset_id=observations.dataset_id,
    )
