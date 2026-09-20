"""Application assembly for Domain, Composition and Execution Packs.

This module owns process-level product configuration. Scientific planning and
pack validation depend on it; MCP only re-exports it for compatibility and is
not an authority boundary.
"""

from __future__ import annotations

import os
from typing import Iterable

from ..claims.capabilities import CapabilityDeclaration
from ..compositionpacks import CompositionPackRegistry
from ..domainpacks.authority import bind_semantic_authority
from ..domainpacks.discovery import (
    DiscoveredDomainPack,
    discover_domain_packs,
    load_discovered_domain_pack,
)
from ..domainpacks.errors import (
    DomainPackDiscoveryError,
    InvalidDomainPackProvider,
)
from ..domainpacks.frozen import freeze_domain_pack_provider
from ..domainpacks.registry import DomainPackRegistry, PackOrigin
from ..executionpacks import ExecutionPackRegistry

ENV_DOMAIN_PACKS = "FORGE_DOMAIN_PACKS"

_PRODUCTION_DOMAIN_PACKS = DomainPackRegistry()
_PRODUCTION_COMPOSITIONS = CompositionPackRegistry()
_PRODUCTION_EXECUTIONS = ExecutionPackRegistry()
_PRODUCTION_DOMAIN_CLAIMS: dict[
    tuple[str, str], tuple[CapabilityDeclaration, ...]
] = {}
_ENV_CONFIGURED = False
_BUILTINS_CONFIGURED = False


def _claim_declarations(
    provider,
    manifest,
) -> tuple[CapabilityDeclaration, ...]:
    getter = getattr(provider, "claim_capabilities", None)
    if getter is None:
        return ()
    if not callable(getter):
        raise InvalidDomainPackProvider(
            "claim_capabilities must be a zero-argument callable when provided"
        )
    try:
        declarations = tuple(getter())
    except Exception as exc:
        raise InvalidDomainPackProvider(
            "provider.claim_capabilities() failed during production admission"
        ) from exc

    if any(
        not isinstance(item, CapabilityDeclaration)
        for item in declarations
    ):
        raise InvalidDomainPackProvider(
            "claim_capabilities() must return CapabilityDeclaration records only"
        )
    if len({item.capability_id for item in declarations}) != len(declarations):
        raise InvalidDomainPackProvider(
            "claim_capabilities() returned duplicate capability ids"
        )

    manifest_caps = frozenset(manifest.capabilities)
    model_keys = {
        (item.artifact_id, item.version) for item in manifest.models
    }
    solver_keys = {
        (item.artifact_id, item.version) for item in manifest.solvers
    }
    errors: list[str] = []
    for declaration in declarations:
        if declaration.domain != manifest.domain:
            errors.append(
                f"{declaration.capability_id}: domain "
                f"{declaration.domain!r} does not match pack domain "
                f"{manifest.domain!r}"
            )
        undeclared_science = sorted(
            item.capability.identifier
            for item in declaration.provides
            if item.capability.identifier not in manifest_caps
        )
        if undeclared_science:
            errors.append(
                f"{declaration.capability_id}: provides capabilities "
                f"outside the pack manifest: {undeclared_science}"
            )
        undeclared_models = sorted(
            f"{item.model_id}@{item.version}"
            for item in declaration.models
            if (item.model_id, item.version) not in model_keys
        )
        if undeclared_models:
            errors.append(
                f"{declaration.capability_id}: references models outside "
                f"the atomic pack: {undeclared_models}"
            )
        undeclared_solvers = sorted(
            f"{item.solver_id}@{item.version}"
            for item in declaration.solvers
            if (item.solver_id, item.version) not in solver_keys
        )
        if undeclared_solvers:
            errors.append(
                f"{declaration.capability_id}: references solvers outside "
                f"the atomic pack: {undeclared_solvers}"
            )
        if not declaration.executable:
            errors.append(
                f"{declaration.capability_id}: production domain capability "
                "has no executor"
            )
    if errors:
        raise InvalidDomainPackProvider(
            f"domain pack {manifest.pack_id}@{manifest.pack_version} "
            "claim routing is invalid: " + "; ".join(errors)
        )
    return tuple(
        sorted(declarations, key=lambda item: item.capability_id)
    )


