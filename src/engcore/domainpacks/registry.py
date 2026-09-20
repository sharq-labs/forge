"""Deterministic Domain Pack registry with explicit enablement."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

from ..scientific.capabilities import ScientificCapability
from .errors import DuplicateDomainPack, DomainPackNotEnabled, DomainPackNotFound
from .authority import SemanticAuthoritySnapshot, bind_semantic_authority
from .frozen import (
    ArtifactImplementationFingerprint,
    FrozenDomainPackProvider,
    freeze_domain_pack_provider,
)
from .provider import DomainPackProvider
from .validation import DomainPackValidationReport, validate_domain_pack


@dataclass(frozen=True)
class PackOrigin:
    kind: str
    distribution_name: str | None = None
    distribution_version: str | None = None
    entry_point: str | None = None

    @classmethod
    def builtin(cls) -> "PackOrigin":
        return cls("builtin")

    @classmethod
    def external(
        cls,
        *,
        distribution_name: str,
        distribution_version: str,
        entry_point: str,
    ) -> "PackOrigin":
        return cls(
            "entry_point",
            str(distribution_name),
            str(distribution_version),
            str(entry_point),
        )


@dataclass(frozen=True)
class RegisteredDomainPack:
    provider: FrozenDomainPackProvider
    validation: DomainPackValidationReport
    origin: PackOrigin
    implementation_fingerprints: tuple[
        ArtifactImplementationFingerprint, ...
    ]
    implementation_digest: str
    semantic_authority: SemanticAuthoritySnapshot | None = None

    @property
    def manifest(self):
        return self.provider.manifest


class DomainPackRegistry:
    """Registration proves validity; enablement is a separate explicit act."""

    def __init__(self) -> None:
        self._packs: dict[tuple[str, str], RegisteredDomainPack] = {}
        self._enabled: set[tuple[str, str]] = set()

    def register(
        self,
        provider: DomainPackProvider,
        *,
        origin: PackOrigin | None = None,
    ) -> RegisteredDomainPack:
        manifest = getattr(provider, "manifest", None)
        semantic_authority = bind_semantic_authority(
            provider,
            manifest,
        )
        frozen = freeze_domain_pack_provider(
            provider,
            manifest=manifest,
        )
        return self.register_frozen(
            frozen,
            semantic_authority=semantic_authority,
            origin=origin,
        )

    def register_frozen(
        self,
        frozen,
        *,
        semantic_authority: SemanticAuthoritySnapshot | None = None,
        origin: PackOrigin | None = None,
    ) -> RegisteredDomainPack:
        from .frozen import FrozenDomainPack

        if not isinstance(frozen, FrozenDomainPack):
            raise TypeError("register_frozen requires FrozenDomainPack")
        report = validate_domain_pack(frozen.provider)
        report.require_valid()
        key = frozen.manifest.key
        if key in self._packs:
            raise DuplicateDomainPack(
                f"domain pack {key[0]}@{key[1]} is already registered"
            )
        registration = RegisteredDomainPack(
            provider=frozen.provider,
            validation=report,
            origin=origin or PackOrigin.builtin(),
            implementation_fingerprints=(
                frozen.implementation_fingerprints
            ),
            implementation_digest=frozen.implementation_digest,
            semantic_authority=semantic_authority,
        )
        self._packs[key] = registration
        return registration

    def enable(self, pack_id: str, pack_version: str) -> None:
        key = (str(pack_id), str(pack_version))
        if key not in self._packs:
            raise DomainPackNotFound(
                f"cannot enable unregistered domain pack {key[0]}@{key[1]}"
            )
        self._enabled.add(key)

    def disable(self, pack_id: str, pack_version: str) -> None:
        self._enabled.discard((str(pack_id), str(pack_version)))

    def is_enabled(self, pack_id: str, pack_version: str) -> bool:
        return (str(pack_id), str(pack_version)) in self._enabled

    def get(
        self,
        pack_id: str,
        pack_version: str,
        *,
        require_enabled: bool = False,
    ) -> RegisteredDomainPack:
        key = (str(pack_id), str(pack_version))
        try:
            registration = self._packs[key]
        except KeyError:
            available = ", ".join(f"{p}@{v}" for p, v in sorted(self._packs)) or "<empty>"
            raise DomainPackNotFound(
                f"no domain pack {key[0]}@{key[1]}; available: {available}"
            ) from None
        if require_enabled and key not in self._enabled:
            raise DomainPackNotEnabled(
                f"domain pack {key[0]}@{key[1]} is registered but not enabled"
            )
        return registration

    def list(self, *, enabled_only: bool = False) -> tuple[RegisteredDomainPack, ...]:
        keys = sorted(self._enabled if enabled_only else self._packs)
        return tuple(self._packs[key] for key in keys)

    def providing(
        self,
        capability: ScientificCapability | str,
        *,
        enabled_only: bool = True,
    ) -> tuple[RegisteredDomainPack, ...]:
        wanted = ScientificCapability.coerce(capability).identifier
        registrations = self.list(enabled_only=enabled_only)
        return tuple(
            item for item in registrations if wanted in item.manifest.capabilities
        )

    def __len__(self) -> int:
        return len(self._packs)

    def __iter__(self) -> Iterator[RegisteredDomainPack]:
        return iter(self.list())
