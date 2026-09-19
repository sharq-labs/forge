from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping

from ..errors import InvalidScientificProblem
from ..serialization import require_schema, schema_string

RUNTIME_ENVIRONMENT_SCHEMA = schema_string("replay_runtime_environment")


@dataclass(frozen=True)
class RuntimeEnvironment:
    python: str
    platform: str
    dependencies_digest: str
    hardware: str = ""
    floating_point: str = ""

    def __post_init__(self) -> None:
        if not str(self.python).strip() or not str(self.platform).strip():
            raise InvalidScientificProblem("replay environment requires python and platform identity")
        digest=str(self.dependencies_digest).strip().lower()
        if not re.fullmatch(r"[0-9a-f]{64}",digest):
            raise InvalidScientificProblem("dependencies_digest must be lowercase SHA-256")
        object.__setattr__(self,"dependencies_digest",digest)

    def to_dict(self) -> dict[str, Any]:
        return {"schema": RUNTIME_ENVIRONMENT_SCHEMA, "python": self.python,
                "platform": self.platform, "dependencies_digest": self.dependencies_digest,
                "hardware": self.hardware, "floating_point": self.floating_point}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RuntimeEnvironment":
        require_schema(payload, RUNTIME_ENVIRONMENT_SCHEMA)
        return cls(payload["python"], payload["platform"], payload["dependencies_digest"],
                   payload.get("hardware", ""), payload.get("floating_point", ""))
