import pytest
from engcore.credibility.evidence_graph import *
from engcore.scientific.errors import InvalidScientificProblem

def node(i): return EvidenceNode(i,EvidenceAuthority.MEASUREMENT,"a"*64,"lab")

def test_dangling_edges_are_refused():
    with pytest.raises(InvalidScientificProblem):
        EvidenceGraph((node("a"),),(EvidenceEdge("a","missing",EvidenceRelation.SUPPORTS),))
