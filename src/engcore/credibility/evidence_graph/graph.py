from __future__ import annotations

from dataclasses import dataclass

from ...scientific.errors import InvalidScientificProblem
from .edge import EvidenceEdge
from .node import EvidenceNode


@dataclass(frozen=True)
class EvidenceGraph:
    nodes: tuple[EvidenceNode,...]
    edges: tuple[EvidenceEdge,...]=()

    def __post_init__(self)->None:
        object.__setattr__(self,"nodes",tuple(self.nodes))
        object.__setattr__(self,"edges",tuple(self.edges))
        if any(not isinstance(n,EvidenceNode) for n in self.nodes):
            raise InvalidScientificProblem("evidence graph nodes must be EvidenceNode")
        if any(not isinstance(e,EvidenceEdge) for e in self.edges):
            raise InvalidScientificProblem("evidence graph edges must be EvidenceEdge")
        ids=[n.evidence_id for n in self.nodes]
        if len(ids)!=len(set(ids)):
            raise InvalidScientificProblem("evidence graph contains duplicate node ids")
        known=set(ids)
        dangling=[(e.source_id,e.target_id) for e in self.edges
                  if e.source_id not in known or e.target_id not in known]
        if dangling:
            raise InvalidScientificProblem(f"evidence graph contains dangling edges {dangling}")

    def node(self,evidence_id:str)->EvidenceNode:
        for node in self.nodes:
            if node.evidence_id==evidence_id:
                return node
        raise KeyError(evidence_id)
