from engcore.credibility.evidence_graph import *

def test_support_and_contradict_same_edge_is_conflict():
    nodes=(EvidenceNode("a",EvidenceAuthority.MEASUREMENT,"a"*64,"lab"),EvidenceNode("b",EvidenceAuthority.ANALYTICAL,"b"*64,"calc"))
    graph=EvidenceGraph(nodes,(EvidenceEdge("a","b",EvidenceRelation.SUPPORTS),EvidenceEdge("a","b",EvidenceRelation.CONTRADICTS)))
    assert detect_direct_conflict(graph)