def register_production_domain_pack(
    provider,
    *,
    origin: PackOrigin | None = None,
    enable: bool = True,
):
    """Freeze artifacts and claims from one provider before registry mutation."""

    manifest = getattr(provider, "manifest", None)
    semantic = bind_semantic_authority(provider, manifest)
    frozen = freeze_domain_pack_provider(
        provider,
        manifest=manifest,
    )
    claims = _claim_declarations(provider, frozen.manifest)

    registration = _PRODUCTION_DOMAIN_PACKS.register_frozen(
        frozen,
        semantic_authority=semantic,
        origin=origin,
    )
    _PRODUCTION_DOMAIN_CLAIMS[registration.manifest.key] = claims
    if enable:
        _PRODUCTION_DOMAIN_PACKS.enable(
            registration.manifest.pack_id,
            registration.manifest.pack_version,
        )
    return registration


def register_production_composition_pack(
    provider,
    *,
    enable: bool = True,
):
    registration = _PRODUCTION_COMPOSITIONS.register(
        provider,
        domain_packs=_PRODUCTION_DOMAIN_PACKS,
        require_enabled_dependencies=True,
    )
    if enable:
        _PRODUCTION_COMPOSITIONS.enable(
            registration.manifest.pack_id,
            registration.manifest.pack_version,
        )
    return registration


def register_production_execution_pack(
    provider,
    *,
    enable: bool = True,
):
    registration = _PRODUCTION_EXECUTIONS.register(
        provider,
        compositions=_PRODUCTION_COMPOSITIONS,
        domain_packs=_PRODUCTION_DOMAIN_PACKS,
    )
    if enable:
        _PRODUCTION_EXECUTIONS.enable(
            registration.manifest.pack_id,
            registration.manifest.pack_version,
        )
    return registration


def _configure_builtin_packs() -> DomainPackRegistry:
    global _BUILTINS_CONFIGURED
    if _BUILTINS_CONFIGURED:
        return _PRODUCTION_DOMAIN_PACKS

    from ..compositionpacks.builtin_electrothermal_feedback import (
        BUILTIN_ELECTROTHERMAL_FEEDBACK_COMPOSITION,
    )
    from ..compositionpacks.builtin_thermal_resistance import (
        BUILTIN_THERMAL_RESISTANCE_COMPOSITION,
    )
    from ..domainpacks.builtin_battery import BUILTIN_BATTERY_CELL_PACK
    from ..domainpacks.builtin_cstr import BUILTIN_CSTR_PACK
    from ..domainpacks.builtin_electrical_dc import (
        BUILTIN_ELECTRICAL_DC_PACK,
    )
    from ..domainpacks.builtin_electrical_material import (
        BUILTIN_ELECTRICAL_MATERIAL_PACK,
    )
    from ..domainpacks.builtin_thermal_lumped import (
        BUILTIN_THERMAL_LUMPED_PACK,
    )
    from ..executionpacks.builtin_electrothermal_feedback import (
        BUILTIN_ELECTROTHERMAL_FEEDBACK_EXECUTION,
    )
    from ..executionpacks.builtin_thermal_resistance import (
        BUILTIN_THERMAL_RESISTANCE_EXECUTION,
    )

    for provider in (
        BUILTIN_BATTERY_CELL_PACK,
        BUILTIN_CSTR_PACK,
        BUILTIN_THERMAL_LUMPED_PACK,
        BUILTIN_ELECTRICAL_MATERIAL_PACK,
        BUILTIN_ELECTRICAL_DC_PACK,
    ):
        register_production_domain_pack(
            provider,
            origin=PackOrigin.builtin(),
            enable=True,
        )

    register_production_composition_pack(
        BUILTIN_THERMAL_RESISTANCE_COMPOSITION,
        enable=True,
    )
    register_production_composition_pack(
        BUILTIN_ELECTROTHERMAL_FEEDBACK_COMPOSITION,
        enable=True,
    )
    register_production_execution_pack(
        BUILTIN_THERMAL_RESISTANCE_EXECUTION,
        enable=True,
    )
    register_production_execution_pack(
        BUILTIN_ELECTROTHERMAL_FEEDBACK_EXECUTION,
        enable=True,
    )

    _BUILTINS_CONFIGURED = True
    return _PRODUCTION_DOMAIN_PACKS


