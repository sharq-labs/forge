from __future__ import annotations

from dataclasses import dataclass

from .conflict import detect_direct_conflict
from .graph import EvidenceGraph
from .node import EvidenceAuthority


@dataclass(frozen=True)
class EvidenceGraphPolicy:
    refuse_conflicts: bool=True
    require_known_authority: bool=True
    require_provenance: bool=False
    require_trusted_provenance: bool=False
    require_fresh_provenance: bool=False


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
    if policy.require_provenance and any(n.provenance is None for n in graph.nodes):
        problems.append("missing evidence provenance")
    if policy.require_trusted_provenance and any(
        n.provenance is None or not n.provenance.trusted for n in graph.nodes
    ):
        problems.append("evidence provenance is not pinned/trusted")
    if policy.require_fresh_provenance and any(
        n.provenance is None or not n.provenance.fresh_enough for n in graph.nodes
    ):
        problems.append("evidence provenance is stale or freshness is unknown")
    return EvidenceGraphAssessment(not problems,tuple(problems))
