"""Explicit posterior conditioning on predictive admission.

K3 discovered a boundary case that a posterior point can be scientifically
admissible at fitting conditions yet fail the numerical-admission gate at a new
predictive condition.  This module implements the separately preregistered K3.1
policy: measure unsupported posterior mass, fail closed above a declared budget,
and otherwise condition explicitly on the predictive-admitted event.

Nothing here fabricates a rejected prediction or weakens a domain gate.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from ..inference import AdmittedForwardTable, PosteriorGrid
from .predictive import UQProblemError


@dataclass(frozen=True)
class PredictiveAdmissionAudit:
    """Auditable record of conditioning a posterior on predictive admission."""

    posterior_dataset_id: str
    maximum_unsupported_mass: float
    supported_mass: float
    unsupported_mass: float
    conditioning_factor: float
    rejected_point_count: int
    rejected_point_indices: tuple[int, ...]
    positive_weight_rejected_point_count: int
    positive_weight_rejected_point_indices: tuple[int, ...]
    rejection_reasons: tuple[str, ...]
    conditional_on_predictive_admission: bool

    def __post_init__(self) -> None:
        for label in (
            "maximum_unsupported_mass",
            "supported_mass",
            "unsupported_mass",
            "conditioning_factor",
        ):
            value = float(getattr(self, label))
            if not math.isfinite(value):
                raise UQProblemError(f"{label} must be finite")
            object.__setattr__(self, label, value)
        if self.maximum_unsupported_mass < 0.0:
            raise UQProblemError("maximum_unsupported_mass cannot be negative")
        if not 0.0 <= self.supported_mass <= 1.0 + 1.0e-12:
            raise UQProblemError("supported_mass is outside probability bounds")
        if not 0.0 <= self.unsupported_mass <= 1.0 + 1.0e-12:
            raise UQProblemError("unsupported_mass is outside probability bounds")
        # Direct float64 summation of an already-normalized posterior can place
        # supported_mass a final bit above one (for example
        # 1.0000000000000002).  Then the mathematically expected factor >= 1
        # is represented as 0.9999999999999998.  The same 1e-12 accounting
        # tolerance used by the K3.1 preregistration admits this rounding dust;
        # materially sub-unit factors still fail closed.
        if self.conditioning_factor < 1.0 - 1.0e-12:
            raise UQProblemError(
                "conditioning_factor is materially below one beyond probability-accounting tolerance"
            )
        if len(self.rejected_point_indices) != len(self.rejection_reasons):
            raise UQProblemError("rejected-point indices/reasons length mismatch")
        if int(self.rejected_point_count) != len(self.rejected_point_indices):
            raise UQProblemError("rejected_point_count is inconsistent")
        if int(self.positive_weight_rejected_point_count) != len(
            self.positive_weight_rejected_point_indices
        ):
            raise UQProblemError("positive-weight rejected-point count is inconsistent")

    def to_dict(self) -> dict[str, Any]:
        return {
            "posterior_dataset_id": self.posterior_dataset_id,
            "maximum_unsupported_mass": self.maximum_unsupported_mass,
            "supported_mass": self.supported_mass,
            "unsupported_mass": self.unsupported_mass,
            "conditioning_factor": self.conditioning_factor,
            "rejected_point_count": int(self.rejected_point_count),
            "rejected_point_indices": list(self.rejected_point_indices),
            "positive_weight_rejected_point_count": int(
                self.positive_weight_rejected_point_count
            ),
            "positive_weight_rejected_point_indices": list(
                self.positive_weight_rejected_point_indices
            ),
            "rejection_reasons": list(self.rejection_reasons),
            "conditional_on_predictive_admission": bool(
                self.conditional_on_predictive_admission
            ),
        }


@dataclass(frozen=True)
class ConditionedPosterior:
    """Posterior plus the evidence record authorizing its predictive use."""

    posterior: PosteriorGrid
    audit: PredictiveAdmissionAudit


def _validate_binding(posterior: PosteriorGrid, table: AdmittedForwardTable) -> None:
    if not isinstance(posterior, PosteriorGrid):
        raise UQProblemError("predictive admission requires PosteriorGrid")
    if not isinstance(table, AdmittedForwardTable):
        raise UQProblemError("predictive admission requires AdmittedForwardTable")
    if posterior.parameter_names != table.parameter_names:
        raise UQProblemError("posterior and predictive table parameter names differ")
    if posterior.points.shape != table.points.shape or not np.array_equal(
        posterior.points, table.points
    ):
        raise UQProblemError(
            "posterior and predictive table are not on identical parameter support"
        )


def condition_posterior_on_predictive_admission(
    posterior: PosteriorGrid,
    predictive_table: AdmittedForwardTable,
    *,
    maximum_unsupported_mass: float,
) -> ConditionedPosterior:
    """Condition explicitly on predictive admission or fail closed.

    ``unsupported_mass`` is computed by direct summation of stored posterior
    weights at rejected predictive points, exactly as preregistered.  A non-zero
    mass is never described as zero; when it is within the declared budget the
    returned posterior has rejected weights set to zero and admitted weights
    divided by the measured supported mass.
    """

    _validate_binding(posterior, predictive_table)
    budget = float(maximum_unsupported_mass)
    if not math.isfinite(budget) or budget < 0.0:
        raise UQProblemError("maximum_unsupported_mass must be finite and non-negative")

    weights = np.asarray(posterior.weights, dtype=np.float64)
    admitted = np.asarray(predictive_table.admissible_mask, dtype=bool)
    rejected = ~admitted

    unsupported_mass = float(np.sum(weights[rejected], dtype=np.float64))
    supported_mass = float(np.sum(weights[admitted], dtype=np.float64))
    total = supported_mass + unsupported_mass
    if not math.isfinite(total) or abs(total - 1.0) > 1.0e-12:
        raise UQProblemError(
            "predictive support accounting does not sum to one within 1e-12: "
            f"supported={supported_mass:.17g}, unsupported={unsupported_mass:.17g}"
        )
    if unsupported_mass > budget:
        raise UQProblemError(
            "unsupported predictive posterior mass exceeds declared budget: "
            f"mass={unsupported_mass:.17g}, budget={budget:.17g}"
        )
    if supported_mass <= 0.0:
        raise UQProblemError("no posterior mass remains on predictive-admitted support")

    rejected_indices = tuple(int(i) for i in np.flatnonzero(rejected))
    positive_rejected = rejected & (weights > 0.0)
    positive_rejected_indices = tuple(
        int(i) for i in np.flatnonzero(positive_rejected)
    )
    reasons = tuple(
        str(predictive_table.rejection_reasons[i]) for i in rejected_indices
    )

    if unsupported_mass == 0.0:
        conditioned = posterior
        factor = 1.0
    else:
        conditioned_weights = np.array(weights, copy=True)
        conditioned_weights[rejected] = 0.0
        conditioned_weights[admitted] = conditioned_weights[admitted] / supported_mass
        # Last-bit normalization keeps PosteriorGrid's strict sum contract while
        # preserving the explicit conditioning factor in the audit record.
        conditioned_weights = conditioned_weights / float(
            np.sum(conditioned_weights, dtype=np.float64)
        )
        conditioned = PosteriorGrid(
            parameter_names=posterior.parameter_names,
            points=posterior.points,
            weights=conditioned_weights,
            log_likelihood=posterior.log_likelihood,
            admissible_mask=posterior.admissible_mask,
            dataset_id=posterior.dataset_id,
        )
        factor = 1.0 / supported_mass

    audit = PredictiveAdmissionAudit(
        posterior_dataset_id=posterior.dataset_id,
        maximum_unsupported_mass=budget,
        supported_mass=supported_mass,
        unsupported_mass=unsupported_mass,
        conditioning_factor=factor,
        rejected_point_count=len(rejected_indices),
        rejected_point_indices=rejected_indices,
        positive_weight_rejected_point_count=len(positive_rejected_indices),
        positive_weight_rejected_point_indices=positive_rejected_indices,
        rejection_reasons=reasons,
        conditional_on_predictive_admission=unsupported_mass > 0.0,
    )
    return ConditionedPosterior(posterior=conditioned, audit=audit)
