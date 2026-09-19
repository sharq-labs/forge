from __future__ import annotations
from enum import Enum
from ..certification_core import CertificationVerification
from ..validation_core import ValidationDecision, ValidationReport
from ..verification import VerificationDecision, VerificationReport

class AssuranceDecision(str,Enum):
    TRUSTED="trusted"
    REFUSED="refused"
    INCOMPLETE="incomplete"

def decide_assurance(validation:ValidationReport,verification:VerificationReport,certification:CertificationVerification)->AssuranceDecision:
    if validation.decision is ValidationDecision.INCOMPLETE or verification.decision in {VerificationDecision.NO_VERIFICATION,VerificationDecision.INSUFFICIENT_INDEPENDENCE}:
        return AssuranceDecision.INCOMPLETE
    if validation.decision is not ValidationDecision.ACCEPTED or verification.decision is not VerificationDecision.VERIFIED or not certification.verified:
        return AssuranceDecision.REFUSED
    return AssuranceDecision.TRUSTED
