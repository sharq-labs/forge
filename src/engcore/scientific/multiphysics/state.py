"""Serializable identities for participant checkpoints."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ..errors import InvalidScientificProblem
from ..serialization import require_schema, schema_string
from ..units.quantity import Quantity, dimensionality

CHECKPOINT_SCHEMA = schema_string("multiphysics_checkpoint")


@dataclass(frozen=True)
class CheckpointRecord:
    participant_id: str
    instant: Quantity
    state_digest: str
    deterministic_restore: bool
    provider_state_id: str = ""

    def __post_init__(self) -> None:
        participant = str(self.participant_id).strip()
        digest = str(self.state_digest).strip().lower()
        if not participant:
            raise InvalidScientificProblem("checkpoint requires participant_id")
        if not isinstance(self.instant, Quantity) or dimensionality(self.instant.units) != dimensionality("second"):
            raise InvalidScientificProblem("checkpoint instant must be time")
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise InvalidScientificProblem("checkpoint state_digest must be sha256 hex")
        if not isinstance(self.deterministic_restore, bool):
            raise InvalidScientificProblem("deterministic_restore must be boolean")
        object.__setattr__(self, "participant_id", participant)
        object.__setattr__(self, "instant", self.instant.to("second"))
        object.__setattr__(self, "state_digest", digest)
        object.__setattr__(self, "provider_state_id", str(self.provider_state_id).strip())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": CHECKPOINT_SCHEMA,
            "participant_id": self.participant_id,
            "instant": self.instant.to_dict(),
            "state_digest": self.state_digest,
            "deterministic_restore": self.deterministic_restore,
            "provider_state_id": self.provider_state_id,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CheckpointRecord":
        require_schema(payload, CHECKPOINT_SCHEMA)
        return cls(
            participant_id=payload["participant_id"],
            instant=Quantity.from_dict(payload["instant"]),
            state_digest=payload["state_digest"],
            deterministic_restore=payload["deterministic_restore"],
            provider_state_id=payload.get("provider_state_id", ""),
        )
