"""Replayable provenance snapshot for an Execution Pack."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any

from .registry import RegisteredExecutionPack

EXECUTION_SNAPSHOT_SCHEMA = "forge.execution_pack_snapshot/1"


@dataclass(frozen=True)
class ExecutionPackSnapshot:
    pack_id: str
    pack_version: str
    manifest_digest: str
    composition_pack_id: str
    composition_pack_version: str
    composition_manifest_digest: str
    participant_factories: tuple[dict[str, str], ...]

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
            "participant_factories": list(self.participant_factories),
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
    )


__all__ = [
    "EXECUTION_SNAPSHOT_SCHEMA",
    "ExecutionPackSnapshot",
    "snapshot_execution_pack",
]
