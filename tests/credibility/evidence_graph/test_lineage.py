import pytest
from engcore.credibility.evidence_graph import *
from engcore.scientific.errors import InvalidScientificProblem

def node(i): return EvidenceNode(i,EvidenceAuthority.MEASUREMENT,i[0]*64,"lab")

def test_derived_from_cycle_is_refused():
    nodes=(node("a"),node("b"),node("c"))
    edges=(
        EvidenceEdge("a","b",EvidenceRelation.DERIVED_FROM),
        EvidenceEdge("b","c",EvidenceRelation.DERIVED_FROM),
        EvidenceEdge("c","a",EvidenceRelation.DERIVED_FROM),
    )
    with pytest.raises(InvalidScientificProblem,match="cycle"):
        EvidenceGraph(nodes,edges)

def test_duplicate_evidence_edge_is_refused():
    nodes=(node("a"),node("b"))
    edge=EvidenceEdge("a","b",EvidenceRelation.SUPPORTS)
    with pytest.raises(InvalidScientificProblem,match="duplicate edges"):
        EvidenceGraph(nodes,(edge,edge))
