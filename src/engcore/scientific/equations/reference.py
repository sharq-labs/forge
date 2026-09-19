"""Stable references binding provenance to an exact scientific law contract."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping

from ..serialization import require_schema, schema_string
from .errors import LawIdentityError
from .fingerprint import law_fingerprint
from .law import LawDefinition

LAW_REFERENCE_SCHEMA = schema_string("scientific_law_reference")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class LawReference:
    law_id: str
    fingerprint: str

    def __post_init__(self) -> None:
        law_id = str(self.law_id).strip()
        fingerprint = str(self.fingerprint).strip().lower()
        if not law_id:
            raise LawIdentityError("invalid_law_reference", "law reference id must be non-empty")
        if not _SHA256.fullmatch(fingerprint):
            raise LawIdentityError(
                "invalid_law_reference",
                "law reference fingerprint must be a lowercase SHA-256 hex digest",
            )
        object.__setattr__(self, "law_id", law_id)
        object.__setattr__(self, "fingerprint", fingerprint)

    @classmethod
    def from_law(cls, law: LawDefinition) -> "LawReference":
        if not isinstance(law, LawDefinition):
            raise TypeError("LawReference.from_law requires LawDefinition")
        return cls(law_id=law.law_id, fingerprint=law_fingerprint(law))

    def verify(self, law: LawDefinition) -> None:
        if not isinstance(law, LawDefinition):
            raise TypeError("LawReference.verify requires LawDefinition")
        if law.law_id != self.law_id:
            raise LawIdentityError(
                "law_id_mismatch",
                f"law reference names {self.law_id!r}, received {law.law_id!r}",
            )
        actual = law_fingerprint(law)
        if actual != self.fingerprint:
            raise LawIdentityError(
                "law_fingerprint_mismatch",
                f"law {self.law_id!r} content fingerprint changed: "
                f"expected {self.fingerprint}, found {actual}",
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": LAW_REFERENCE_SCHEMA,
            "law_id": self.law_id,
            "fingerprint": self.fingerprint,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "LawReference":
        require_schema(payload, LAW_REFERENCE_SCHEMA)
        return cls(
            law_id=payload["law_id"],
            fingerprint=payload["fingerprint"],
        )
