from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ..errors import InvalidScientificProblem
from ..serialization import require_schema, schema_string
from .environment import RuntimeEnvironment
from .identity import ArtifactIdentity

REPLAY_BUNDLE_SCHEMA = schema_string("scientific_replay_bundle")


@dataclass(frozen=True)
class ReplayBundle:
    run_id: str
    artifacts: tuple[ArtifactIdentity, ...]
    environment: RuntimeEnvironment
    random_seed: int | None = None

    def __post_init__(self) -> None:
        run_id = str(self.run_id).strip()
        if not run_id:
            raise InvalidScientificProblem("replay bundle requires run_id")
        object.__setattr__(self, "run_id", run_id)
        artifacts = tuple(self.artifacts)
        if any(not isinstance(a, ArtifactIdentity) for a in artifacts):
            raise InvalidScientificProblem(
                "replay bundle artifacts must be ArtifactIdentity records"
            )
        artifacts = tuple(
            sorted(
                artifacts,
                key=lambda a: (a.kind, a.identifier, a.digest),
            )
        )
        object.__setattr__(self, "artifacts", artifacts)
        keys=[(a.kind,a.identifier) for a in self.artifacts]
        if len(keys) != len(set(keys)):
            raise InvalidScientificProblem("replay bundle contains duplicate artifact identities")
        if not isinstance(self.environment, RuntimeEnvironment):
            raise InvalidScientificProblem("replay bundle requires RuntimeEnvironment")
        if self.random_seed is not None and (
            isinstance(self.random_seed, bool)
            or not isinstance(self.random_seed, int)
        ):
            raise InvalidScientificProblem("random_seed must be int or None")

    def to_dict(self) -> dict[str, Any]:
        return {"schema": REPLAY_BUNDLE_SCHEMA, "run_id": self.run_id,
                "artifacts": [a.to_dict() for a in self.artifacts],
                "environment": self.environment.to_dict(), "random_seed": self.random_seed}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ReplayBundle":
        require_schema(payload, REPLAY_BUNDLE_SCHEMA)
        return cls(payload["run_id"],
                   tuple(ArtifactIdentity.from_dict(a) for a in payload.get("artifacts", ())),
                   RuntimeEnvironment.from_dict(payload["environment"]),
                   payload.get("random_seed"))
