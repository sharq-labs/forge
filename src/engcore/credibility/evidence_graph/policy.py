from __future__ import annotations

from dataclasses import dataclass

from .conflict import detect_direct_conflict
from .graph import EvidenceGraph
from .node import EvidenceAuthority


@dataclass(frozen=True)
class EvidenceGraphPolicy:
    refuse_conflicts: bool=True
    require_known_authority: bool=True


@dataclass(frozen=True)
class EvidenceGraphAssessment:
    admissible: bool
    problems: tuple[str,...]


def assess_graph(graph:EvidenceGraph,policy:EvidenceGraphPolicy=EvidenceGraphPolicy())->EvidenceGraphAssessment:
    problems=[]
    if policy.refuse_conflicts and detect_direct_conflict(graph):
        problems.append("direct evidence conflict")
    if policy.require_known_authority and any(n.authority is EvidenceAuthority.UNKNOWN for n in graph.nodes):
        problems.append("unknown evidence authority")
    return EvidenceGraphAssessment(not problems,tuple(problems))
