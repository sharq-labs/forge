"""Structured scientific evidence graph."""

from .conflict import ConflictKind, EvidenceConflict, detect_direct_conflict
from .edge import EvidenceEdge, EvidenceRelation
from .fingerprint import evidence_graph_fingerprint
from .freshness import FreshnessStatus, assess_freshness
from .graph import EvidenceGraph
from .lineage import lineage_cycle
from .node import EvidenceAuthority, EvidenceNode
from .provenance import EvidenceProvenance
from .policy import EvidenceGraphPolicy, assess_graph
from .supersession import SupersessionDecision, assess_supersession

__all__ = [
    "EvidenceAuthority", "EvidenceNode", "EvidenceProvenance", "EvidenceRelation", "EvidenceEdge",
    "EvidenceGraph", "ConflictKind", "EvidenceConflict", "detect_direct_conflict",
    "FreshnessStatus", "assess_freshness", "SupersessionDecision",
    "assess_supersession", "EvidenceGraphPolicy", "assess_graph",
    "evidence_graph_fingerprint","lineage_cycle",
]
