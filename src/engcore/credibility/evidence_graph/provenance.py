from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Any, Mapping

from ...scientific.errors import InvalidScientificProblem
from ...scientific.serialization import require_schema, schema_string

EVIDENCE_PROVENANCE_SCHEMA = schema_string("evidence_provenance", 2)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class EvidenceProvenance:
    source_id: str
    issuer: str
    document_digest: str
    version: str
    locator: str
    published_at: str
    retrieved_at: str
    source_class: str
    pin_issuer: str
    pin_document_digest: str
    pin_version: str
    freshness_limit_days: int | None
    freshness_requires_timestamp: bool
    assessed_at: str
    context_digest: str
    claim_digest: str

    def __post_init__(self) -> None:
        for label in (
            "source_id", "issuer", "version", "locator", "source_class",
            "pin_issuer", "pin_version", "assessed_at",
        ):
            value = str(getattr(self, label)).strip()
            if not value:
                raise InvalidScientificProblem(
                    f"evidence provenance {label} must be non-empty"
                )
            object.__setattr__(self, label, value)
        for label in ("published_at", "retrieved_at"):
            object.__setattr__(self, label, str(getattr(self, label)).strip())
        for label in (
            "document_digest", "pin_document_digest", "context_digest", "claim_digest",
        ):
            value = str(getattr(self, label)).strip().lower()
            if not _SHA256.fullmatch(value):
                raise InvalidScientificProblem(
                    f"evidence provenance {label} must be lowercase SHA-256"
                )
            object.__setattr__(self, label, value)
        if self.freshness_limit_days is not None:
            limit = int(self.freshness_limit_days)
            if limit < 0:
                raise InvalidScientificProblem(
                    "evidence provenance freshness limit must be non-negative"
                )
            object.__setattr__(self, "freshness_limit_days", limit)
        if not isinstance(self.freshness_requires_timestamp, bool):
            raise InvalidScientificProblem(
                "freshness_requires_timestamp must be bool"
            )
        self._assessment_time()

    def _assessment_time(self) -> datetime:
        try:
            parsed = datetime.fromisoformat(self.assessed_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise InvalidScientificProblem(
                "evidence provenance assessed_at must be ISO-8601"
            ) from exc
        if parsed.tzinfo is None:
            raise InvalidScientificProblem(
                "evidence provenance assessed_at must be timezone-aware"
            )
        return parsed.astimezone(timezone.utc)

    @property
    def trust_status(self) -> str:
        if self.issuer != self.pin_issuer:
            return "issuer_mismatch"
        if self.version != self.pin_version:
            return "version_mismatch"
        if self.document_digest != self.pin_document_digest:
            return "digest_mismatch"
        return "pinned"

    @property
    def trusted(self) -> bool:
        return self.trust_status == "pinned"

    @property
    def freshness(self) -> str:
        if self.freshness_limit_days is None:
            return "not_applicable"
        if not self.published_at:
            return "unknown"
        try:
            published = datetime.fromisoformat(
                self.published_at.replace("Z", "+00:00")
            )
        except ValueError:
            return "unknown"
        if published.tzinfo is None:
            return "unknown"
        age = (
            self._assessment_time() - published.astimezone(timezone.utc)
        ).total_seconds() / 86400
        if age < 0:
            return "unknown"
        return "current" if age <= self.freshness_limit_days else "stale"

    @property
    def fresh_enough(self) -> bool:
        if self.freshness == "unknown" and not self.freshness_requires_timestamp:
            return True
        return self.freshness in {"current", "not_applicable"}

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": EVIDENCE_PROVENANCE_SCHEMA,
            "source_id": self.source_id,
            "issuer": self.issuer,
            "document_digest": self.document_digest,
            "version": self.version,
            "locator": self.locator,
            "published_at": self.published_at,
            "retrieved_at": self.retrieved_at,
            "source_class": self.source_class,
            "pin_issuer": self.pin_issuer,
            "pin_document_digest": self.pin_document_digest,
            "pin_version": self.pin_version,
            "freshness_limit_days": self.freshness_limit_days,
            "freshness_requires_timestamp": self.freshness_requires_timestamp,
            "assessed_at": self.assessed_at,
            "context_digest": self.context_digest,
            "claim_digest": self.claim_digest,
            "trust_status": self.trust_status,
            "freshness": self.freshness,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "EvidenceProvenance":
        require_schema(payload, EVIDENCE_PROVENANCE_SCHEMA)
        value = cls(
            payload["source_id"],
            payload["issuer"],
            payload["document_digest"],
            payload["version"],
            payload["locator"],
            payload.get("published_at", ""),
            payload.get("retrieved_at", ""),
            payload["source_class"],
            payload["pin_issuer"],
            payload["pin_document_digest"],
            payload["pin_version"],
            payload.get("freshness_limit_days"),
            payload["freshness_requires_timestamp"],
            payload["assessed_at"],
            payload["context_digest"],
            payload["claim_digest"],
        )
        if "trust_status" in payload and payload["trust_status"] != value.trust_status:
            raise InvalidScientificProblem(
                "serialized evidence provenance trust status is forged or stale"
            )
        if "freshness" in payload and payload["freshness"] != value.freshness:
            raise InvalidScientificProblem(
                "serialized evidence provenance freshness is forged or stale"
            )
        return value
