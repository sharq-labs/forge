"""Replayable provenance snapshot for an Execution Pack."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping

from ..scientific.serialization import require_schema_any
from ..scientific.results.immutable import detach, freeze
from .registry import RegisteredExecutionPack

EXECUTION_SNAPSHOT_SCHEMA_V1 = "forge.execution_pack_snapshot/1"
EXECUTION_SNAPSHOT_SCHEMA = "forge.execution_pack_snapshot/2"


@dataclass(frozen=True)
class ExecutionPackSnapshot:
    pack_id: str
    pack_version: str
    manifest_digest: str
    composition_pack_id: str
    composition_pack_version: str
    composition_manifest_digest: str
    participant_factories: tuple[dict[str, Any], ...]
    composition_authority_digest: str
    authority_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "participant_factories",
            tuple(freeze(dict(item)) for item in self.participant_factories),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": EXECUTION_SNAPSHOT_SCHEMA,
            "pack_id": self.pack_id,
            "pack_version": self.pack_version,
            "manifest_digest": self.manifest_digest,
            "composition": {
                "pack_id": self.composition_pack_id,
                "pack_version": self.composition_pack_version,
                "manifest_digest": self.composition_manifest_digest,
            },
            "participant_factories": detach(self.participant_factories),
            "composition_authority_digest": (
                self.composition_authority_digest
            ),
            "authority_digest": self.authority_digest,
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
        cls,
        payload: Mapping[str, Any],
    ) -> "ExecutionPackSnapshot":
        require_schema_any(
            payload,
            (EXECUTION_SNAPSHOT_SCHEMA_V1, EXECUTION_SNAPSHOT_SCHEMA),
        )
        composition = payload["composition"]
        return cls(
            pack_id=payload["pack_id"],
            pack_version=payload["pack_version"],
            manifest_digest=payload["manifest_digest"],
            composition_pack_id=composition["pack_id"],
            composition_pack_version=composition["pack_version"],
            composition_manifest_digest=composition["manifest_digest"],
            participant_factories=tuple(
                dict(item)
                for item in payload.get("participant_factories", ())
            ),
            composition_authority_digest=payload[
                "composition_authority_digest"
            ],
            authority_digest=payload["authority_digest"],
        )


def snapshot_execution_pack(
    registration: RegisteredExecutionPack,
) -> ExecutionPackSnapshot:
    manifest = registration.manifest
    return ExecutionPackSnapshot(
        pack_id=manifest.pack_id,
        pack_version=manifest.pack_version,
        manifest_digest=manifest.digest,
        composition_pack_id=manifest.composition.pack_id,
        composition_pack_version=manifest.composition.pack_version,
        composition_manifest_digest=manifest.composition.manifest_digest,
        participant_factories=tuple(
            item.to_dict()
            for item in manifest.participant_factories
        ),
        composition_authority_digest=(
            registration.composition_authority_digest
        ),
        authority_digest=registration.authority_digest,
    )


__all__ = [
    "EXECUTION_SNAPSHOT_SCHEMA",
    "EXECUTION_SNAPSHOT_SCHEMA_V1",
    "ExecutionPackSnapshot",
    "snapshot_execution_pack",
]
