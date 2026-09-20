"""Replayable provenance snapshot for a registered Composition Pack."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping

from ..scientific.serialization import require_schema_any
from .registry import RegisteredCompositionPack

COMPOSITION_SNAPSHOT_SCHEMA_V1 = "forge.composition_pack_snapshot/1"
COMPOSITION_SNAPSHOT_SCHEMA_V2 = "forge.composition_pack_snapshot/2"
COMPOSITION_SNAPSHOT_SCHEMA = "forge.composition_pack_snapshot/3"


@dataclass(frozen=True)
class CompositionPackSnapshot:
    pack_id: str
    pack_version: str
    manifest_digest: str
    dependency_manifests: tuple[tuple[str, str, str], ...]
    blueprint_digests: tuple[tuple[str, str, str], ...]
    coupling_policy_digests: tuple[tuple[str, str, str], ...]
    system_contract_digest: str
    claim_capability_digests: tuple[tuple[str, str, str], ...]
    validation_implementations: tuple[dict[str, str], ...]
    dependency_authority_digests: tuple[tuple[str, str, str], ...]
    authority_digest: str
    uncertainty_implementations: tuple[dict[str, str], ...] = ()
    verification_implementations: tuple[dict[str, str], ...] = ()
    semantic_authority: dict[str, Any] | None = None

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
            "claim_capability_digests": [
                {
                    "capability_id": capability_id,
                    "version": version,
                    "digest": digest,
                }
                for capability_id, version, digest
                in self.claim_capability_digests
            ],
            "validation_implementations": list(
                self.validation_implementations
            ),
            "uncertainty_implementations": list(
                self.uncertainty_implementations
            ),
            "verification_implementations": list(
                self.verification_implementations
            ),
            "semantic_authority": self.semantic_authority,
            "dependency_authority_digests": [
                {
                    "pack_id": pack_id,
                    "pack_version": version,
                    "authority_digest": digest,
                }
                for pack_id, version, digest
                in self.dependency_authority_digests
            ],
            "authority_digest": self.authority_digest,
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

    @classmethod
    def from_dict(
        cls,
        payload: Mapping[str, Any],
    ) -> "CompositionPackSnapshot":
        schema = require_schema_any(
            payload,
            (
                COMPOSITION_SNAPSHOT_SCHEMA_V1,
                COMPOSITION_SNAPSHOT_SCHEMA_V2,
                COMPOSITION_SNAPSHOT_SCHEMA,
            ),
        )

        def deps(items, digest_key):
            return tuple(
                (
                    item["pack_id"],
                    item["pack_version"],
                    item[digest_key],
                )
                for item in items
            )

        made = cls(
            pack_id=payload["pack_id"],
            pack_version=payload["pack_version"],
            manifest_digest=payload["manifest_digest"],
            dependency_manifests=deps(
                payload.get("dependency_manifests", ()),
                "manifest_digest",
            ),
            blueprint_digests=tuple(
                (
                    item["blueprint_id"],
                    item["version"],
                    item["digest"],
                )
                for item in payload.get("blueprint_digests", ())
            ),
            coupling_policy_digests=tuple(
                (
                    item["template_id"],
                    item["version"],
                    item["digest"],
                )
                for item in payload.get("coupling_policy_digests", ())
            ),
            system_contract_digest=payload["system_contract_digest"],
            claim_capability_digests=tuple(
                (
                    item["capability_id"],
                    item["version"],
                    item["digest"],
                )
                for item in payload.get("claim_capability_digests", ())
            ),
            validation_implementations=tuple(
                dict(item)
                for item in payload.get(
                    "validation_implementations", ()
                )
            ),
            uncertainty_implementations=(
                ()
                if schema == COMPOSITION_SNAPSHOT_SCHEMA_V1
                else tuple(
                    dict(item)
                    for item in payload.get(
                        "uncertainty_implementations", ()
                    )
                )
            ),
            verification_implementations=(
                ()
                if schema == COMPOSITION_SNAPSHOT_SCHEMA_V1
                else tuple(
                    dict(item)
                    for item in payload.get(
                        "verification_implementations", ()
                    )
                )
            ),
            semantic_authority=(
                None
                if schema in (
                    COMPOSITION_SNAPSHOT_SCHEMA_V1,
                    COMPOSITION_SNAPSHOT_SCHEMA_V2,
                )
                else dict(payload["semantic_authority"])
            ),
            dependency_authority_digests=deps(
                payload.get("dependency_authority_digests", ()),
                "authority_digest",
            ),
            authority_digest=payload["authority_digest"],
        )
        return made


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
        claim_capability_digests=tuple(
            (
                item.capability_id,
                item.version,
                item.digest,
            )
            for item in registration.claim_capabilities
        ),
        validation_implementations=tuple(
            item.to_dict()
            for item in registration.validation_fingerprints
        ),
        uncertainty_implementations=tuple(
            item.to_dict()
            for item in registration.uncertainty_fingerprints
        ),
        verification_implementations=tuple(
            item.to_dict()
            for item in registration.verification_fingerprints
        ),
        semantic_authority=registration.semantic_authority.to_dict(),
        dependency_authority_digests=(
            registration.dependency_authority_digests
        ),
        authority_digest=registration.authority_digest,
    )


__all__ = [
    "COMPOSITION_SNAPSHOT_SCHEMA",
    "COMPOSITION_SNAPSHOT_SCHEMA_V1",
    "COMPOSITION_SNAPSHOT_SCHEMA_V2",
    "CompositionPackSnapshot",
    "snapshot_composition_pack",
]
