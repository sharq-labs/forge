from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from .estimate import ModelFormEstimate
from .policy import ModelFormPolicy
from .promotion import assess_promotion
from .qualification import ProducerQualification
from .scope import ModelFormScope

class AuthorityDecision(str,Enum):
    AUTHORIZED="authorized"
    REFUSED="refused"

@dataclass(frozen=True)
class AuthorityReport:
    decision:AuthorityDecision
    reasons:tuple[str,...]

def authorize_model_form(estimate:ModelFormEstimate,qualification:ProducerQualification,
                         target_scope:ModelFormScope,
                         policy:ModelFormPolicy=ModelFormPolicy())->AuthorityReport:
    reasons=list(assess_promotion(estimate,policy).reasons)
    if estimate.scope is None or estimate.scope!=target_scope: reasons.append("model-form estimate scope does not match the target model/context/dataset")
    if not qualification.approves(estimate.quantity,estimate.estimator_method): reasons.append("producer is not qualified for this quantity/estimator")
    if qualification.producer_id==qualification.independent_reviewer_id: reasons.append("producer and independent reviewer identities must differ")
    if qualification.validation_digest==qualification.independent_review_digest: reasons.append("producer validation and independent review evidence must be distinct")
    return AuthorityReport(AuthorityDecision.REFUSED if reasons else AuthorityDecision.AUTHORIZED,tuple(reasons))
