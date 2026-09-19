from __future__ import annotations
from dataclasses import dataclass

from ..certification_core import CertificationVerification
from ..validation_core import ValidationReport
from ..verification import VerificationReport

@dataclass(frozen=True)
class AssuranceSnapshot:
    validation:ValidationReport
    verification:VerificationReport
    certification:CertificationVerification
