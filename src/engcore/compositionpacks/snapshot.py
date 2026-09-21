"""Replayable provenance snapshot for a registered Composition Pack."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping

from ..scientific.serialization import require_schema_any
from ..scientific.results.immutable import detach, freeze
from .registry import RegisteredCompositionPack

COMPOSITION_SNAPSHOT_SCHEMA_V1 = "forge.composition_pack_snapshot/1"
COMPOSITION_SNAPSHOT_SCHEMA_V2 = "forge.composition_pack_snapshot/2"
COMPOSITION_SNAPSHOT_SCHEMA_V3 = "forge.composition_pack_snapshot/3"
#: V4 carries the blueprint-scoped REQUIREMENTS, not just the pinned
#: implementations. A certification gate asking "did every required protocol
#: run?" needs the required set, and fingerprints alone do not say which
#: blueprint each protocol belongs to. Snapshots written before V4 carry empty
#: requirement tuples, which the completeness gates report as unenforceable
#: rather than as satisfied.
COMPOSITION_SNAPSHOT_SCHEMA = "forge.composition_pack_snapshot/4"


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
    protocol_requirements: tuple[dict[str, str], ...] = ()
    uncertainty_requirements: tuple[dict[str, str], ...] = ()
    #: WHETHER the required sets are stated, which is not the same question
    #: as whether they are non-empty. A V4 pack that genuinely requires no
    #: protocol for a blueprint has declared an empty requirement, and its
    #: completeness is enforceable and exactly satisfied by executing
    #: nothing. A pre-V4 snapshot has declared nothing at all and cannot be
    #: enforced. Reading emptiness as 'old' conflated the two.
    requirements_declared: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "validation_implementations",
            tuple(
                freeze(dict(item))
                for item in self.validation_implementations
            ),
        )
        object.__setattr__(
            self,
            "uncertainty_implementations",
            tuple(
                freeze(dict(item))
                for item in self.uncertainty_implementations
            ),
        )
        object.__setattr__(
            self,
            "verification_implementations",
            tuple(
                freeze(dict(item))
                for item in self.verification_implementations
            ),
        )
        for label in ("protocol_requirements", "uncertainty_requirements"):
            object.__setattr__(
                self,
                label,
                tuple(
                    freeze(dict(item))
                    for item in sorted(
                        getattr(self, label),
                        key=lambda item: tuple(
                            str(item[key]) for key in sorted(item)
                        ),
                    )
                ),
            )
        if self.semantic_authority is not None:
            object.__setattr__(
                self,
                "semantic_authority",
                freeze(dict(self.semantic_authority)),
            )

    def required_protocols(self, blueprint_id: str, kind: str) -> frozenset[tuple[str, str]]:
        """Which (artifact_id, version) protocols this blueprint requires.

        Empty may mean "requires none" or "cannot say"; the two are
        distinguished by :attr:`declares_requirements`, not by this set.
        """
        return frozenset(
            (str(item["artifact_id"]), str(item["version"]))
            for item in self.protocol_requirements
            if str(item.get("blueprint_id")) == str(blueprint_id)
            and str(item.get("kind")) == str(kind)
        )

    def required_uncertainty_cells(
        self, blueprint_id: str
    ) -> frozenset[tuple[str, str]]:
        """The (quantity, channel) cells this blueprint's producers must cover."""
        return frozenset(
            (str(item["quantity"]), str(item["channel"]))
            for item in self.uncertainty_requirements
            if str(item.get("blueprint_id")) == str(blueprint_id)
        )

    @property
    def declares_requirements(self) -> bool:
        """Whether this snapshot states its required sets at all.

        An explicit flag rather than ``bool(self.protocol_requirements)``. The
        tuple being empty answers a different question -- "is the required set
        empty" -- and using it as a version probe made "declares zero required
        protocols" indistinguishable from "predates requirements", so a pack
        that correctly requires nothing was reported unenforceable.
        """
        return bool(self.requirements_declared)

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
            "validation_implementations": detach(
                self.validation_implementations
            ),
            "uncertainty_implementations": detach(
                self.uncertainty_implementations
            ),
            "verification_implementations": detach(
                self.verification_implementations
            ),
            "semantic_authority": detach(self.semantic_authority),
            "requirements_declared": self.requirements_declared,
            "protocol_requirements": detach(self.protocol_requirements),
            "uncertainty_requirements": detach(
                self.uncertainty_requirements
            ),
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
                COMPOSITION_SNAPSHOT_SCHEMA_V3,
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
            # A pre-V4 snapshot declared nothing, whatever its tuples look
            # like. A V4 payload says so explicitly, and defaults to True for a
            # V4 writer that predates the flag itself.
            requirements_declared=(
                False
                if schema
                in (
                    COMPOSITION_SNAPSHOT_SCHEMA_V1,
                    COMPOSITION_SNAPSHOT_SCHEMA_V2,
                    COMPOSITION_SNAPSHOT_SCHEMA_V3,
                )
                else bool(payload.get("requirements_declared", True))
            ),
            protocol_requirements=tuple(
                dict(item) for item in payload.get("protocol_requirements", ())
            ),
            uncertainty_requirements=tuple(
                dict(item)
                for item in payload.get("uncertainty_requirements", ())
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
        # A live registration always knows its requirements, including when
        # they are empty.
        requirements_declared=True,
        # THE REQUIRED SETS, scoped to the blueprint that requires them. Without
        # these a completeness gate can only ask whether something ran.
        protocol_requirements=tuple(
            {
                "blueprint_id": item.blueprint_id,
                "kind": kind,
                "artifact_id": item.ref.artifact_id,
                "version": item.ref.version,
            }
            for kind, records in (
                ("validation", registration.validation_protocols),
                ("verification", registration.verification_protocols),
                ("uncertainty", registration.uncertainty_producers),
            )
            for item in records
        ),
        uncertainty_requirements=tuple(
            {
                "blueprint_id": item.blueprint_id,
                "artifact_id": item.ref.artifact_id,
                "version": item.ref.version,
                "quantity": quantity,
                "channel": channel.value,
            }
            for item in registration.uncertainty_producers
            for quantity in item.quantities
            for channel in item.channels
        ),
        dependency_authority_digests=(
            registration.dependency_authority_digests
        ),
        authority_digest=registration.authority_digest,
    )


__all__ = [
    "COMPOSITION_SNAPSHOT_SCHEMA",
    "COMPOSITION_SNAPSHOT_SCHEMA_V1",
    "COMPOSITION_SNAPSHOT_SCHEMA_V2",
    "COMPOSITION_SNAPSHOT_SCHEMA_V3",
    "CompositionPackSnapshot",
    "snapshot_composition_pack",
]
