from __future__ import annotations

from enum import Enum
from .graph import EvidenceGraph
from .edge import EvidenceRelation


class SupersessionDecision(str,Enum):
    ACTIVE="active"
    SUPERSEDED="superseded"


def assess_supersession(graph:EvidenceGraph,evidence_id:str)->SupersessionDecision:
    graph.node(evidence_id)
    for edge in graph.edges:
        if edge.relation is EvidenceRelation.SUPERSEDES and edge.target_id==evidence_id:
            return SupersessionDecision.SUPERSEDED
    return SupersessionDecision.ACTIVE
