from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .claim import KnowledgeClaim
from .conflicts import KnowledgeConflict, KnowledgeConflictStatus, compare_claims


class KnowledgeSetStatus(str, Enum):
    EMPTY = "empty"
    CONSISTENT = "consistent"
    OVERLAPPING = "overlapping"
    CONFLICTING = "conflicting"
    INCOMPARABLE = "incomparable"


@dataclass(frozen=True)
class KnowledgeSetAssessment:
    status: KnowledgeSetStatus
    claims: tuple[KnowledgeClaim, ...]
    pairwise: tuple[KnowledgeConflict, ...]

    @property
    def resolved(self) -> bool:
        return self.status in {
            KnowledgeSetStatus.CONSISTENT,
            KnowledgeSetStatus.OVERLAPPING,
        }


def assess_knowledge_set(
    claims: tuple[KnowledgeClaim, ...],
) -> KnowledgeSetAssessment:
    claims = tuple(claims)
    if not claims:
        return KnowledgeSetAssessment(KnowledgeSetStatus.EMPTY, (), ())
    pairwise = []
    for i, left in enumerate(claims):
        for right in claims[i + 1 :]:
            pairwise.append(compare_claims(left, right))
    pairwise_t = tuple(pairwise)
    statuses = {item.status for item in pairwise_t}
    if KnowledgeConflictStatus.DISAGREEMENT in statuses:
        status = KnowledgeSetStatus.CONFLICTING
    elif KnowledgeConflictStatus.INCOMPARABLE in statuses:
        status = KnowledgeSetStatus.INCOMPARABLE
    elif KnowledgeConflictStatus.OVERLAPPING_INTERVALS in statuses:
        status = KnowledgeSetStatus.OVERLAPPING
    else:
        status = KnowledgeSetStatus.CONSISTENT
    return KnowledgeSetAssessment(status, claims, pairwise_t)
