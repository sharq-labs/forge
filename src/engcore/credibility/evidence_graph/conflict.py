from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .edge import EvidenceRelation
from .graph import EvidenceGraph


class ConflictKind(str,Enum):
    SUPPORT_AND_CONTRADICT="support_and_contradict"


@dataclass(frozen=True)
class EvidenceConflict:
    source_id: str
    target_id: str
    kind: ConflictKind


def detect_direct_conflict(graph:EvidenceGraph)->tuple[EvidenceConflict,...]:
    pairs={}
    for edge in graph.edges:
        key=(edge.source_id,edge.target_id)
        pairs.setdefault(key,set()).add(edge.relation)
    return tuple(
        EvidenceConflict(a,b,ConflictKind.SUPPORT_AND_CONTRADICT)
        for (a,b),relations in sorted(pairs.items())
        if EvidenceRelation.SUPPORTS in relations and EvidenceRelation.CONTRADICTS in relations
    )
