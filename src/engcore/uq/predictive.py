"""Reusable posterior-predictive uncertainty capability pulled by K3.

The engine consumes only a posterior already produced by the inference layer and
an :class:`AdmittedForwardTable` whose predictions crossed the domain
admissibility boundary.  It never accepts raw solver arrays as scientific
predictive support.

K3 deliberately separates two statements:

* epistemic / parameter uncertainty: the weighted distribution of admitted
  model means over posterior parameter support;
* total predictive uncertainty: that distribution convolved with an explicitly
  declared independent Gaussian observation-noise model.

No model-discrepancy term is invented here.  Model-form uncertainty belongs to
model adequacy / competition work (K4).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.special import ndtr

from ..inference import AdmittedForwardTable, PosteriorGrid
from ..scientific.ir.problem import ModelReference
from ..scientific.results.uncertainty import Uncertainty, UncertaintyKind
from ..scientific.twins import TwinReference
from ..scientific.units.quantity import Quantity, normalize_unit


class UQProblemError(ValueError):
    """Raised when a quantified-UQ request is internally inconsistent."""


@dataclass(frozen=True)
class PredictiveObservableSpec:
    """Unit/noise declaration for one predictive forward-table observable."""

    observation_key: str
    unit: str
    observation_sigma: Quantity | None = None

    def __post_init__(self) -> None:
        key = str(self.observation_key).strip()
        if not key:
            raise UQProblemError("predictive observable requires a non-empty observation_key")
        object.__setattr__(self, "observation_key", key)
        object.__setattr__(self, "unit", normalize_unit(self.unit))
        if self.observation_sigma is not None:
            if not isinstance(self.observation_sigma, Quantity):
                raise UQProblemError("observation_sigma must be a Quantity when supplied")
            self.observation_sigma.require_compatible(
                Quantity(1.0, self.unit), context=f"predictive noise {key}"
            )
            sigma = self.observation_sigma.to(self.unit)
            if sigma.magnitude <= 0.0:
                raise UQProblemError("observation_sigma must be strictly positive")
            object.__setattr__(self, "observation_sigma", sigma)


@dataclass(frozen=True)
class QuantifiedPredictiveResult:
    """One unit-bearing posterior-predictive UQ result.

    ``epistemic_*`` describe uncertainty in the latent model mean induced by
    posterior parameter uncertainty. ``total_*`` additionally include the
    declared independent observation noise.
    """

    observation_key: str
    mean: Quantity
    epistemic_standard_uncertainty: Quantity
    epistemic_interval: Uncertainty
    total_standard_uncertainty: Quantity
    total_interval: Uncertainty
    confidence_level: float
    posterior_dataset_id: str
    twin: TwinReference
    model: ModelReference
    source_ref: str
    posterior_support_size: int

    def __post_init__(self) -> None:
        if not str(self.observation_key).strip():
            raise UQProblemError("quantified prediction requires observation_key")
        if not isinstance(self.mean, Quantity):
            raise UQProblemError("quantified prediction mean must be a Quantity")
        for label in ("epistemic_standard_uncertainty", "total_standard_uncertainty"):
            value = getattr(self, label)
            if not isinstance(value, Quantity):
                raise UQProblemError(f"{label} must be a Quantity")
            self.mean.require_compatible(value, context=label)
            if value.magnitude_in(self.mean.units) < 0.0:
                raise UQProblemError(f"{label} must be non-negative")
        for label in ("epistemic_interval", "total_interval"):
            value = getattr(self, label)
            if not isinstance(value, Uncertainty) or value.kind is not UncertaintyKind.INTERVAL:
                raise UQProblemError(f"{label} must be INTERVAL uncertainty")
            if value.lower is None or value.upper is None:
                raise UQProblemError(f"{label} is missing bounds")
            self.mean.require_compatible(value.lower, context=label)
            self.mean.require_compatible(value.upper, context=label)
        level = float(self.confidence_level)
        if not 0.0 < level < 1.0:
            raise UQProblemError("confidence_level must lie strictly between 0 and 1")
        object.__setattr__(self, "confidence_level", level)
        if not str(self.posterior_dataset_id).strip():
            raise UQProblemError("posterior_dataset_id must be non-empty")
        if not isinstance(self.twin, TwinReference):
            raise UQProblemError("quantified prediction requires TwinReference")
        if not isinstance(self.model, ModelReference):
            raise UQProblemError("quantified prediction requires ModelReference")
        if not str(self.source_ref).strip():
            raise UQProblemError("quantified prediction requires source_ref")
        if int(self.posterior_support_size) < 1:
            raise UQProblemError("posterior_support_size must be positive")

    @property
    def epistemic_variance(self) -> float:
        value = self.epistemic_standard_uncertainty.magnitude_in(self.mean.units)
        return value * value

    @property
    def total_variance(self) -> float:
        value = self.total_standard_uncertainty.magnitude_in(self.mean.units)
        return value * value

    def to_dict(self) -> dict[str, Any]:
        return {
            "observation_key": self.observation_key,
            "mean": self.mean.to_dict(),
            "epistemic_standard_uncertainty": self.epistemic_standard_uncertainty.to_dict(),
            "epistemic_interval": self.epistemic_interval.to_dict(),
            "total_standard_uncertainty": self.total_standard_uncertainty.to_dict(),
            "total_interval": self.total_interval.to_dict(),
            "confidence_level": self.confidence_level,
            "posterior_dataset_id": self.posterior_dataset_id,
            "twin": self.twin.to_dict(),
            "model": self.model.to_dict(),
            "source_ref": self.source_ref,
            "posterior_support_size": int(self.posterior_support_size),
        }


def _validate_posterior_table_binding(
    posterior: PosteriorGrid,
    table: AdmittedForwardTable,
) -> None:
    if posterior.parameter_names != table.parameter_names:
        raise UQProblemError("posterior and predictive table parameter names differ")
    if posterior.points.shape != table.points.shape or not np.array_equal(
        posterior.points, table.points
    ):
        raise UQProblemError("posterior and predictive table are not on identical parameter support")

    positive = posterior.weights > 0.0
    rejected_positive = positive & ~table.admissible_mask
    if np.any(rejected_positive):
        mass = float(np.sum(posterior.weights[rejected_positive]))
        raise UQProblemError(
            "predictive table rejects parameter support carrying posterior mass; "
            f"refusing silent renormalization (rejected mass={mass:.17g})"
        )


def _weighted_central_interval(
    values: np.ndarray,
    weights: np.ndarray,
    mass: float,
) -> tuple[float, float]:
    if not 0.0 < mass < 1.0:
        raise UQProblemError("credible mass must lie strictly between 0 and 1")
    order = np.argsort(values, kind="stable")
    sorted_values = values[order]
    cumulative = np.cumsum(weights[order])
    tail = (1.0 - mass) / 2.0
    lower_i = min(int(np.searchsorted(cumulative, tail, side="left")), len(order) - 1)
    upper_i = min(
        int(np.searchsorted(cumulative, 1.0 - tail, side="left")), len(order) - 1
    )
    return float(sorted_values[lower_i]), float(sorted_values[upper_i])


def _gaussian_mixture_cdf(
    x: float,
    means: np.ndarray,
    weights: np.ndarray,
    sigma: float,
) -> float:
    z = (float(x) - means) / float(sigma)
    return float(np.sum(weights * ndtr(z)))


def _gaussian_mixture_quantile(
    probability: float,
    means: np.ndarray,
    weights: np.ndarray,
    sigma: float,
) -> float:
    """Deterministic finite-Gaussian-mixture quantile by fixed bisection.

    Ninety-six iterations are deliberately fixed instead of using a wall-clock
    or stochastic stopping rule.  The initial bracket extends twelve declared
    observation sigmas beyond the finite component means.
    """
    probability = float(probability)
    if not 0.0 < probability < 1.0:
        raise UQProblemError("mixture quantile probability must lie in (0, 1)")
    if not math.isfinite(sigma) or sigma <= 0.0:
        raise UQProblemError("mixture sigma must be finite and positive")

    lower = float(np.min(means) - 12.0 * sigma)
    upper = float(np.max(means) + 12.0 * sigma)
    for _ in range(96):
        midpoint = (lower + upper) / 2.0
        if _gaussian_mixture_cdf(midpoint, means, weights, sigma) < probability:
            lower = midpoint
        else:
            upper = midpoint
    return (lower + upper) / 2.0


def posterior_predictive_uq(
    posterior: PosteriorGrid,
    predictive_table: AdmittedForwardTable,
    spec: PredictiveObservableSpec,
    *,
    twin: TwinReference,
    model: ModelReference,
    source_ref: str,
    credible_mass: float = 0.95,
) -> QuantifiedPredictiveResult:
    """Compute exact weighted posterior-predictive moments and intervals.

    The latent/epistemic interval is a weighted discrete central interval over
    admitted model means.  When ``observation_sigma`` is declared, the total
    interval is obtained from the exact finite Gaussian-mixture CDF via
    deterministic bisection; it is **not** approximated as Gaussian.
    """
    if not isinstance(posterior, PosteriorGrid):
        raise UQProblemError("posterior_predictive_uq requires PosteriorGrid")
    if not isinstance(predictive_table, AdmittedForwardTable):
        raise UQProblemError("posterior_predictive_uq requires AdmittedForwardTable")
    if not isinstance(spec, PredictiveObservableSpec):
        raise UQProblemError("posterior_predictive_uq requires PredictiveObservableSpec")
    if not isinstance(twin, TwinReference):
        raise UQProblemError("posterior_predictive_uq requires TwinReference")
    if not isinstance(model, ModelReference):
        raise UQProblemError("posterior_predictive_uq requires ModelReference")
    source_ref = str(source_ref).strip()
    if not source_ref:
        raise UQProblemError("source_ref must be non-empty")
    credible_mass = float(credible_mass)
    if not 0.0 < credible_mass < 1.0:
        raise UQProblemError("credible_mass must lie strictly between 0 and 1")

    _validate_posterior_table_binding(posterior, predictive_table)

    try:
        column = predictive_table.observation_keys.index(spec.observation_key)
    except ValueError as exc:
        raise UQProblemError(
            f"predictive table has no observable {spec.observation_key!r}"
        ) from exc

    values = np.asarray(predictive_table.values[:, column], dtype=np.float64)
    weights = np.asarray(posterior.weights, dtype=np.float64)
    positive = weights > 0.0
    values = values[positive]
    weights = weights[positive]
    weights = weights / float(np.sum(weights))

    if not np.all(np.isfinite(values)) or not np.all(np.isfinite(weights)):
        raise UQProblemError("posterior predictive support contains non-finite values")

    mean = float(np.sum(weights * values))
    centered = values - mean
    epistemic_variance = float(np.sum(weights * centered * centered))
    if epistemic_variance < 0.0 and abs(epistemic_variance) <= 1.0e-15:
        epistemic_variance = 0.0
    if not math.isfinite(epistemic_variance) or epistemic_variance < 0.0:
        raise UQProblemError("posterior predictive variance is invalid")
    epistemic_std = math.sqrt(epistemic_variance)
    epistemic_lower, epistemic_upper = _weighted_central_interval(
        values, weights, credible_mass
    )

    if spec.observation_sigma is None:
        total_variance = epistemic_variance
        total_std = epistemic_std
        total_lower, total_upper = epistemic_lower, epistemic_upper
        total_method = "weighted_posterior_predictive_discrete"
    else:
        sigma = spec.observation_sigma.magnitude_in(spec.unit)
        total_variance = epistemic_variance + sigma * sigma
        total_std = math.sqrt(total_variance)
        tail = (1.0 - credible_mass) / 2.0
        total_lower = _gaussian_mixture_quantile(tail, values, weights, sigma)
        total_upper = _gaussian_mixture_quantile(1.0 - tail, values, weights, sigma)
        total_method = "weighted_posterior_predictive_gaussian_mixture"

    confidence = credible_mass
    epistemic_interval = Uncertainty(
        kind=UncertaintyKind.INTERVAL,
        lower=Quantity(epistemic_lower, spec.unit),
        upper=Quantity(epistemic_upper, spec.unit),
        confidence_level=confidence,
        source=source_ref,
        method="weighted_posterior_predictive_discrete",
        notes="Parameter/posterior uncertainty only; excludes model discrepancy and observation noise.",
    )
    total_interval = Uncertainty(
        kind=UncertaintyKind.INTERVAL,
        lower=Quantity(total_lower, spec.unit),
        upper=Quantity(total_upper, spec.unit),
        confidence_level=confidence,
        source=source_ref,
        method=total_method,
        notes=(
            "Total predictive uncertainty from parameter posterior plus declared independent "
            "observation noise; excludes model discrepancy."
        ),
    )

    return QuantifiedPredictiveResult(
        observation_key=spec.observation_key,
        mean=Quantity(mean, spec.unit),
        epistemic_standard_uncertainty=Quantity(epistemic_std, spec.unit),
        epistemic_interval=epistemic_interval,
        total_standard_uncertainty=Quantity(total_std, spec.unit),
        total_interval=total_interval,
        confidence_level=confidence,
        posterior_dataset_id=posterior.dataset_id,
        twin=twin,
        model=model,
        source_ref=source_ref,
        posterior_support_size=int(np.count_nonzero(positive)),
    )
