"""Versioned manifest for cross-domain Composition Packs.

A Composition Pack owns no domain model. It references exact Domain Packs and
owns only the system-level relationships between their artifacts.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Mapping

from ..domainpacks.manifest import ArtifactRef
from .errors import InvalidCompositionPackManifest

COMPOSITION_PACK_SCHEMA = "forge.composition_pack/1"
COMPOSITION_PACK_API = "forge.compositionpack_api/1"

_ID = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*$")


def _text(value: object, field: str) -> str:
    text = str(value).strip()
    if not text:
        raise InvalidCompositionPackManifest(f"{field} must be non-empty")
    return text


def _id(value: object, field: str) -> str:
    text = _text(value, field)
    if not _ID.fullmatch(text):
        raise InvalidCompositionPackManifest(
            f"{field} {text!r} must be lowercase dotted identifier segments"
        )
    return text


def _sha(value: object, field: str) -> str:
    text = str(value).strip().lower()
    if (
        len(text) != 64
        or any(ch not in "0123456789abcdef" for ch in text)
    ):
        raise InvalidCompositionPackManifest(
            f"{field} must be sha256 hex"
        )
    return text


@dataclass(frozen=True, order=True)
class DomainPackDependency:
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
    def from_dict(cls, payload: Mapping[str, Any]) -> "DomainPackDependency":
        if set(payload) != {"pack_id", "pack_version", "manifest_digest"}:
            raise InvalidCompositionPackManifest(
                "domain dependency shape mismatch"
            )
        return cls(
            payload["pack_id"],
            payload["pack_version"],
            payload["manifest_digest"],
        )


@dataclass(frozen=True, order=True)
class BlueprintRef:
    blueprint_id: str
    version: str
    digest: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "blueprint_id", _id(self.blueprint_id, "blueprint_id")
        )
        object.__setattr__(self, "version", _text(self.version, "version"))
        object.__setattr__(self, "digest", _sha(self.digest, "digest"))

    @property
    def key(self) -> tuple[str, str]:
        return self.blueprint_id, self.version

    def to_dict(self) -> dict[str, str]:
        return {
            "blueprint_id": self.blueprint_id,
            "version": self.version,
            "digest": self.digest,
        }

    @classmethod
    def from_blueprint(cls, blueprint: Any) -> "BlueprintRef":
        payload = blueprint.to_dict()
        digest = hashlib.sha256(
            json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
        ).hexdigest()
        return cls(blueprint.blueprint_id, blueprint.version, digest)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "BlueprintRef":
        if set(payload) != {"blueprint_id", "version", "digest"}:
            raise InvalidCompositionPackManifest(
                "blueprint ref shape mismatch"
            )
        return cls(
            payload["blueprint_id"],
            payload["version"],
            payload["digest"],
        )


@dataclass(frozen=True)
class PolicyTemplateRef:
    template_id: str
    version: str
    digest: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "template_id", _id(self.template_id, "template_id")
        )
        object.__setattr__(self, "version", _text(self.version, "version"))
        object.__setattr__(self, "digest", _sha(self.digest, "digest"))

    @property
    def key(self) -> tuple[str, str]:
        return self.template_id, self.version

    def to_dict(self) -> dict[str, str]:
        return {
            "template_id": self.template_id,
            "version": self.version,
            "digest": self.digest,
        }

    @classmethod
    def from_template(cls, template: Any) -> "PolicyTemplateRef":
        payload = template.to_dict()
        digest = hashlib.sha256(
            json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
        ).hexdigest()
        return cls(template.template_id, template.version, digest)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "PolicyTemplateRef":
        if set(payload) != {"template_id", "version", "digest"}:
            raise InvalidCompositionPackManifest(
                "policy template ref shape mismatch"
            )
        return cls(
            payload["template_id"],
            payload["version"],
            payload["digest"],
        )


@dataclass(frozen=True)
class CompositionPackManifest:
    pack_id: str
    pack_version: str
    compatible_core_apis: tuple[str, ...]
    requires_domain_packs: tuple[DomainPackDependency, ...]
    capabilities: tuple[str, ...]
    blueprints: tuple[BlueprintRef, ...]
    coupling_policies: tuple[PolicyTemplateRef, ...]
    system_contract_digest: str
    validation_protocols: tuple[ArtifactRef, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "pack_id", _id(self.pack_id, "pack_id"))
        object.__setattr__(
            self, "pack_version", _text(self.pack_version, "pack_version")
        )
        apis = tuple(
            sorted({_text(item, "compatible_core_api") for item in self.compatible_core_apis})
        )
        if not apis:
            raise InvalidCompositionPackManifest(
                "compatible_core_apis may not be empty"
            )
        object.__setattr__(self, "compatible_core_apis", apis)

        deps = tuple(sorted(self.requires_domain_packs))
        if len({item.key for item in deps}) != len(deps):
            raise InvalidCompositionPackManifest(
                "requires_domain_packs contains duplicate pack identities"
            )
        if len(deps) < 2:
            raise InvalidCompositionPackManifest(
                "CompositionPack must reference at least two Domain Packs; "
                "single-domain graph declarations belong with domain/product "
                "configuration, not cross-domain authority"
            )
        object.__setattr__(self, "requires_domain_packs", deps)

        capabilities = tuple(sorted({_id(item, "capability") for item in self.capabilities}))
        if not capabilities:
            raise InvalidCompositionPackManifest(
                "CompositionPack requires at least one system capability"
            )
        object.__setattr__(self, "capabilities", capabilities)

        blueprints = tuple(sorted(self.blueprints))
        if not blueprints:
            raise InvalidCompositionPackManifest(
                "CompositionPack requires at least one blueprint"
            )
        if len({item.key for item in blueprints}) != len(blueprints):
            raise InvalidCompositionPackManifest(
                "CompositionPack contains duplicate blueprint identities"
            )
        object.__setattr__(self, "blueprints", blueprints)

        policies = tuple(sorted(self.coupling_policies))
        if not policies:
            raise InvalidCompositionPackManifest(
                "CompositionPack requires at least one coupling policy template"
            )
        if len({item.key for item in policies}) != len(policies):
            raise InvalidCompositionPackManifest(
                "CompositionPack contains duplicate coupling policy identities"
            )
        object.__setattr__(self, "coupling_policies", policies)
        object.__setattr__(
            self,
            "system_contract_digest",
            _sha(self.system_contract_digest, "system_contract_digest"),
        )

        protocols = tuple(sorted(self.validation_protocols))
        if len(set(protocols)) != len(protocols):
            raise InvalidCompositionPackManifest(
                "duplicate composition validation protocol identities"
            )
        object.__setattr__(self, "validation_protocols", protocols)

    @property
    def key(self) -> tuple[str, str]:
        return self.pack_id, self.pack_version

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": COMPOSITION_PACK_SCHEMA,
            "pack_id": self.pack_id,
            "pack_version": self.pack_version,
            "compatible_core_apis": list(self.compatible_core_apis),
            "requires_domain_packs": [
                item.to_dict() for item in self.requires_domain_packs
            ],
            "capabilities": list(self.capabilities),
            "blueprints": [item.to_dict() for item in self.blueprints],
            "coupling_policies": [
                item.to_dict() for item in self.coupling_policies
            ],
            "system_contract_digest": self.system_contract_digest,
            "validation_protocols": [
                item.to_dict() for item in self.validation_protocols
            ],
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
    def from_dict(cls, payload: Mapping[str, Any]) -> "CompositionPackManifest":
        if payload.get("schema") != COMPOSITION_PACK_SCHEMA:
            raise InvalidCompositionPackManifest(
                f"unsupported schema {payload.get('schema')!r}"
            )
        expected = {
            "schema",
            "pack_id",
            "pack_version",
            "compatible_core_apis",
            "requires_domain_packs",
            "capabilities",
            "blueprints",
            "coupling_policies",
            "system_contract_digest",
            "validation_protocols",
        }
        if set(payload) != expected:
            raise InvalidCompositionPackManifest(
                "composition pack manifest shape mismatch"
            )
        return cls(
            pack_id=payload["pack_id"],
            pack_version=payload["pack_version"],
            compatible_core_apis=tuple(payload["compatible_core_apis"]),
            requires_domain_packs=tuple(
                DomainPackDependency.from_dict(item)
                for item in payload["requires_domain_packs"]
            ),
            capabilities=tuple(payload["capabilities"]),
            blueprints=tuple(
                BlueprintRef.from_dict(item)
                for item in payload["blueprints"]
            ),
            coupling_policies=tuple(
                PolicyTemplateRef.from_dict(item)
                for item in payload["coupling_policies"]
            ),
            system_contract_digest=payload["system_contract_digest"],
            validation_protocols=tuple(
                ArtifactRef.from_dict(item)
                for item in payload["validation_protocols"]
            ),
        )


__all__ = [
    "BlueprintRef",
    "COMPOSITION_PACK_API",
    "COMPOSITION_PACK_SCHEMA",
    "CompositionPackManifest",
    "DomainPackDependency",
    "PolicyTemplateRef",
]