def production_domain_packs() -> DomainPackRegistry:
    return _configure_builtin_packs()


def production_composition_packs() -> CompositionPackRegistry:
    _configure_builtin_packs()
    return _PRODUCTION_COMPOSITIONS


def production_execution_packs() -> ExecutionPackRegistry:
    _configure_builtin_packs()
    return _PRODUCTION_EXECUTIONS


def _resolve_configured(
    requested: Iterable[str],
    discovered: tuple[DiscoveredDomainPack, ...],
) -> tuple[DiscoveredDomainPack, ...]:
    chosen: list[DiscoveredDomainPack] = []
    for raw in requested:
        token = str(raw).strip()
        if not token:
            continue
        matches = tuple(
            item
            for item in discovered
            if token == item.name or token == item.entry_point
        )
        if len(matches) != 1:
            raise DomainPackDiscoveryError(
                f"{ENV_DOMAIN_PACKS} entry {token!r} matched "
                f"{len(matches)} installed domain packs"
            )
        chosen.append(matches[0])
    return tuple(chosen)


def configure_production_domain_packs_from_env() -> DomainPackRegistry:
    global _ENV_CONFIGURED
    _configure_builtin_packs()
    if _ENV_CONFIGURED:
        return _PRODUCTION_DOMAIN_PACKS

    requested = tuple(
        part.strip()
        for part in os.environ.get(ENV_DOMAIN_PACKS, "").split(",")
        if part.strip()
    )
    if requested:
        discovered = discover_domain_packs()
        for descriptor in _resolve_configured(requested, discovered):
            provider = load_discovered_domain_pack(descriptor)
            register_production_domain_pack(
                provider,
                origin=PackOrigin.external(
                    distribution_name=descriptor.distribution_name,
                    distribution_version=descriptor.distribution_version,
                    entry_point=descriptor.entry_point,
                ),
                enable=True,
            )
    _ENV_CONFIGURED = True
    return _PRODUCTION_DOMAIN_PACKS


def production_domain_claim_capabilities(
) -> tuple[CapabilityDeclaration, ...]:
    registry = configure_production_domain_packs_from_env()
    out: list[CapabilityDeclaration] = []
    for registration in registry.list(enabled_only=True):
        out.extend(
            _PRODUCTION_DOMAIN_CLAIMS.get(
                registration.manifest.key,
                (),
            )
        )
    return tuple(sorted(out, key=lambda item: item.capability_id))


def production_composition_claim_capabilities(
) -> tuple[CapabilityDeclaration, ...]:
    _configure_builtin_packs()
    out = [
        declaration
        for registration in _PRODUCTION_COMPOSITIONS.list(
            enabled_only=True
        )
        for declaration in registration.claim_capabilities
    ]
    return tuple(sorted(out, key=lambda item: item.capability_id))


def production_pack_capabilities(
) -> tuple[CapabilityDeclaration, ...]:
    """Compatibility name: all enabled pack-owned capability declarations."""

    return tuple(
        sorted(
            (
                *production_domain_claim_capabilities(),
                *production_composition_claim_capabilities(),
            ),
            key=lambda item: item.capability_id,
        )
    )


def production_multiphysics_factory_registry():
    _configure_builtin_packs()
    return _PRODUCTION_EXECUTIONS.participant_factory_registry(
        enabled_only=True
    )


