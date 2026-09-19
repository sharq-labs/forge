from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping

from ..errors import InvalidScientificProblem
from ..serialization import require_schema, schema_string

ARTIFACT_IDENTITY_SCHEMA = schema_string("replay_artifact_identity")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class ArtifactIdentity:
    kind: str
    identifier: str
    digest: str

    def __post_init__(self) -> None:
        kind, identifier, digest = str(self.kind).strip(), str(self.identifier).strip(), str(self.digest).strip().lower()
        if not kind or not identifier:
            raise InvalidScientificProblem("replay artifact identity requires kind and identifier")
        if not _SHA256.fullmatch(digest):
            raise InvalidScientificProblem("replay artifact digest must be lowercase SHA-256")
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "identifier", identifier)
        object.__setattr__(self, "digest", digest)

    def to_dict(self) -> dict[str, Any]:
        return {"schema": ARTIFACT_IDENTITY_SCHEMA, "kind": self.kind,
                "identifier": self.identifier, "digest": self.digest}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ArtifactIdentity":
        require_schema(payload, ARTIFACT_IDENTITY_SCHEMA)
        return cls(payload["kind"], payload["identifier"], payload["digest"])
