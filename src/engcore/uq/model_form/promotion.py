from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .estimate import ModelFormEstimate, ModelFormStatus
from .policy import ModelFormPolicy


class PromotionDecision(str,Enum):
    PROMOTABLE="promotable"
    REFUSED="refused"


@dataclass(frozen=True)
class PromotionReport:
    decision:PromotionDecision
    reasons:tuple[str,...]


def assess_promotion(estimate:ModelFormEstimate,policy:ModelFormPolicy)->PromotionReport:
    reasons=[]
    if estimate.status is not ModelFormStatus.VALIDATED:
        reasons.append(f"estimate status is {estimate.status.value}, not validated")
    if estimate.standard_uncertainty is None or estimate.standard_uncertainty<=0:
        reasons.append("positive model-form uncertainty was not established")
    if len(estimate.validation_groups)<policy.minimum_validation_groups:
        reasons.append("insufficient independent validation groups")
    if estimate.empirical_holdout_coverage is None or estimate.empirical_holdout_coverage<policy.minimum_holdout_coverage:
        reasons.append("holdout coverage does not meet policy")
    return PromotionReport(PromotionDecision.REFUSED if reasons else PromotionDecision.PROMOTABLE,tuple(reasons))
