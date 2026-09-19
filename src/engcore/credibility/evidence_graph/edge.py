from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from ...scientific.errors import InvalidScientificProblem
from ...scientific.serialization import require_schema, schema_string

EVIDENCE_EDGE_SCHEMA=schema_string("evidence_graph_edge")


class EvidenceRelation(str, Enum):
    SUPPORTS="supports"
    CONTRADICTS="contradicts"
    DERIVED_FROM="derived_from"
    REPLICATES="replicates"
    SUPERSEDES="supersedes"
    CALIBRATES="calibrates"
    VALIDATES="validates"


@dataclass(frozen=True)
class EvidenceEdge:
    source_id: str
    target_id: str
    relation: EvidenceRelation

    def __post_init__(self)->None:
        source,target=str(self.source_id).strip(),str(self.target_id).strip()
        if not source or not target:
            raise InvalidScientificProblem("evidence edge requires source and target")
        if source==target:
            raise InvalidScientificProblem("evidence edge cannot self-reference")
        object.__setattr__(self,"source_id",source)
        object.__setattr__(self,"target_id",target)
        object.__setattr__(self,"relation",EvidenceRelation(self.relation))

    def to_dict(self)->dict[str,Any]:
        return {"schema":EVIDENCE_EDGE_SCHEMA,"source_id":self.source_id,
                "target_id":self.target_id,"relation":self.relation.value}

    @classmethod
    def from_dict(cls,payload:Mapping[str,Any])->"EvidenceEdge":
        require_schema(payload,EVIDENCE_EDGE_SCHEMA)
        return cls(payload["source_id"],payload["target_id"],EvidenceRelation(payload["relation"]))
