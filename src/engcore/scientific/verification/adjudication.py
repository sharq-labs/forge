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
    if not independence or all(item.level in {IndependenceLevel.NONE,IndependenceLevel.PARTIAL} for item in independence):
        return VerificationDecision.INSUFFICIENT_INDEPENDENCE
    return VerificationDecision.VERIFIED
