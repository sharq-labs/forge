from __future__ import annotations

from enum import Enum
from .comparison import RouteComparison
from .independence import IndependenceEvidence, IndependenceLevel


class VerificationDecision(str,Enum):
    VERIFIED="verified"
    DISAGREEMENT="disagreement"
    INSUFFICIENT_INDEPENDENCE="insufficient_independence"
    NO_VERIFICATION="no_verification"


def adjudicate(comparisons:tuple[RouteComparison,...],independence:tuple[IndependenceEvidence,...])->VerificationDecision:
    if not comparisons:
        return VerificationDecision.NO_VERIFICATION
    if any(not item.agreement for item in comparisons):
        return VerificationDecision.DISAGREEMENT
    evidence_by_pair={}
    for item in independence:
        if item.pair in evidence_by_pair:
            return VerificationDecision.INSUFFICIENT_INDEPENDENCE
        evidence_by_pair[item.pair]=item
    for comparison in comparisons:
        evidence=evidence_by_pair.get((comparison.primary_route_id,comparison.verification_route_id))
        if evidence is None or evidence.level in {IndependenceLevel.NONE,IndependenceLevel.PARTIAL}:
            return VerificationDecision.INSUFFICIENT_INDEPENDENCE
    return VerificationDecision.VERIFIED
