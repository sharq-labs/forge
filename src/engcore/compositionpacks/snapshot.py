"""Replayable provenance snapshot for a registered Composition Pack."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any

from .registry import RegisteredCompositionPack

COMPOSITION_SNAPSHOT_SCHEMA = "forge.composition_pack_snapshot/1"


@dataclass(frozen=True)
class CompositionPackSnapshot:
    pack_id: str
    pack_version: str
    manifest_digest: str
    dependency_manifests: tuple[tuple[str, str, str], ...]
    blueprint_digests: tuple[tuple[str, str, str], ...]
    coupling_policy_digests: tuple[tuple[str, str, str], ...]
    system_contract_digest: str
    validation_implementations: tuple[dict[str, str], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": COMPOSITION_SNAPSHOT_SCHEMA,
            "pack_id": self.pack_id,
            "pack_version": self.pack_version,
            "manifest_digest": self.manifest_digest,
            "dependency_manifests": [
                {
                    "pack_id": pack_id,
                    "pack_version": version,
                    "manifest_digest": digest,
                }
                for pack_id, version, digest in self.dependency_manifests
            ],
            "blueprint_digests": [
                {
                    "blueprint_id": blueprint_id,
                    "version": version,
                    "digest": digest,
                }
                for blueprint_id, version, digest in self.blueprint_digests
            ],
            "coupling_policy_digests": [
                {
                    "template_id": template_id,
                    "version": version,
                    "digest": digest,
                }
                for template_id, version, digest in self.coupling_policy_digests
            ],
            "system_contract_digest": self.system_contract_digest,
            "validation_implementations": list(self.validation_implementations),
        }

    @property
    def digest(self) -> str:
        return hashlib.sha256(
            json.dumps(
                self.to_dict(),
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
        ).hexdigest()


def snapshot_composition_pack(
    registration: RegisteredCompositionPack,
) -> CompositionPackSnapshot:
    manifest = registration.manifest
    return CompositionPackSnapshot(
        pack_id=manifest.pack_id,
        pack_version=manifest.pack_version,
        manifest_digest=manifest.digest,
        dependency_manifests=tuple(
            (
                item.pack_id,
                item.pack_version,
                item.manifest_digest,
            )
            for item in manifest.requires_domain_packs
        ),
        blueprint_digests=tuple(
            (item.blueprint_id, item.version, item.digest)
            for item in manifest.blueprints
        ),
        coupling_policy_digests=tuple(
            (item.template_id, item.version, item.digest)
            for item in manifest.coupling_policies
        ),
        system_contract_digest=manifest.system_contract_digest,
        validation_implementations=tuple(
            item.to_dict()
            for item in registration.validation_fingerprints
        ),
    )


__all__ = [
    "COMPOSITION_SNAPSHOT_SCHEMA",
    "CompositionPackSnapshot",
    "snapshot_composition_pack",
]
