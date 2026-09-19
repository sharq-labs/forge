from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping

from ...scientific.errors import InvalidScientificProblem
from ...scientific.serialization import require_schema, schema_string

EVIDENCE_PROVENANCE_SCHEMA = schema_string("evidence_provenance")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class EvidenceProvenance:
    source_id: str
    issuer: str
    document_digest: str
    version: str
    locator: str
    retrieved_at: str
    source_class: str
    trust_status: str
    freshness: str
    context_digest: str
    claim_digest: str

    def __post_init__(self) -> None:
        for label in (
            "source_id", "issuer", "version", "locator",
            "source_class", "trust_status", "freshness",
        ):
            value = str(getattr(self, label)).strip()
            if not value:
                raise InvalidScientificProblem(
                    f"evidence provenance {label} must be non-empty"
                )
            object.__setattr__(self, label, value)
        object.__setattr__(self, "retrieved_at", str(self.retrieved_at).strip())
        for label in ("document_digest", "context_digest", "claim_digest"):
            value = str(getattr(self, label)).strip().lower()
            if not _SHA256.fullmatch(value):
                raise InvalidScientificProblem(
                    f"evidence provenance {label} must be lowercase SHA-256"
                )
            object.__setattr__(self, label, value)

    @property
    def trusted(self) -> bool:
        return self.trust_status == "pinned"

    @property
    def fresh_enough(self) -> bool:
        return self.freshness in {"current", "not_applicable"}

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": EVIDENCE_PROVENANCE_SCHEMA,
            "source_id": self.source_id,
            "issuer": self.issuer,
            "document_digest": self.document_digest,
            "version": self.version,
            "locator": self.locator,
            "retrieved_at": self.retrieved_at,
            "source_class": self.source_class,
            "trust_status": self.trust_status,
            "freshness": self.freshness,
            "context_digest": self.context_digest,
            "claim_digest": self.claim_digest,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "EvidenceProvenance":
        require_schema(payload, EVIDENCE_PROVENANCE_SCHEMA)
        return cls(
            payload["source_id"],
            payload["issuer"],
            payload["document_digest"],
            payload["version"],
            payload["locator"],
            payload.get("retrieved_at", ""),
            payload["source_class"],
            payload["trust_status"],
            payload["freshness"],
            payload["context_digest"],
            payload["claim_digest"],
        )
