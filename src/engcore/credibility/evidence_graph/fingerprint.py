from __future__ import annotations

import hashlib, json
from .graph import EvidenceGraph


def evidence_graph_fingerprint(graph:EvidenceGraph)->str:
    payload={
        "nodes":[n.to_dict() for n in sorted(graph.nodes,key=lambda n:n.evidence_id)],
        "edges":[e.to_dict() for e in sorted(graph.edges,key=lambda e:(e.source_id,e.target_id,e.relation.value))],
    }
    return hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(",",":")).encode()).hexdigest()
