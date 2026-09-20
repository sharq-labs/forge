"""Canonical bindings from EngineeringIntent facts to graph input ports."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping

from ..scientific.serialization import require_schema, schema_string
from .errors import InvalidCompositionPackProvider

EXTERNAL_INPUT_BINDING_SCHEMA = schema_string(
    "composition_external_input_binding"
)

_PATH_SEGMENT = r"[a-zA-Z_][a-zA-Z0-9_]*(?:\[\d+\])?"
_PATH = re.compile(rf"^{_PATH_SEGMENT}(?:\.{_PATH_SEGMENT})*$")


@dataclass(frozen=True, order=True)
class ExternalInputBinding:
    blueprint_id: str
    participant_id: str
    port_id: str
    fact_path: str

    def __post_init__(self) -> None:
        for label in ("blueprint_id", "participant_id", "port_id"):
            value = str(getattr(self, label)).strip()
            if not value:
                raise InvalidCompositionPackProvider(
                    f"external input binding requires {label}"
                )
            object.__setattr__(self, label, value)
        path = str(self.fact_path).strip()
        if not _PATH.fullmatch(path):
            raise InvalidCompositionPackProvider(
                f"external input fact_path {path!r} must be a dotted "
                "concrete EngineeringIntent fact path"
            )
        object.__setattr__(self, "fact_path", path)

    @property
    def key(self) -> tuple[str, str, str]:
        return self.blueprint_id, self.participant_id, self.port_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": EXTERNAL_INPUT_BINDING_SCHEMA,
            "blueprint_id": self.blueprint_id,
            "participant_id": self.participant_id,
            "port_id": self.port_id,
            "fact_path": self.fact_path,
        }

    @classmethod
    def from_dict(
        cls,
        payload: Mapping[str, Any],
    ) -> "ExternalInputBinding":
        require_schema(payload, EXTERNAL_INPUT_BINDING_SCHEMA)
        return cls(
            blueprint_id=payload["blueprint_id"],
            participant_id=payload["participant_id"],
            port_id=payload["port_id"],
            fact_path=payload["fact_path"],
        )


__all__ = [
    "EXTERNAL_INPUT_BINDING_SCHEMA",
    "ExternalInputBinding",
]
