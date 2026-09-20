"""Manifest for executable adapters separated from composition science."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Mapping

from ..scientific.multiphysics import ParticipantModelRef
from .errors import InvalidExecutionPackManifest

EXECUTION_PACK_SCHEMA_V1 = "forge.execution_pack/1"
EXECUTION_PACK_SCHEMA = "forge.execution_pack/2"
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

    @classmethod
    def from_dict(
        cls, payload: Mapping[str, Any]
    ) -> "CompositionDependency":
        return cls(
            payload["pack_id"],
            payload["pack_version"],
            payload["manifest_digest"],
        )


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
    models: tuple[ParticipantModelRef, ...] = ()

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
        models = tuple(self.models)
        if not models:
            models = (
                ParticipantModelRef(self.model_id, self.model_version),
            )
        if any(not isinstance(item, ParticipantModelRef) for item in models):
            raise InvalidExecutionPackManifest(
                "participant factory ref models must be ParticipantModelRef"
            )
        keys = [item.key for item in models]
        if len(keys) != len(set(keys)):
            raise InvalidExecutionPackManifest(
                "participant factory ref model assembly contains duplicates"
            )
        if (self.model_id, self.model_version) not in set(keys):
            raise InvalidExecutionPackManifest(
                "participant factory ref primary model must be in assembly"
            )
        object.__setattr__(
            self,
            "models",
            tuple(sorted(models, key=lambda item: item.key)),
        )

    @property
    def model_keys(self) -> tuple[tuple[str, str], ...]:
        return tuple(item.key for item in self.models)

    @property
    def key(self) -> tuple[object, ...]:
        return (
            self.model_keys,
            self.realization_id,
            self.realization_version,
            self.solver_id,
            self.solver_version,
            self.adapter_id,
            self.adapter_version,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "model_version": self.model_version,
            "models": [item.to_dict() for item in self.models],
            "realization_id": self.realization_id,
            "realization_version": self.realization_version,
            "solver_id": self.solver_id,
            "solver_version": self.solver_version,
            "adapter_id": self.adapter_id,
            "adapter_version": self.adapter_version,
            "implementation_digest": self.implementation_digest,
        }

    @classmethod
    def from_dict(
        cls,
        payload: Mapping[str, Any],
        *,
        legacy: bool = False,
    ) -> "ParticipantFactoryRef":
        models = (
            ()
            if legacy
            else tuple(
                ParticipantModelRef.from_dict(item)
                for item in payload.get("models", ())
            )
        )
        return cls(
            model_id=payload["model_id"],
            model_version=payload["model_version"],
            realization_id=payload["realization_id"],
            realization_version=payload["realization_version"],
            solver_id=payload["solver_id"],
            solver_version=payload["solver_version"],
            adapter_id=payload["adapter_id"],
            adapter_version=payload["adapter_version"],
            implementation_digest=payload["implementation_digest"],
            models=models,
        )


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
            sorted(
                {
                    _text(item, "compatible_core_api")
                    for item in self.compatible_core_apis
                }
            )
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

    @classmethod
    def from_dict(
        cls, payload: Mapping[str, Any]
    ) -> "ExecutionPackManifest":
        schema = payload.get("schema")
        if schema not in (EXECUTION_PACK_SCHEMA_V1, EXECUTION_PACK_SCHEMA):
            raise InvalidExecutionPackManifest(
                f"unsupported execution pack schema {schema!r}"
            )
        legacy = schema == EXECUTION_PACK_SCHEMA_V1
        return cls(
            pack_id=payload["pack_id"],
            pack_version=payload["pack_version"],
            compatible_core_apis=tuple(payload["compatible_core_apis"]),
            composition=CompositionDependency.from_dict(
                payload["composition"]
            ),
            participant_factories=tuple(
                ParticipantFactoryRef.from_dict(
                    item,
                    legacy=legacy,
                )
                for item in payload["participant_factories"]
            ),
        )


__all__ = [
    "EXECUTION_PACK_API",
    "EXECUTION_PACK_SCHEMA",
    "EXECUTION_PACK_SCHEMA_V1",
    "CompositionDependency",
    "ExecutionPackManifest",
    "ParticipantFactoryRef",
]
