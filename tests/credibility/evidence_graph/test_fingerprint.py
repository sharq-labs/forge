from engcore.credibility.evidence_graph import *

def test_graph_fingerprint_is_order_independent():
    a=EvidenceNode("a",EvidenceAuthority.MEASUREMENT,"a"*64,"lab"); b=EvidenceNode("b",EvidenceAuthority.ANALYTICAL,"b"*64,"calc")
    assert evidence_graph_fingerprint(EvidenceGraph((a,b)))==evidence_graph_fingerprint(EvidenceGraph((b,a)))
