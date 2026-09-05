"""Shared model-adequacy math pulled by K4.

Adequacy is evaluated against observations that were not used to fit the
posterior.  The scored path keeps the exact finite Gaussian-mixture predictive
distribution: no Gaussian approximation replaces its CDF or log density.

The result is deliberately study-bounded evidence.  It does not mutate a
model's global validation status or convert predictive support into a truth
probability.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np
from scipy.special import logsumexp, ndtr

from ..inference import AdmittedForwardTable, PosteriorGrid
from ..scientific.ir.problem import ModelReference
from ..scientific.twins import TwinReference
from ..scientific.units.quantity import Quantity
from ..uq import PredictiveObservableSpec, posterior_predictive_uq
from ..uq.predictive import UQProblemError


class ModelAdequacyError(ValueError):
    """Raised when an adequacy/comparison request is scientifically invalid."""


class StudyAdequacyStatus(str):
    ADEQUATE_FOR_DECLARED_STUDY = "adequate_for_declared_study"
    INADEQUATE_FOR_DECLARED_STUDY = "inadequate_for_declared_study"
    INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True)
class PredictiveObservationAssessment:
    observation_key: str
    observed: Quantity
    predictive_mean: Quantity
    total_standard_uncertainty: Quantity
    standardized_residual: float
    predictive_cdf: float
    two_sided_tail_probability: float
    log_predictive_density: float
    covered_by_central_interval: bool
    confidence_level: float
    posterior_dataset_id: str
    twin: TwinReference
    model: ModelReference
    source_ref: str

    def __post_init__(self) -> None:
        if not str(self.observation_key).strip():
            raise ModelAdequacyError("adequacy assessment requires observation_key")
        for value in (self.observed, self.predictive_mean, self.total_standard_uncertainty):
            if not isinstance(value, Quantity):
                raise ModelAdequacyError("adequacy quantities must be Quantity")
        self.predictive_mean.require_compatible(self.observed, context="adequacy observation")
        self.predictive_mean.require_compatible(
            self.total_standard_uncertainty, context="adequacy predictive uncertainty"
        )
        for label in (
            "standardized_residual",
            "predictive_cdf",
            "two_sided_tail_probability",
            "log_predictive_density",
        ):
            value = float(getattr(self, label))
            if not math.isfinite(value):
                raise ModelAdequacyError(f"{label} must be finite")
            object.__setattr__(self, label, value)
        if not 0.0 <= self.predictive_cdf <= 1.0:
            raise ModelAdequacyError("predictive_cdf must lie in [0, 1]")
        if not 0.0 <= self.two_sided_tail_probability <= 1.0:
            raise ModelAdequacyError("two_sided_tail_probability must lie in [0, 1]")
        level = float(self.confidence_level)
        if not 0.0 < level < 1.0:
            raise ModelAdequacyError("confidence_level must lie in (0, 1)")
        object.__setattr__(self, "confidence_level", level)
        if not str(self.posterior_dataset_id).strip() or not str(self.source_ref).strip():
            raise ModelAdequacyError("adequacy assessment requires dataset/source binding")
        if not isinstance(self.twin, TwinReference) or not isinstance(self.model, ModelReference):
            raise ModelAdequacyError("adequacy assessment requires TwinReference and ModelReference")

    def to_dict(self) -> dict[str, Any]:
        return {
            "observation_key": self.observation_key,
            "observed": self.observed.to_dict(),
            "predictive_mean": self.predictive_mean.to_dict(),
            "total_standard_uncertainty": self.total_standard_uncertainty.to_dict(),
            "standardized_residual": self.standardized_residual,
            "predictive_cdf": self.predictive_cdf,
            "two_sided_tail_probability": self.two_sided_tail_probability,
            "log_predictive_density": self.log_predictive_density,
            "covered_by_central_interval": bool(self.covered_by_central_interval),
            "confidence_level": self.confidence_level,
            "posterior_dataset_id": self.posterior_dataset_id,
            "twin": self.twin.to_dict(),
            "model": self.model.to_dict(),
            "source_ref": self.source_ref,
        }


@dataclass(frozen=True)
class ModelScoreComparison:
    model_a: ModelReference
    model_b: ModelReference
    score_a: float
    score_b: float
    delta_a_minus_b: float
    preferred_model: ModelReference | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_a": self.model_a.to_dict(),
            "model_b": self.model_b.to_dict(),
            "score_a": self.score_a,
            "score_b": self.score_b,
            "delta_a_minus_b": self.delta_a_minus_b,
            "preferred_model": self.preferred_model.to_dict() if self.preferred_model else None,
        }


def assess_predictive_observation(
    posterior: PosteriorGrid,
    predictive_table: AdmittedForwardTable,
    spec: PredictiveObservableSpec,
    observed: Quantity,
    *,
    twin: TwinReference,
    model: ModelReference,
    source_ref: str,
    credible_mass: float = 0.95,
) -> PredictiveObservationAssessment:
    """Score one held-out observation against an exact predictive mixture."""

    if spec.observation_sigma is None:
        raise ModelAdequacyError(
            "predictive adequacy requires declared observation noise; latent-only "
            "uncertainty has no observational likelihood"
        )
    if not isinstance(observed, Quantity):
        raise ModelAdequacyError("held-out observation must be Quantity")
    try:
        observed.require_compatible(Quantity(1.0, spec.unit), context="held-out observation")
        predictive = posterior_predictive_uq(
            posterior,
            predictive_table,
            spec,
            twin=twin,
            model=model,
            source_ref=source_ref,
            credible_mass=credible_mass,
        )
    except UQProblemError as exc:
        raise ModelAdequacyError(str(exc)) from exc

    try:
        column = predictive_table.observation_keys.index(spec.observation_key)
    except ValueError as exc:
        raise ModelAdequacyError(
            f"predictive table has no observable {spec.observation_key!r}"
        ) from exc

    weights = np.asarray(posterior.weights, dtype=np.float64)
    positive = weights > 0.0
    if not np.any(positive):
        raise ModelAdequacyError("posterior has no positive predictive mass")
    means = np.asarray(predictive_table.values[:, column], dtype=np.float64)[positive]
    weights = weights[positive]
    weights = weights / float(np.sum(weights, dtype=np.float64))

    sigma = float(spec.observation_sigma.magnitude_in(spec.unit))
    y = float(observed.magnitude_in(spec.unit))
    if not math.isfinite(sigma) or sigma <= 0.0:
        raise ModelAdequacyError("observation sigma must be finite and positive")
    if not math.isfinite(y) or not np.all(np.isfinite(means)):
        raise ModelAdequacyError("predictive adequacy received non-finite support/observation")

    z_components = (y - means) / sigma
    cdf = float(np.sum(weights * ndtr(z_components)))
    cdf = min(max(cdf, 0.0), 1.0)
    tail = 2.0 * min(cdf, 1.0 - cdf)

    log_components = (
        np.log(weights)
        - 0.5 * z_components * z_components
        - math.log(sigma)
        - 0.5 * math.log(2.0 * math.pi)
    )
    log_density = float(logsumexp(log_components))

    unit = predictive.mean.units
    total_std = predictive.total_standard_uncertainty.magnitude_in(unit)
    if total_std <= 0.0:
        raise ModelAdequacyError("total predictive standard uncertainty must be positive")
    standardized = (
        observed.magnitude_in(unit) - predictive.mean.magnitude_in(unit)
    ) / total_std

    interval = predictive.total_interval
    if interval.lower is None or interval.upper is None:
        raise ModelAdequacyError("total predictive interval is missing bounds")
    value = observed.magnitude_in(unit)
    covered = (
        interval.lower.magnitude_in(unit) <= value <= interval.upper.magnitude_in(unit)
    )

    return PredictiveObservationAssessment(
        observation_key=spec.observation_key,
        observed=observed.to(spec.unit),
        predictive_mean=predictive.mean,
        total_standard_uncertainty=predictive.total_standard_uncertainty,
        standardized_residual=float(standardized),
        predictive_cdf=cdf,
        two_sided_tail_probability=tail,
        log_predictive_density=log_density,
        covered_by_central_interval=covered,
        confidence_level=float(credible_mass),
        posterior_dataset_id=posterior.dataset_id,
        twin=twin,
        model=model,
        source_ref=str(source_ref).strip(),
    )


def compare_log_predictive_scores(
    model_a: ModelReference,
    assessments_a: Sequence[PredictiveObservationAssessment],
    model_b: ModelReference,
    assessments_b: Sequence[PredictiveObservationAssessment],
) -> ModelScoreComparison:
    """Compare paired out-of-sample log predictive scores.

    A positive delta favors ``model_a``.  The function does not convert score
    differences into model probabilities.
    """

    a = tuple(assessments_a)
    b = tuple(assessments_b)
    if not a or not b or len(a) != len(b):
        raise ModelAdequacyError("model comparison requires equally sized non-empty assessments")
    keys_a = tuple(item.observation_key for item in a)
    keys_b = tuple(item.observation_key for item in b)
    if keys_a != keys_b:
        raise ModelAdequacyError("model comparison observation order/keys differ")
    if any(item.model != model_a for item in a):
        raise ModelAdequacyError("model_a assessments carry a different ModelReference")
    if any(item.model != model_b for item in b):
        raise ModelAdequacyError("model_b assessments carry a different ModelReference")

    score_a = float(sum(item.log_predictive_density for item in a))
    score_b = float(sum(item.log_predictive_density for item in b))
    if not math.isfinite(score_a) or not math.isfinite(score_b):
        raise ModelAdequacyError("model comparison score is non-finite")
    delta = score_a - score_b
    preferred = model_a if delta > 0.0 else model_b if delta < 0.0 else None
    return ModelScoreComparison(model_a, model_b, score_a, score_b, delta, preferred)
