from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..results.uncertainty import UncertaintyKind
from .claim import KnowledgeClaim


class KnowledgeConflictStatus(str,Enum):
    SAME="same"
    OVERLAPPING_INTERVALS="overlapping_intervals"
    DISAGREEMENT="disagreement"
    INCOMPARABLE="incomparable"


@dataclass(frozen=True)
class KnowledgeConflict:
    left_claim_id:str
    right_claim_id:str
    status:KnowledgeConflictStatus
    reason:str


def compare_claims(left:KnowledgeClaim,right:KnowledgeClaim)->KnowledgeConflict:
    if (left.subject,left.quantity_name,left.applicability_context_digest)!=(right.subject,right.quantity_name,right.applicability_context_digest):
        return KnowledgeConflict(left.claim_id,right.claim_id,KnowledgeConflictStatus.INCOMPARABLE,"claims do not address the same subject/quantity/context")
    if left.numeric_value is None or right.numeric_value is None:
        status=KnowledgeConflictStatus.SAME if left.text_value==right.text_value else KnowledgeConflictStatus.DISAGREEMENT
        return KnowledgeConflict(left.claim_id,right.claim_id,status,"text values equal" if status is KnowledgeConflictStatus.SAME else "text values differ")
    try: rv=right.numeric_value.to(left.numeric_value.units)
    except Exception:
        return KnowledgeConflict(left.claim_id,right.claim_id,KnowledgeConflictStatus.INCOMPARABLE,"numeric values have incompatible dimensions")
    if rv.magnitude==left.numeric_value.magnitude:
        return KnowledgeConflict(left.claim_id,right.claim_id,KnowledgeConflictStatus.SAME,"numeric values equal")
    if (left.uncertainty is not None and right.uncertainty is not None and
        left.uncertainty.kind is UncertaintyKind.INTERVAL and right.uncertainty.kind is UncertaintyKind.INTERVAL):
        llo=left.uncertainty.lower.to(left.numeric_value.units).magnitude;lhi=left.uncertainty.upper.to(left.numeric_value.units).magnitude
        rlo=right.uncertainty.lower.to(left.numeric_value.units).magnitude;rhi=right.uncertainty.upper.to(left.numeric_value.units).magnitude
        if max(llo,rlo)<=min(lhi,rhi):
            return KnowledgeConflict(left.claim_id,right.claim_id,KnowledgeConflictStatus.OVERLAPPING_INTERVALS,"explicit uncertainty intervals overlap")
        return KnowledgeConflict(left.claim_id,right.claim_id,KnowledgeConflictStatus.DISAGREEMENT,"explicit uncertainty intervals do not overlap")
    return KnowledgeConflict(left.claim_id,right.claim_id,KnowledgeConflictStatus.INCOMPARABLE,
                             "values differ but explicit comparable uncertainty intervals are unavailable")
