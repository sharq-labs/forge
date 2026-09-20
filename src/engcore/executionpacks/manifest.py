"""Manifest for executable adapters separated from composition science."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Mapping

from .errors import InvalidExecutionPackManifest

EXECUTION_PACK_SCHEMA = "forge.execution_pack/1"
EXECUTION_PACK_API = "forge.executionpack_api/1"

_ID = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*$")


def _text(value: object, field: str) -> str:
    text = str(value).strip()
    if not text:
        raise InvalidExecutionPackManifest(f"{field} must be non-empty")
    return text


def _id(value: object, field: str) -> str:
    text = _text(value, field)
    if not _ID.fullmatch(text):
        raise InvalidExecutionPackManifest(
            f"{field} {text!r} must be lowercase dotted identifier segments"
        )
    return text


def _sha(value: object, field: str) -> str:
    text = str(value).strip().lower()
    if (
        len(text) != 64
        or any(ch not in "0123456789abcdef" for ch in text)
    ):
        raise InvalidExecutionPackManifest(f"{field} must be sha256 hex")
    return text


@dataclass(frozen=True, order=True)
class CompositionDependency:
    pack_id: str
    pack_version: str
    manifest_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "pack_id", _id(self.pack_id, "pack_id"))
        object.__setattr__(
            self, "pack_version", _text(self.pack_version, "pack_version")
        )
        object.__setattr__(
            self,
            "manifest_digest",
            _sha(self.manifest_digest, "manifest_digest"),
        )

    @property
    def key(self) -> tuple[str, str]:
        return self.pack_id, self.pack_version

    def to_dict(self) -> dict[str, str]:
        return {
            "pack_id": self.pack_id,
            "pack_version": self.pack_version,
            "manifest_digest": self.manifest_digest,
        }


@dataclass(frozen=True, order=True)
class ParticipantFactoryRef:
    model_id: str
    model_version: str
    realization_id: str
    realization_version: str
    solver_id: str
    solver_version: str
    adapter_id: str
    adapter_version: str
    implementation_digest: str

    def __post_init__(self) -> None:
        for label in (
            "model_id",
            "model_version",
            "realization_id",
            "realization_version",
            "solver_id",
            "solver_version",
            "adapter_id",
            "adapter_version",
        ):
            value = str(getattr(self, label)).strip()
            if not value:
                raise InvalidExecutionPackManifest(
                    f"participant factory ref requires {label}"
                )
            object.__setattr__(self, label, value)
        object.__setattr__(
            self,
            "implementation_digest",
            _sha(self.implementation_digest, "implementation_digest"),
        )

    @property
    def key(self) -> tuple[str, ...]:
        return (
            self.model_id,
            self.model_version,
            self.realization_id,
            self.realization_version,
            self.solver_id,
            self.solver_version,
            self.adapter_id,
            self.adapter_version,
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "model_id": self.model_id,
            "model_version": self.model_version,
            "realization_id": self.realization_id,
            "realization_version": self.realization_version,
            "solver_id": self.solver_id,
            "solver_version": self.solver_version,
            "adapter_id": self.adapter_id,
            "adapter_version": self.adapter_version,
            "implementation_digest": self.implementation_digest,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ParticipantFactoryRef":
        return cls(**dict(payload))


@dataclass(frozen=True)
class ExecutionPackManifest:
    pack_id: str
    pack_version: str
    compatible_core_apis: tuple[str, ...]
    composition: CompositionDependency
    participant_factories: tuple[ParticipantFactoryRef, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "pack_id", _id(self.pack_id, "pack_id"))
        object.__setattr__(
            self, "pack_version", _text(self.pack_version, "pack_version")
        )
        apis = tuple(
            sorted({_text(item, "compatible_core_api") for item in self.compatible_core_apis})
        )
        if not apis:
            raise InvalidExecutionPackManifest(
                "compatible_core_apis may not be empty"
            )
        object.__setattr__(self, "compatible_core_apis", apis)
        if not isinstance(self.composition, CompositionDependency):
            raise InvalidExecutionPackManifest(
                "execution pack requires CompositionDependency"
            )
        refs = tuple(sorted(self.participant_factories))
        if not refs:
            raise InvalidExecutionPackManifest(
                "execution pack requires participant factories"
            )
        if len({item.key for item in refs}) != len(refs):
            raise InvalidExecutionPackManifest(
                "duplicate participant factory identities"
            )
        object.__setattr__(self, "participant_factories", refs)

    @property
    def key(self) -> tuple[str, str]:
        return self.pack_id, self.pack_version

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": EXECUTION_PACK_SCHEMA,
            "pack_id": self.pack_id,
            "pack_version": self.pack_version,
            "compatible_core_apis": list(self.compatible_core_apis),
            "composition": self.composition.to_dict(),
            "participant_factories": [
                item.to_dict() for item in self.participant_factories
            ],
        }

    @property
    def digest(self) -> str:
        return hashlib.sha256(
            json.dumps(
                self.to_dict(),
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()


__all__ = [
    "EXECUTION_PACK_API",
    "EXECUTION_PACK_SCHEMA",
    "CompositionDependency",
    "ExecutionPackManifest",
    "ParticipantFactoryRef",
]
