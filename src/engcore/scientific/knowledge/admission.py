from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from ..errors import InvalidScientificProblem
from .claim import KnowledgeClaim
from .freshness import FreshnessPolicy,KnowledgeFreshness
from .snapshot import KnowledgeSnapshot
from .trust import SourceStanding,TrustedSourceRegistry


class KnowledgeAdmissionStatus(str,Enum):
    ADMISSIBLE="admissible"
    UNTRUSTED_SOURCE="untrusted_source"
    STALE_SOURCE="stale_source"
    UNKNOWN_FRESHNESS="unknown_freshness"
    CONTEXT_MISMATCH="context_mismatch"


@dataclass(frozen=True)
class KnowledgeAdmission:
    claim_id:str
    status:KnowledgeAdmissionStatus
    source_standing:SourceStanding
    freshness:KnowledgeFreshness
    reasons:tuple[str,...]
    @property
    def admissible(self)->bool: return self.status is KnowledgeAdmissionStatus.ADMISSIBLE


def admit_claim(snapshot:KnowledgeSnapshot,claim_id:str,registry:TrustedSourceRegistry,
                freshness_policy:FreshnessPolicy,*,now:datetime,target_context_digest:str)->KnowledgeAdmission:
    claim=next((c for c in snapshot.claims if c.claim_id==claim_id),None)
    if claim is None:
        raise InvalidScientificProblem(f"knowledge snapshot has no claim {claim_id!r}")
    source=next((s for s in snapshot.sources if s.source_id==claim.source_id),None)
    if source is None:
        raise InvalidScientificProblem(
            f"knowledge claim {claim.claim_id!r} references source absent from snapshot"
        )
    trust=registry.assess(source);freshness=freshness_policy.assess(source,now=now);reasons=[]
    if not trust.trusted: reasons.append(trust.reason)
    if freshness is KnowledgeFreshness.STALE: reasons.append("source is stale under declared freshness policy")
    if freshness is KnowledgeFreshness.UNKNOWN and freshness_policy.require_timestamp: reasons.append("source freshness is unknown")
    if claim.applicability_context_digest!=target_context_digest: reasons.append("knowledge claim context differs from target context")
    if not trust.trusted: status=KnowledgeAdmissionStatus.UNTRUSTED_SOURCE
    elif freshness is KnowledgeFreshness.STALE: status=KnowledgeAdmissionStatus.STALE_SOURCE
    elif freshness is KnowledgeFreshness.UNKNOWN and freshness_policy.require_timestamp: status=KnowledgeAdmissionStatus.UNKNOWN_FRESHNESS
    elif claim.applicability_context_digest!=target_context_digest: status=KnowledgeAdmissionStatus.CONTEXT_MISMATCH
    else: status=KnowledgeAdmissionStatus.ADMISSIBLE
    return KnowledgeAdmission(claim.claim_id,status,trust.standing,freshness,tuple(reasons))
