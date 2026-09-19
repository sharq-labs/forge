from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .estimate import ModelFormEstimate
from .policy import ModelFormPolicy
from .promotion import PromotionDecision, assess_promotion
from .qualification import ProducerQualification


class AuthorityDecision(str,Enum):
    AUTHORIZED="authorized"
    REFUSED="refused"


@dataclass(frozen=True)
class AuthorityReport:
    decision:AuthorityDecision
    reasons:tuple[str,...]


def authorize_model_form(
    estimate:ModelFormEstimate,
    qualification:ProducerQualification,
    policy:ModelFormPolicy=ModelFormPolicy(),
)->AuthorityReport:
    reasons=list(assess_promotion(estimate,policy).reasons)
    if not qualification.approves(estimate.quantity):
        reasons.append(f"producer is not qualified for quantity {estimate.quantity!r}")
    if qualification.validation_digest == qualification.independent_review_digest:
        reasons.append("producer validation and independent review evidence must be distinct")
    return AuthorityReport(
        AuthorityDecision.REFUSED if reasons else AuthorityDecision.AUTHORIZED,
        tuple(reasons),
    )
