from __future__ import annotations

from .edge import EvidenceEdge, EvidenceRelation

_LINEAGE_RELATIONS=frozenset({EvidenceRelation.DERIVED_FROM,EvidenceRelation.SUPERSEDES})


def lineage_cycle(edges:tuple[EvidenceEdge,...])->tuple[str,...]:
    graph={}
    for edge in edges:
        if edge.relation in _LINEAGE_RELATIONS:
            graph.setdefault(edge.source_id,set()).add(edge.target_id)
    visiting=set()
    done=set()

    def walk(node,trail):
        if node in visiting:
            start=trail.index(node) if node in trail else 0
            return tuple(trail[start:]+[node])
        if node in done:
            return ()
        visiting.add(node)
        for nxt in sorted(graph.get(node,())):
            found=walk(nxt,trail+[node])
            if found:
                return found
        visiting.remove(node)
        done.add(node)
        return ()

    for node in sorted(graph):
        found=walk(node,[])
        if found:
            return found
    return ()
