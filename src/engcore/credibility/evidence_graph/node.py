from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from ...scientific.errors import InvalidScientificProblem
from ...scientific.serialization import require_schema, schema_string

EVIDENCE_NODE_SCHEMA=schema_string("evidence_graph_node")


class EvidenceAuthority(str, Enum):
    MEASUREMENT="measurement"
    EXPERIMENT="experiment"
    STANDARD="standard"
    PEER_REVIEWED="peer_reviewed"
    SIMULATION="simulation"
    ANALYTICAL="analytical"
    EXTERNAL_ORACLE="external_oracle"
    UNKNOWN="unknown"


@dataclass(frozen=True)
class EvidenceNode:
    evidence_id: str
    authority: EvidenceAuthority
    content_digest: str
    source: str
    observed_at: str = ""
    applicability: str = ""

    def __post_init__(self) -> None:
        eid=str(self.evidence_id).strip()
        digest=str(self.content_digest).strip().lower()
        source=str(self.source).strip()
        if not eid or not source:
            raise InvalidScientificProblem("evidence node requires id and source")
        if len(digest)!=64 or any(ch not in "0123456789abcdef" for ch in digest):
            raise InvalidScientificProblem("evidence content_digest must be lowercase SHA-256")
        object.__setattr__(self,"evidence_id",eid)
        object.__setattr__(self,"authority",EvidenceAuthority(self.authority))
        object.__setattr__(self,"content_digest",digest)
        object.__setattr__(self,"source",source)

    def to_dict(self)->dict[str,Any]:
        return {"schema":EVIDENCE_NODE_SCHEMA,"evidence_id":self.evidence_id,
                "authority":self.authority.value,"content_digest":self.content_digest,
                "source":self.source,"observed_at":self.observed_at,
                "applicability":self.applicability}

    @classmethod
    def from_dict(cls,payload:Mapping[str,Any])->"EvidenceNode":
        require_schema(payload,EVIDENCE_NODE_SCHEMA)
        return cls(payload["evidence_id"],EvidenceAuthority(payload["authority"]),
                   payload["content_digest"],payload["source"],
                   payload.get("observed_at",""),payload.get("applicability",""))
