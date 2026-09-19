from engcore.credibility.evidence_graph import *

def test_unknown_authority_refuses_default_graph_policy():
    graph=EvidenceGraph((EvidenceNode("a",EvidenceAuthority.UNKNOWN,"a"*64,"web"),))
    assert not assess_graph(graph).admissible
