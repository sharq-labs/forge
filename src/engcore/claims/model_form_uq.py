"""Adapter from claims held-out discrepancy evidence into scoped Core model-form UQ."""

from __future__ import annotations
from dataclasses import dataclass
from ..uq.model_form import (ModelFormEstimate,ModelFormPolicy,ModelFormScope,ModelFormStatus,ModelFormStudy,
    ModelResidualObservation,PromotionReport,assess_promotion,evaluate_model_form_study)
from .analysis.model_discrepancy import DiscrepancyEstimateStatus,ModelFormDiscrepancyEstimate
from .measurement_dataset import DatasetSplit

@dataclass(frozen=True)
class ModelFormPromotionAttempt:
    estimate:ModelFormEstimate
    promotion:PromotionReport

#: What a discrepancy protocol that stopped short of a validated candidate means for the model-form study.
_STOPPED={
    DiscrepancyEstimateStatus.INSUFFICIENT_DATA:ModelFormStatus.INSUFFICIENT_DATA,
    DiscrepancyEstimateStatus.INSUFFICIENT_UNCERTAINTY:ModelFormStatus.INSUFFICIENT_DATA,
    DiscrepancyEstimateStatus.CALIBRATED_UNVALIDATED:ModelFormStatus.CALIBRATED_UNVALIDATED,
    DiscrepancyEstimateStatus.FAILED_VALIDATION:ModelFormStatus.FAILED_HOLDOUT,
    DiscrepancyEstimateStatus.UNRESOLVED_BELOW_KNOWN_UNCERTAINTY:ModelFormStatus.UNRESOLVED,
}

def evaluate_discrepancy_for_model_form(discrepancy:ModelFormDiscrepancyEstimate,*,
        scope:ModelFormScope,policy:ModelFormPolicy=ModelFormPolicy())->ModelFormPromotionAttempt:
    """Only a discrepancy that passed its own held-out protocol reaches the model-form study.

    The protocol's verdict is not re-litigated by a second, looser test: a failed
    validation, an unknown point uncertainty or too little data stops here, and
    no point is dropped to make the rest pass.
    """
    if scope.quantity!=discrepancy.quantity:
        raise ValueError("discrepancy quantity does not match model-form scope")
    if discrepancy.status is not DiscrepancyEstimateStatus.VALIDATED_CANDIDATE:
        groups=lambda split:tuple(sorted({p.independence_group for p in discrepancy.points if p.split is split}))
        stopped=ModelFormEstimate(discrepancy.quantity,discrepancy.units,_STOPPED[discrepancy.status],None,
            groups(DatasetSplit.CALIBRATION),groups(DatasetSplit.VALIDATION),None,
            f"the discrepancy protocol stopped at {discrepancy.status.value}: {discrepancy.reason}",policy.estimator,scope)
        return ModelFormPromotionAttempt(stopped,assess_promotion(stopped,policy))
    observations=[]
    for point in discrepancy.points:
        if point.known_half_width is None:
            raise ValueError(f"validated discrepancy point {point.observation_id} has no known uncertainty; it cannot be dropped")
        observations.append(ModelResidualObservation(
            point.observation_id,point.independence_group,discrepancy.quantity,point.units,
            point.residual,float(point.known_half_width),point.split is DatasetSplit.VALIDATION))
    estimate=evaluate_model_form_study(ModelFormStudy(tuple(observations),policy,scope))
    return ModelFormPromotionAttempt(estimate,assess_promotion(estimate,policy))
