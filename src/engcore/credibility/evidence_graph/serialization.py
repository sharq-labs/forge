from __future__ import annotations

from typing import Any, Mapping

from ...scientific.serialization import require_schema, schema_string
from .edge import EvidenceEdge
from .graph import EvidenceGraph
from .node import EvidenceNode

EVIDENCE_GRAPH_SCHEMA=schema_string("evidence_graph")


def graph_to_dict(graph:EvidenceGraph)->dict[str,Any]:
    return {"schema":EVIDENCE_GRAPH_SCHEMA,
            "nodes":[n.to_dict() for n in graph.nodes],
            "edges":[e.to_dict() for e in graph.edges]}


def graph_from_dict(payload:Mapping[str,Any])->EvidenceGraph:
    require_schema(payload,EVIDENCE_GRAPH_SCHEMA)
    return EvidenceGraph(
        tuple(EvidenceNode.from_dict(n) for n in payload.get("nodes",())),
        tuple(EvidenceEdge.from_dict(e) for e in payload.get("edges",())),
    )
