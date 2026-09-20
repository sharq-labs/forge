"""Canonical quantity and coupling semantics for cross-domain composition."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping

from ..scientific.serialization import require_schema, schema_string
from .errors import InvalidCompositionPackProvider

PORT_SEMANTIC_SCHEMA = schema_string("composition_port_semantic")
COUPLING_SEMANTIC_SCHEMA = schema_string("composition_coupling_semantic")

_ID = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*$")


def canonical_quantity_id(value: object, field: str = "quantity_id") -> str:
    text = str(value).strip()
    if not _ID.fullmatch(text):
        raise InvalidCompositionPackProvider(
            f"{field} {text!r} must be lowercase dotted identifier segments"
        )
    return text


@dataclass(frozen=True, order=True)
class PortSemanticBinding:
    blueprint_id: str
    participant_id: str
    port_id: str
    quantity_id: str

    def __post_init__(self) -> None:
        for label in ("blueprint_id", "participant_id", "port_id"):
            value = str(getattr(self, label)).strip()
            if not value:
                raise InvalidCompositionPackProvider(
                    f"port semantic binding requires {label}"
                )
            object.__setattr__(self, label, value)
        object.__setattr__(
            self,
            "quantity_id",
            canonical_quantity_id(self.quantity_id),
        )

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.blueprint_id, self.participant_id, self.port_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": PORT_SEMANTIC_SCHEMA,
            "blueprint_id": self.blueprint_id,
            "participant_id": self.participant_id,
            "port_id": self.port_id,
            "quantity_id": self.quantity_id,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "PortSemanticBinding":
        require_schema(payload, PORT_SEMANTIC_SCHEMA)
        return cls(
            payload["blueprint_id"],
            payload["participant_id"],
            payload["port_id"],
            payload["quantity_id"],
        )


@dataclass(frozen=True, order=True)
class CouplingSemantic:
    blueprint_id: str
    edge_id: str
    source_quantity_id: str
    target_quantity_id: str
    transfer_law_id: str
    sign_convention: str
    conserved_quantity_id: str = ""
    reference: str = ""
    description: str = ""

    def __post_init__(self) -> None:
        for label in ("blueprint_id", "edge_id", "transfer_law_id", "sign_convention"):
            value = str(getattr(self, label)).strip()
            if not value:
                raise InvalidCompositionPackProvider(
                    f"coupling semantic requires {label}"
                )
            object.__setattr__(self, label, value)
        object.__setattr__(
            self,
            "source_quantity_id",
            canonical_quantity_id(self.source_quantity_id, "source_quantity_id"),
        )
        object.__setattr__(
            self,
            "target_quantity_id",
            canonical_quantity_id(self.target_quantity_id, "target_quantity_id"),
        )
        conserved = str(self.conserved_quantity_id).strip()
        if conserved:
            conserved = canonical_quantity_id(
                conserved, "conserved_quantity_id"
            )
        object.__setattr__(self, "conserved_quantity_id", conserved)
        object.__setattr__(self, "reference", str(self.reference).strip())
        object.__setattr__(self, "description", str(self.description).strip())

    @property
    def key(self) -> tuple[str, str]:
        return (self.blueprint_id, self.edge_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": COUPLING_SEMANTIC_SCHEMA,
            "blueprint_id": self.blueprint_id,
            "edge_id": self.edge_id,
            "source_quantity_id": self.source_quantity_id,
            "target_quantity_id": self.target_quantity_id,
            "transfer_law_id": self.transfer_law_id,
            "sign_convention": self.sign_convention,
            "conserved_quantity_id": self.conserved_quantity_id,
            "reference": self.reference,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CouplingSemantic":
        require_schema(payload, COUPLING_SEMANTIC_SCHEMA)
        return cls(
            blueprint_id=payload["blueprint_id"],
            edge_id=payload["edge_id"],
            source_quantity_id=payload["source_quantity_id"],
            target_quantity_id=payload["target_quantity_id"],
            transfer_law_id=payload["transfer_law_id"],
            sign_convention=payload["sign_convention"],
            conserved_quantity_id=payload.get("conserved_quantity_id", ""),
            reference=payload.get("reference", ""),
            description=payload.get("description", ""),
        )


__all__ = [
    "COUPLING_SEMANTIC_SCHEMA",
    "PORT_SEMANTIC_SCHEMA",
    "CouplingSemantic",
    "PortSemanticBinding",
    "canonical_quantity_id",
]
