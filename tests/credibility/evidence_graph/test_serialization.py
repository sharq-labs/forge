from engcore.credibility.evidence_graph import *
from engcore.credibility.evidence_graph.serialization import graph_from_dict, graph_to_dict

def test_graph_round_trip_revalidates_edges():
    graph=EvidenceGraph((EvidenceNode("a",EvidenceAuthority.MEASUREMENT,"a"*64,"lab"),))
    assert graph_from_dict(graph_to_dict(graph))==graph
