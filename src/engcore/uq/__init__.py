"""Shared quantified-uncertainty capabilities.

K3 pulls posterior-predictive uncertainty from admitted posterior support and
admitted forward predictions. K3.1 adds explicit, auditable conditioning on the
predictive-admitted event when unsupported posterior mass is within a declared
study budget.
"""

from .admission import (
    ConditionedPosterior,
    PredictiveAdmissionAudit,
    condition_posterior_on_predictive_admission,
)
from .predictive import (
    PredictiveObservableSpec,
    QuantifiedPredictiveResult,
    UQProblemError,
    posterior_predictive_uq,
)

__all__ = [
    "ConditionedPosterior",
    "PredictiveAdmissionAudit",
    "condition_posterior_on_predictive_admission",
    "PredictiveObservableSpec",
    "QuantifiedPredictiveResult",
    "UQProblemError",
    "posterior_predictive_uq",
]
