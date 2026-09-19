from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from ...scientific.errors import InvalidScientificProblem
from ...scientific.serialization import require_schema, schema_string
from .provenance import EvidenceProvenance

EVIDENCE_NODE_SCHEMA = schema_string("evidence_graph_node", 2)
EVIDENCE_NODE_SCHEMA_V1 = schema_string("evidence_graph_node")


class EvidenceAuthority(str, Enum):
    MEASUREMENT = "measurement"
    EXPERIMENT = "experiment"
    STANDARD = "standard"
    PEER_REVIEWED = "peer_reviewed"
    OFFICIAL_DATA = "official_data"
    REFERENCE_DATA = "reference_data"
    DATASHEET = "datasheet"
    SIMULATION = "simulation"
    ANALYTICAL = "analytical"
    EXTERNAL_ORACLE = "external_oracle"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class EvidenceNode:
    evidence_id: str
    authority: EvidenceAuthority
    content_digest: str
    source: str
    observed_at: str = ""
    applicability: str = ""
    provenance: EvidenceProvenance | None = None

    def __post_init__(self) -> None:
        eid = str(self.evidence_id).strip()
        digest = str(self.content_digest).strip().lower()
        source = str(self.source).strip()
        if not eid or not source:
            raise InvalidScientificProblem("evidence node requires id and source")
        if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
            raise InvalidScientificProblem(
                "evidence content_digest must be lowercase SHA-256"
            )
        if self.provenance is not None:
            if not isinstance(self.provenance, EvidenceProvenance):
                raise InvalidScientificProblem(
                    "evidence provenance must be EvidenceProvenance"
                )
            if self.provenance.claim_digest != digest:
                raise InvalidScientificProblem(
                    "evidence content digest must equal provenance claim digest"
                )
            if self.applicability and self.applicability != self.provenance.context_digest:
                raise InvalidScientificProblem(
                    "evidence applicability differs from provenance context"
                )
        object.__setattr__(self, "evidence_id", eid)
        object.__setattr__(self, "authority", EvidenceAuthority(self.authority))
        object.__setattr__(self, "content_digest", digest)
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "observed_at", str(self.observed_at).strip())
        object.__setattr__(self, "applicability", str(self.applicability).strip())

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "schema": (
                EVIDENCE_NODE_SCHEMA
                if self.provenance is not None
                else EVIDENCE_NODE_SCHEMA_V1
            ),
            "evidence_id": self.evidence_id,
            "authority": self.authority.value,
            "content_digest": self.content_digest,
            "source": self.source,
            "observed_at": self.observed_at,
            "applicability": self.applicability,
        }
        if self.provenance is not None:
            payload["provenance"] = self.provenance.to_dict()
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "EvidenceNode":
        schema = payload.get("schema")
        if schema not in {EVIDENCE_NODE_SCHEMA, EVIDENCE_NODE_SCHEMA_V1}:
            require_schema(payload, EVIDENCE_NODE_SCHEMA)
        provenance = payload.get("provenance")
        if schema == EVIDENCE_NODE_SCHEMA_V1 and provenance is not None:
            raise InvalidScientificProblem(
                "V1 evidence node cannot carry provenance"
            )
        return cls(
            payload["evidence_id"],
            EvidenceAuthority(payload["authority"]),
            payload["content_digest"],
            payload["source"],
            payload.get("observed_at", ""),
            payload.get("applicability", ""),
            EvidenceProvenance.from_dict(provenance)
            if provenance is not None
            else None,
        )