def production_pack_schema_inventory() -> dict[str, tuple[dict, ...]]:
    """Return deterministic current-schema inventory for release tooling."""

    from ..compositionpacks.manifest import COMPOSITION_PACK_SCHEMA
    from ..executionpacks.manifest import EXECUTION_PACK_SCHEMA

    _configure_builtin_packs()
    from .replay_catalog import builtin_golden_replay_catalog

    golden = builtin_golden_replay_catalog()
    compositions = tuple(
        {
            "pack_id": item.manifest.pack_id,
            "pack_version": item.manifest.pack_version,
            "schema": item.manifest.to_dict()["schema"],
            "expected_schema": COMPOSITION_PACK_SCHEMA,
            "authority_digest": item.authority_digest,
            "semantic_authority_digest": item.semantic_authority.digest,
            "uncertainty_protocols": len(
                item.manifest.uncertainty_protocols
            ),
            "verification_protocols": len(
                item.manifest.verification_protocols
            ),
            "golden_replay_scenarios": len(
                golden.for_composition(
                    item.manifest.pack_id,
                    item.manifest.pack_version,
                )
            ),
        }
        for item in _PRODUCTION_COMPOSITIONS.list(enabled_only=True)
    )
    executions = tuple(
        {
            "pack_id": item.manifest.pack_id,
            "pack_version": item.manifest.pack_version,
            "schema": item.manifest.to_dict()["schema"],
            "expected_schema": EXECUTION_PACK_SCHEMA,
            "authority_digest": item.authority_digest,
            "composition_authority_digest": (
                item.composition_authority_digest
            ),
        }
        for item in _PRODUCTION_EXECUTIONS.list(enabled_only=True)
    )
    return {
        "composition": compositions,
        "execution": executions,
    }


def assert_current_production_pack_schemas() -> None:
    """Fail a release when enabled multiphysics authority is legacy/incomplete."""

    inventory = production_pack_schema_inventory()
    problems = []
    for item in inventory["composition"]:
        if item["schema"] != item["expected_schema"]:
            problems.append(
                f"composition {item['pack_id']}@{item['pack_version']} "
                f"uses {item['schema']}, expected {item['expected_schema']}"
            )
        if not item["semantic_authority_digest"]:
            problems.append(
                f"composition {item['pack_id']}@{item['pack_version']} "
                "has no semantic authority digest"
            )
        if item["uncertainty_protocols"] < 1:
            problems.append(
                f"composition {item['pack_id']}@{item['pack_version']} "
                "has no pinned uncertainty protocol"
            )
        if item["verification_protocols"] < 1:
            problems.append(
                f"composition {item['pack_id']}@{item['pack_version']} "
                "has no pinned verification protocol"
            )
        if item["golden_replay_scenarios"] < 1:
            problems.append(
                f"composition {item['pack_id']}@{item['pack_version']} "
                "has no golden replay baseline"
            )
    for item in inventory["execution"]:
        if item["schema"] != item["expected_schema"]:
            problems.append(
                f"execution {item['pack_id']}@{item['pack_version']} "
                f"uses {item['schema']}, expected {item['expected_schema']}"
            )
        if not item["composition_authority_digest"]:
            problems.append(
                f"execution {item['pack_id']}@{item['pack_version']} "
                "is not bound to composition authority"
            )
    if problems:
        raise RuntimeError(
            "production multiphysics catalog is not release-ready: "
            + "; ".join(problems)
        )


__all__ = [
    "ENV_DOMAIN_PACKS",
    "configure_production_domain_packs_from_env",
    "production_composition_claim_capabilities",
    "production_composition_packs",
    "production_domain_claim_capabilities",
    "production_domain_packs",
    "production_execution_packs",
    "production_multiphysics_factory_registry",
    "production_pack_schema_inventory",
    "assert_current_production_pack_schemas",
    "production_pack_capabilities",
    "register_production_composition_pack",
    "register_production_domain_pack",
    "register_production_execution_pack",
]
