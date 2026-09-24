from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Mapping

from ..errors import InvalidScientificProblem
from ..results.immutable import freeze
from ..serialization import require_schema, schema_string
from ..units.quantity import Quantity

EXPERIMENT_CONTEXT_SCHEMA = schema_string("experimental_measurement_context")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class ExperimentContext:
    context_id: str
    protocol_digest: str
    specimen_digest: str
    conditions: Mapping[str, Quantity]

    def __post_init__(self) -> None:
        context_id = str(self.context_id).strip()
        if not context_id:
            raise InvalidScientificProblem(
                "experimental context requires context_id"
            )
        for name in ("protocol_digest", "specimen_digest"):
            value = str(getattr(self, name)).strip().lower()
            if not _SHA256.fullmatch(value):
                raise InvalidScientificProblem(
                    f"{name} must be lowercase SHA-256"
                )
            object.__setattr__(self, name, value)
        conditions = dict(self.conditions)
        if any(
            not str(name).strip() or not isinstance(value, Quantity)
            for name, value in conditions.items()
        ):
            raise InvalidScientificProblem(
                "experimental conditions require named Quantity values"
            )
        object.__setattr__(self, "context_id", context_id)
        object.__setattr__(
            self,
            "conditions",
            freeze(dict(sorted(conditions.items()))),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": EXPERIMENT_CONTEXT_SCHEMA,
            "context_id": self.context_id,
            "protocol_digest": self.protocol_digest,
            "specimen_digest": self.specimen_digest,
            "conditions": {
                key: value.to_dict()
                for key, value in self.conditions.items()
            },
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ExperimentContext":
        require_schema(payload, EXPERIMENT_CONTEXT_SCHEMA)
        return cls(
            payload["context_id"],
            payload["protocol_digest"],
            payload["specimen_digest"],
            {
                key: Quantity.from_dict(value)
                for key, value in payload.get("conditions", {}).items()
            },
        )

    @property
    def digest(self) -> str:
        return hashlib.sha256(
            json.dumps(
                self.to_dict(),
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
