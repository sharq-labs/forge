"""Admission registry for executable adapters separated from system science."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Iterator

from ..compositionpacks.registry import CompositionPackRegistry
from ..domainpacks.frozen import implementation_fingerprint
from ..domainpacks.registry import DomainPackRegistry
from ..execution.multiphysics import (
    ParticipantFactoryDeclaration,
    ParticipantFactoryRegistry,
)
from .errors import (
    DuplicateExecutionPack,
    ExecutionDependencyError,
    ExecutionPackNotEnabled,
    ExecutionPackNotFound,
    InvalidExecutionPackProvider,
)
from .manifest import (
    EXECUTION_PACK_API,
    ExecutionPackManifest,
    ParticipantFactoryRef,
)
from .provider import ExecutionPackProvider


@dataclass(frozen=True)
class RegisteredExecutionPack:
    manifest: ExecutionPackManifest
    participant_factories: tuple[ParticipantFactoryDeclaration, ...]
    composition_authority_digest: str
    source_provider_type: str

    @property
    def key(self) -> tuple[str, str]:
        return self.manifest.key

    @property
    def pack_id(self) -> str:
        return self.manifest.pack_id

    @property
    def pack_version(self) -> str:
        return self.manifest.pack_version

    @property
    def authority_digest(self) -> str:
        payload = {
            "manifest_digest": self.manifest.digest,
            "composition_authority_digest": (
                self.composition_authority_digest
            ),
        }
        return hashlib.sha256(
            json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()


def _factory_ref(
    declaration: ParticipantFactoryDeclaration,
) -> ParticipantFactoryRef:
    digest, _basis = implementation_fingerprint(declaration.factory)
    return ParticipantFactoryRef(
        model_id=declaration.model_id,
        model_version=declaration.model_version,
        realization_id=declaration.realization_id,
        realization_version=declaration.realization_version,
        solver_id=declaration.solver_id,
        solver_version=declaration.solver_version,
        adapter_id=declaration.adapter_id,
        adapter_version=declaration.adapter_version,
        implementation_digest=digest,
        models=declaration.models,
    )


def _domain_artifacts(composition, domain_packs: DomainPackRegistry):
    registrations = tuple(
        domain_packs.get(
            item.pack_id,
            item.pack_version,
            require_enabled=True,
        )
        for item in composition.manifest.requires_domain_packs
    )
    models = {}
    realizations = {}
    solvers = {}
    for registration in registrations:
        for model in registration.provider.models():
            models.setdefault(model.key, []).append(
                (registration, model)
            )
        for realization in registration.provider.realizations():
            realizations.setdefault(realization.key, []).append(
                (registration, realization)
            )
        for factory in registration.provider.solver_factories():
            probe = factory()
            solvers.setdefault(probe.identity.key, []).append(
                (registration, probe)
            )
    return registrations, models, realizations, solvers


class ExecutionPackRegistry:
    def __init__(self) -> None:
        self._packs: dict[
            tuple[str, str], RegisteredExecutionPack
        ] = {}
        self._enabled: set[tuple[str, str]] = set()

    def register(
        self,
        provider: ExecutionPackProvider,
        *,
        compositions: CompositionPackRegistry,
        domain_packs: DomainPackRegistry,
    ) -> RegisteredExecutionPack:
        manifest = getattr(provider, "manifest", None)
        if not isinstance(manifest, ExecutionPackManifest):
            raise InvalidExecutionPackProvider(
                "execution provider manifest must be ExecutionPackManifest"
            )
        if EXECUTION_PACK_API not in manifest.compatible_core_apis:
            raise InvalidExecutionPackProvider(
                "execution pack does not declare compatibility with "
                f"{EXECUTION_PACK_API}"
            )
        if manifest.key in self._packs:
            raise DuplicateExecutionPack(
                f"execution pack {manifest.pack_id}@"
                f"{manifest.pack_version} is already registered"
            )

        composition = compositions.get(
            manifest.composition.pack_id,
            manifest.composition.pack_version,
            require_enabled=True,
        )
        if composition.manifest.digest != manifest.composition.manifest_digest:
            raise ExecutionDependencyError(
                "execution pack composition digest mismatch; expected "
                f"{manifest.composition.manifest_digest}, registered "
                f"{composition.manifest.digest}"
            )

        try:
            declarations = tuple(provider.participant_factories())
        except Exception as exc:
            raise InvalidExecutionPackProvider(
                "participant_factories() failed during execution admission"
            ) from exc
        if any(
            not isinstance(item, ParticipantFactoryDeclaration)
            for item in declarations
        ):
            raise InvalidExecutionPackProvider(
                "participant_factories() must return "
                "ParticipantFactoryDeclaration records only"
            )
        if len({item.key for item in declarations}) != len(declarations):
            raise InvalidExecutionPackProvider(
                "participant_factories() contains duplicate identities"
            )

        actual_refs = tuple(
            sorted(_factory_ref(item) for item in declarations)
        )
        if actual_refs != manifest.participant_factories:
            raise InvalidExecutionPackProvider(
                "execution manifest participant factory identities or "
                "implementation digests disagree with provider"
            )

        _registrations, models, realizations, solvers = _domain_artifacts(
            composition,
            domain_packs,
        )

        participant_roles = [
            participant
            for blueprint in composition.blueprints
            for participant in blueprint.participants
        ]
        role_keys = {
            (
                participant.model_keys,
                participant.adapter_id,
                participant.adapter_version,
            )
            for participant in participant_roles
        }

        for declaration in declarations:
            role_key = (
                declaration.model_keys,
                declaration.adapter_id,
                declaration.adapter_version,
            )
            if role_key not in role_keys:
                raise InvalidExecutionPackProvider(
                    "participant factory does not correspond to any "
                    "composition participant role: "
                    f"{role_key}"
                )

            for model_key in declaration.model_keys:
                model_matches = models.get(model_key, [])
                if len(model_matches) != 1:
                    raise InvalidExecutionPackProvider(
                        f"factory model {model_key} resolves to "
                        f"{len(model_matches)} exact Domain Pack artifacts"
                    )

            realization_key = (
                declaration.realization_id,
                declaration.realization_version,
            )
            realization_matches = realizations.get(realization_key, [])
            if len(realization_matches) != 1:
                raise InvalidExecutionPackProvider(
                    f"factory realization {realization_key} resolves to "
                    f"{len(realization_matches)} exact domain artifacts"
                )
            realization = realization_matches[0][1]
            if realization.model_key != (
                declaration.model_id,
                declaration.model_version,
            ):
                raise InvalidExecutionPackProvider(
                    f"factory realization {realization_key} implements "
                    f"{realization.model_key}, not declared model "
                    f"{declaration.model_id}@{declaration.model_version}"
                )

            solver_key = (
                declaration.solver_id,
                declaration.solver_version,
            )
            solver_matches = solvers.get(solver_key, [])
            if len(solver_matches) != 1:
                raise InvalidExecutionPackProvider(
                    f"factory solver {solver_key} resolves to "
                    f"{len(solver_matches)} exact domain artifacts"
                )
            solver = solver_matches[0][1]
            required_solver_caps = {
                item.name
                for item in realization.required_solver_capabilities
            }
            declared_solver_caps = {
                item.name for item in solver.capabilities
            }
            served_models = {
                item.key for item in solver.served_models
            }
            if served_models:
                unsupported_models = sorted(
                    set(declaration.model_keys) - served_models
                )
                if unsupported_models:
                    raise InvalidExecutionPackProvider(
                        f"factory solver {solver_key} does not declare support "
                        f"for participant model assembly members "
                        f"{unsupported_models}"
                    )
            missing_solver_caps = sorted(
                required_solver_caps - declared_solver_caps
            )
            if missing_solver_caps:
                raise InvalidExecutionPackProvider(
                    f"factory solver {solver_key} lacks realization-required "
                    f"solver capabilities {missing_solver_caps}"
                )

        uncovered = []
        for role_key in sorted(role_keys):
            if not any(
                (
                    item.model_keys,
                    item.adapter_id,
                    item.adapter_version,
                )
                == role_key
                for item in declarations
            ):
                uncovered.append(role_key)
        if uncovered:
            raise InvalidExecutionPackProvider(
                "execution pack leaves composition participant roles "
                f"without executable factories: {uncovered}"
            )

        registration = RegisteredExecutionPack(
            manifest=manifest,
            participant_factories=tuple(
                sorted(declarations, key=lambda item: item.key)
            ),
            composition_authority_digest=composition.authority_digest,
            source_provider_type=(
                f"{type(provider).__module__}."
                f"{type(provider).__qualname__}"
            ),
        )
        self._packs[registration.key] = registration
        return registration

    def enable(self, pack_id: str, pack_version: str) -> None:
        key = str(pack_id), str(pack_version)
        if key not in self._packs:
            raise ExecutionPackNotFound(
                f"cannot enable unregistered execution pack "
                f"{key[0]}@{key[1]}"
            )
        self._enabled.add(key)

    def disable(self, pack_id: str, pack_version: str) -> None:
        self._enabled.discard((str(pack_id), str(pack_version)))

    def get(
        self,
        pack_id: str,
        pack_version: str,
        *,
        require_enabled: bool = False,
    ) -> RegisteredExecutionPack:
        key = str(pack_id), str(pack_version)
        try:
            registration = self._packs[key]
        except KeyError:
            raise ExecutionPackNotFound(
                f"no execution pack {key[0]}@{key[1]}"
            ) from None
        if require_enabled and key not in self._enabled:
            raise ExecutionPackNotEnabled(
                f"execution pack {key[0]}@{key[1]} is not enabled"
            )
        return registration

    def list(
        self,
        *,
        enabled_only: bool = False,
    ) -> tuple[RegisteredExecutionPack, ...]:
        keys = sorted(self._enabled if enabled_only else self._packs)
        return tuple(self._packs[key] for key in keys)

    def for_composition(
        self,
        pack_id: str,
        pack_version: str,
        manifest_digest: str,
        *,
        enabled_only: bool = True,
    ) -> tuple[RegisteredExecutionPack, ...]:
        wanted = (
            str(pack_id),
            str(pack_version),
            str(manifest_digest).strip().lower(),
        )
        return tuple(
            registration
            for registration in self.list(enabled_only=enabled_only)
            if (
                registration.manifest.composition.pack_id,
                registration.manifest.composition.pack_version,
                registration.manifest.composition.manifest_digest,
            )
            == wanted
        )

    def participant_factory_registry(
        self,
        *,
        enabled_only: bool = True,
    ) -> ParticipantFactoryRegistry:
        by_key = {}
        refs = {}
        for registration in self.list(enabled_only=enabled_only):
            for declaration in registration.participant_factories:
                reference = _factory_ref(declaration)
                existing = by_key.get(declaration.key)
                if existing is None:
                    by_key[declaration.key] = declaration
                    refs[declaration.key] = reference
                    continue
                if refs[declaration.key] != reference:
                    raise InvalidExecutionPackProvider(
                        "enabled ExecutionPacks provide conflicting factories "
                        f"for exact execution identity {declaration.key}"
                    )
        return ParticipantFactoryRegistry(
            by_key[key] for key in sorted(by_key)
        )

    def __iter__(self) -> Iterator[RegisteredExecutionPack]:
        return iter(self.list())


__all__ = [
    "ExecutionPackRegistry",
    "RegisteredExecutionPack",
]
