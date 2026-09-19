"""Explicit bridge from validated Domain Packs to production claim routing.

Domain Pack discovery remains metadata-only and loading remains an administrator
choice.  Production may opt in installed packs with FORGE_DOMAIN_PACKS, a
comma-separated list of exact entry-point names (or full descriptor strings).
Only enabled packs that expose a ``claim_capabilities()`` method contribute
``CapabilityDeclaration`` records to the scientific claim router.
"""

from __future__ import annotations

import os
from typing import Iterable

from ..claims.capabilities import CapabilityDeclaration
from ..domainpacks.discovery import (
    DiscoveredDomainPack,
    discover_domain_packs,
    load_discovered_domain_pack,
)
from ..domainpacks.errors import DomainPackDiscoveryError, InvalidDomainPackProvider
from ..domainpacks.registry import DomainPackRegistry, PackOrigin

ENV_DOMAIN_PACKS = "FORGE_DOMAIN_PACKS"

_PRODUCTION_PACKS = DomainPackRegistry()
_ENV_CONFIGURED = False


def production_domain_packs() -> DomainPackRegistry:
    """The application-layer registry used by the production claim router."""
    return _PRODUCTION_PACKS


def _claim_declarations(provider) -> tuple[CapabilityDeclaration, ...]:
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
    if any(not isinstance(item, CapabilityDeclaration) for item in declarations):
        bad = sorted({type(item).__name__ for item in declarations if not isinstance(item, CapabilityDeclaration)})
        raise InvalidDomainPackProvider(
            f"claim_capabilities() must return CapabilityDeclaration records only; found {bad}"
        )
    if len({item.capability_id for item in declarations}) != len(declarations):
        raise InvalidDomainPackProvider(
            "claim_capabilities() returned duplicate capability ids"
        )

    manifest = provider.manifest
    manifest_caps = frozenset(manifest.capabilities)
    model_keys = {(item.artifact_id, item.version) for item in manifest.models}
    solver_keys = {(item.artifact_id, item.version) for item in manifest.solvers}
    errors: list[str] = []
    for declaration in declarations:
        if declaration.domain != manifest.domain:
            errors.append(
                f"{declaration.capability_id}: domain {declaration.domain!r} "
                f"does not match pack domain {manifest.domain!r}"
            )
        undeclared_science = sorted(
            c.identifier
            for c in declaration.provided_capabilities
            if c.identifier not in manifest_caps
        )
        if undeclared_science:
            errors.append(
                f"{declaration.capability_id}: provides capabilities not declared by "
                f"the pack manifest: {undeclared_science}"
            )
        undeclared_models = sorted(
            f"{m.model_id}@{m.version}"
            for m in declaration.models
            if (m.model_id, m.version) not in model_keys
        )
        if undeclared_models:
            errors.append(
                f"{declaration.capability_id}: routes through models outside the "
                f"atomic pack: {undeclared_models}"
            )
        undeclared_solvers = sorted(
            f"{s.solver_id}@{s.version}"
            for s in declaration.solvers
            if (s.solver_id, s.version) not in solver_keys
        )
        if undeclared_solvers:
            errors.append(
                f"{declaration.capability_id}: routes through solvers outside the "
                f"atomic pack: {undeclared_solvers}"
            )
        if not declaration.executable:
            errors.append(
                f"{declaration.capability_id}: production claim capability has no executor"
            )
    if errors:
        raise InvalidDomainPackProvider(
            f"domain pack {manifest.pack_id}@{manifest.pack_version} claim routing is invalid: "
            + "; ".join(errors)
        )
    return declarations


def register_production_domain_pack(provider, *, origin: PackOrigin | None = None, enable: bool = True):
    """Validate/register one pack and optionally make its claims routable."""
    # Validate claim declarations before mutating the production registry.
    _claim_declarations(provider)
    registration = _PRODUCTION_PACKS.register(provider, origin=origin)
    if enable:
        _PRODUCTION_PACKS.enable(provider.manifest.pack_id, provider.manifest.pack_version)
    return registration


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
            item for item in discovered
            if token == item.name or token == item.entry_point
        )
        if len(matches) != 1:
            raise DomainPackDiscoveryError(
                f"{ENV_DOMAIN_PACKS} entry {token!r} matched {len(matches)} installed "
                "domain packs; use the full entry-point descriptor when names are ambiguous"
            )
        chosen.append(matches[0])
    return tuple(chosen)


def configure_production_domain_packs_from_env() -> DomainPackRegistry:
    """Load exactly the packs an operator named in FORGE_DOMAIN_PACKS, once."""
    global _ENV_CONFIGURED
    if _ENV_CONFIGURED:
        return _PRODUCTION_PACKS
    raw = os.environ.get(ENV_DOMAIN_PACKS, "")
    requested = tuple(part.strip() for part in raw.split(",") if part.strip())
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
    return _PRODUCTION_PACKS


def production_pack_capabilities() -> tuple[CapabilityDeclaration, ...]:
    """Validated executable claim declarations from every enabled production pack."""
    registry = configure_production_domain_packs_from_env()
    out: list[CapabilityDeclaration] = []
    for registered in registry.list(enabled_only=True):
        out.extend(_claim_declarations(registered.provider))
    return tuple(sorted(out, key=lambda item: item.capability_id))


__all__ = [
    "ENV_DOMAIN_PACKS",
    "configure_production_domain_packs_from_env",
    "production_domain_packs",
    "production_pack_capabilities",
    "register_production_domain_pack",
]
