"""Deterministic registry and admission for cross-domain Composition Packs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterator

from ..claims.capabilities import CapabilityDeclaration
from ..domainpacks.frozen import (
    ArtifactImplementationFingerprint,
    implementation_fingerprint,
)
from ..domainpacks.registry import DomainPackRegistry
from ..scientific.multiphysics import PortDirection
from .blueprint import CouplingPolicyTemplate, SystemGraphBlueprint
from .contracts import (
    ProvidedCompositionValidation,
    SystemApplicabilityRule,
    UncertaintyCompositionRule,
    system_contract_digest,
)
from .errors import (
    CompositionDependencyError,
    CompositionPackNotEnabled,
    CompositionPackNotFound,
    DuplicateCompositionPack,
    InvalidCompositionPackProvider,
)
from .inputs import ExternalInputBinding
from .manifest import (
    BlueprintRef,
    COMPOSITION_PACK_API,
    CompositionPackManifest,
    PolicyTemplateRef,
)
from .provider import CompositionPackProvider
from .semantics import CouplingSemantic, PortSemanticBinding


@dataclass(frozen=True)
class RegisteredCompositionPack:
    manifest: CompositionPackManifest
    claim_capabilities: tuple[CapabilityDeclaration, ...]
    blueprints: tuple[SystemGraphBlueprint, ...]
    coupling_policy_templates: tuple[CouplingPolicyTemplate, ...]
    port_semantics: tuple[PortSemanticBinding, ...]
    coupling_semantics: tuple[CouplingSemantic, ...]
    external_input_bindings: tuple[ExternalInputBinding, ...]
    applicability_rules: tuple[SystemApplicabilityRule, ...]
    uncertainty_rules: tuple[UncertaintyCompositionRule, ...]
    validation_protocols: tuple[ProvidedCompositionValidation, ...]
    validation_fingerprints: tuple[
        ArtifactImplementationFingerprint, ...
    ]
    source_provider_type: str

    @property
    def key(self) -> tuple[str, str]:
        return self.manifest.key

    @property
    def dependency_keys(self) -> tuple[tuple[str, str], ...]:
        return tuple(item.key for item in self.manifest.requires_domain_packs)


def _records(provider: Any, name: str) -> tuple[Any, ...]:
    getter = getattr(provider, name, None)
    if not callable(getter):
        raise InvalidCompositionPackProvider(
            f"composition provider must expose callable {name}()"
        )
    try:
        return tuple(getter())
    except Exception as exc:
        raise InvalidCompositionPackProvider(
            f"composition provider.{name}() failed during admission"
        ) from exc


def _unique(records: tuple[Any, ...], label: str) -> None:
    keys = [item.key for item in records]
    if len(keys) != len(set(keys)):
        raise InvalidCompositionPackProvider(
            f"{label} contains duplicate identities"
        )


def _resolve_dependencies(
    manifest: CompositionPackManifest,
    domain_packs: DomainPackRegistry,
    *,
    require_enabled: bool,
):
    resolved = []
    for dependency in manifest.requires_domain_packs:
        registration = domain_packs.get(
            dependency.pack_id,
            dependency.pack_version,
            require_enabled=require_enabled,
        )
        actual = registration.manifest.digest
        if actual != dependency.manifest_digest:
            raise CompositionDependencyError(
                f"composition pack {manifest.pack_id}@{manifest.pack_version} "
                f"requires {dependency.pack_id}@{dependency.pack_version} "
                f"manifest {dependency.manifest_digest}, registered manifest "
                f"is {actual}"
            )
        resolved.append(registration)
    return tuple(resolved)


def _validate_blueprint_model_ownership(
    blueprint: SystemGraphBlueprint,
    dependencies,
) -> None:
    owners: dict[tuple[str, str], list[str]] = {}
    for registration in dependencies:
        for model in registration.provider.models():
            owners.setdefault(model.key, []).append(
                f"{registration.manifest.pack_id}@"
                f"{registration.manifest.pack_version}"
            )

    for participant in blueprint.participants:
        key = (participant.model_id, participant.model_version)
        matched = owners.get(key, [])
        if len(matched) != 1:
            raise InvalidCompositionPackProvider(
                f"blueprint {blueprint.blueprint_id}@{blueprint.version} "
                f"participant {participant.participant_id!r} references "
                f"model {key[0]}@{key[1]} with {len(matched)} exact "
                f"Domain Pack owners: {matched}"
            )


def _validate_port_and_edge_semantics(
    blueprint: SystemGraphBlueprint,
    port_semantics: tuple[PortSemanticBinding, ...],
    coupling_semantics: tuple[CouplingSemantic, ...],
) -> None:
    bindings = {
        item.key: item
        for item in port_semantics
        if item.blueprint_id == blueprint.blueprint_id
    }

    expected_ports = {
        (blueprint.blueprint_id, participant.participant_id, port.port_id)
        for participant in blueprint.participants
        for port in participant.ports
    }
    actual_ports = set(bindings)
    if actual_ports != expected_ports:
        raise InvalidCompositionPackProvider(
            f"blueprint {blueprint.blueprint_id!r} semantic bindings mismatch; "
            f"missing={sorted(expected_ports-actual_ports)}, "
            f"extra={sorted(actual_ports-expected_ports)}"
        )

    edge_semantics = {
        item.key: item
        for item in coupling_semantics
        if item.blueprint_id == blueprint.blueprint_id
    }
    blueprint_edges = {
        (blueprint.blueprint_id, item.edge_id): item
        for item in blueprint.edges
    }
    extra_edges = sorted(set(edge_semantics) - set(blueprint_edges))
    if extra_edges:
        raise InvalidCompositionPackProvider(
            f"coupling semantics reference undeclared edges {extra_edges}"
        )

    participants = {
        item.participant_id: item for item in blueprint.participants
    }
    for edge in blueprint.edges:
        source_participant = participants[edge.source.participant_id]
        target_participant = participants[edge.target.participant_id]
        source_port = next(
            port for port in source_participant.ports
            if port.port_id == edge.source.port_id
        )
        target_port = next(
            port for port in target_participant.ports
            if port.port_id == edge.target.port_id
        )

        if source_port.direction is not PortDirection.OUTPUT:
            raise InvalidCompositionPackProvider(
                f"edge {edge.edge_id!r} source is not an output port"
            )
        if target_port.direction is not PortDirection.INPUT:
            raise InvalidCompositionPackProvider(
                f"edge {edge.edge_id!r} target is not an input port"
            )
        if source_port.kind is not target_port.kind:
            raise InvalidCompositionPackProvider(
                f"edge {edge.edge_id!r} changes port kind"
            )
        if source_port.dimension != target_port.dimension:
            raise InvalidCompositionPackProvider(
                f"edge {edge.edge_id!r} changes physical dimension "
                f"[{source_port.dimension}] -> [{target_port.dimension}]"
            )

        source_binding = bindings[
            (
                blueprint.blueprint_id,
                edge.source.participant_id,
                edge.source.port_id,
            )
        ]
        target_binding = bindings[
            (
                blueprint.blueprint_id,
                edge.target.participant_id,
                edge.target.port_id,
            )
        ]
        semantic = edge_semantics.get(
            (blueprint.blueprint_id, edge.edge_id)
        )
        if source_binding.quantity_id != target_binding.quantity_id:
            if semantic is None:
                raise InvalidCompositionPackProvider(
                    f"edge {edge.edge_id!r} crosses canonical quantities "
                    f"{source_binding.quantity_id!r} -> "
                    f"{target_binding.quantity_id!r} without a typed "
                    "CouplingSemantic/transfer law"
                )
        if semantic is not None:
            if (
                semantic.source_quantity_id
                != source_binding.quantity_id
                or semantic.target_quantity_id
                != target_binding.quantity_id
            ):
                raise InvalidCompositionPackProvider(
                    f"edge {edge.edge_id!r} coupling semantic disagrees "
                    "with its port semantic bindings"
                )


def _validate_external_input_bindings(
    blueprint: SystemGraphBlueprint,
    bindings: tuple[ExternalInputBinding, ...],
) -> None:
    by_key = {
        item.key: item
        for item in bindings
        if item.blueprint_id == blueprint.blueprint_id
    }
    participants = {
        item.participant_id: item for item in blueprint.participants
    }
    connected_targets = {
        (edge.target.participant_id, edge.target.port_id)
        for edge in blueprint.edges
    }
    expected = {
        (blueprint.blueprint_id, participant.participant_id, port.port_id)
        for participant in blueprint.participants
        for port in participant.ports
        if (
            port.direction is PortDirection.INPUT
            and (participant.participant_id, port.port_id)
            not in connected_targets
        )
    }
    actual = set(by_key)
    if actual != expected:
        raise InvalidCompositionPackProvider(
            f"blueprint {blueprint.blueprint_id!r} external input bindings "
            f"mismatch; missing={sorted(expected-actual)}, "
            f"extra={sorted(actual-expected)}"
        )
    for item in by_key.values():
        participant = participants.get(item.participant_id)
        if participant is None:
            raise InvalidCompositionPackProvider(
                f"external input binding references unknown participant "
                f"{item.participant_id!r}"
            )
        port = next(
            (
                port
                for port in participant.ports
                if port.port_id == item.port_id
            ),
            None,
        )
        if port is None or port.direction is not PortDirection.INPUT:
            raise InvalidCompositionPackProvider(
                f"external input binding {item.key!r} must target an input port"
            )
        if (item.participant_id, item.port_id) in connected_targets:
            raise InvalidCompositionPackProvider(
                f"external input binding {item.key!r} targets an internally "
                "connected graph input"
            )


def _validate_system_contracts(
    blueprints: tuple[SystemGraphBlueprint, ...],
    applicability: tuple[SystemApplicabilityRule, ...],
    uncertainty: tuple[UncertaintyCompositionRule, ...],
    validations: tuple[ProvidedCompositionValidation, ...],
) -> None:
    blueprint_ids = {item.blueprint_id for item in blueprints}

    for label, records in (
        ("applicability", applicability),
        ("uncertainty", uncertainty),
    ):
        unknown = sorted(
            {
                item.blueprint_id
                for item in records
                if item.blueprint_id not in blueprint_ids
            }
        )
        if unknown:
            raise InvalidCompositionPackProvider(
                f"{label} contracts reference unknown blueprints {unknown}"
            )

    validation_unknown = sorted(
        {
            item.blueprint_id
            for item in validations
            if item.blueprint_id not in blueprint_ids
        }
    )
    if validation_unknown:
        raise InvalidCompositionPackProvider(
            "composition validation protocols reference unknown blueprints "
            f"{validation_unknown}"
        )

    for blueprint_id in sorted(blueprint_ids):
        if not any(
            item.blueprint_id == blueprint_id for item in applicability
        ):
            raise InvalidCompositionPackProvider(
                f"blueprint {blueprint_id!r} has no system applicability rule"
            )
        uncertainty_for_blueprint = tuple(
            item
            for item in uncertainty
            if item.blueprint_id == blueprint_id
        )
        if not uncertainty_for_blueprint:
            raise InvalidCompositionPackProvider(
                f"blueprint {blueprint_id!r} has no explicit uncertainty "
                "composition rule; use strategy='unknown' rather than silence"
            )
        if len(uncertainty_for_blueprint) != 1:
            raise InvalidCompositionPackProvider(
                f"blueprint {blueprint_id!r} must declare exactly one "
                "uncertainty composition rule so the planner never chooses "
                "a propagation strategy from registration order"
            )
        if not any(
            item.blueprint_id == blueprint_id for item in validations
        ):
            raise InvalidCompositionPackProvider(
                f"blueprint {blueprint_id!r} has no system-level validation "
                "protocol"
            )


class CompositionPackRegistry:
    def __init__(self) -> None:
        self._packs: dict[
            tuple[str, str], RegisteredCompositionPack
        ] = {}
        self._enabled: set[tuple[str, str]] = set()

    def register(
        self,
        provider: CompositionPackProvider,
        *,
        domain_packs: DomainPackRegistry,
        require_enabled_dependencies: bool = True,
    ) -> RegisteredCompositionPack:
        manifest = getattr(provider, "manifest", None)
        if not isinstance(manifest, CompositionPackManifest):
            raise InvalidCompositionPackProvider(
                "composition provider manifest must be "
                "CompositionPackManifest"
            )
        if COMPOSITION_PACK_API not in manifest.compatible_core_apis:
            raise InvalidCompositionPackProvider(
                "composition pack does not declare compatibility with "
                f"{COMPOSITION_PACK_API}"
            )
        if manifest.key in self._packs:
            raise DuplicateCompositionPack(
                f"composition pack {manifest.pack_id}@"
                f"{manifest.pack_version} is already registered"
            )

        dependencies = _resolve_dependencies(
            manifest,
            domain_packs,
            require_enabled=require_enabled_dependencies,
        )

        claims = _records(provider, "claim_capabilities")
        blueprints = _records(provider, "blueprints")
        policies = _records(provider, "coupling_policy_templates")
        ports = _records(provider, "port_semantics")
        couplings = _records(provider, "coupling_semantics")
        external_inputs = _records(provider, "external_input_bindings")
        applicability = _records(provider, "applicability_rules")
        uncertainty = _records(provider, "uncertainty_rules")
        validations = _records(provider, "validation_protocols")

        if any(
            not isinstance(item, CapabilityDeclaration)
            for item in claims
        ):
            raise InvalidCompositionPackProvider(
                "claim_capabilities() must return CapabilityDeclaration records only"
            )
        if any(item.executable for item in claims):
            raise InvalidCompositionPackProvider(
                "CompositionPack capability declarations may not embed direct "
                "executors; execution belongs to an ExecutionPack"
            )
        if any(item.solvers for item in claims):
            raise InvalidCompositionPackProvider(
                "CompositionPack capability declarations may not pin concrete "
                "solvers; solver authority belongs to an ExecutionPack"
            )

        dependency_models = {}
        for dependency_registration in dependencies:
            for definition in dependency_registration.provider.models():
                dependency_models.setdefault(definition.key, []).append(
                    definition
                )
        for declaration in claims:
            for model_use in declaration.models:
                key = (model_use.model_id, model_use.version)
                matches = dependency_models.get(key, [])
                if len(matches) != 1:
                    raise InvalidCompositionPackProvider(
                        f"composition capability {declaration.capability_id!r} "
                        f"references model {key[0]}@{key[1]} with "
                        f"{len(matches)} exact Domain Pack owners"
                    )
                if (
                    model_use.definition is not None
                    and model_use.definition != matches[0]
                ):
                    raise InvalidCompositionPackProvider(
                        f"composition capability {declaration.capability_id!r} "
                        f"embeds a model definition that differs from its "
                        f"required Domain Pack authority for {key[0]}@{key[1]}"
                    )

        claim_ids = tuple(sorted(item.capability_id for item in claims))
        if claim_ids != manifest.capabilities:
            raise InvalidCompositionPackProvider(
                "composition claim capability ids must exactly match manifest.capabilities"
            )
        if len(set(claim_ids)) != len(claim_ids):
            raise InvalidCompositionPackProvider(
                "composition claim capabilities contain duplicate ids"
            )

        if any(
            not isinstance(item, SystemGraphBlueprint)
            for item in blueprints
        ):
            raise InvalidCompositionPackProvider(
                "blueprints() must return SystemGraphBlueprint records only"
            )
        if any(
            not isinstance(item, CouplingPolicyTemplate)
            for item in policies
        ):
            raise InvalidCompositionPackProvider(
                "coupling_policy_templates() must return "
                "CouplingPolicyTemplate records only"
            )
        for records, cls, label in (
            (ports, PortSemanticBinding, "port_semantics"),
            (couplings, CouplingSemantic, "coupling_semantics"),
            (external_inputs, ExternalInputBinding, "external_input_bindings"),
            (applicability, SystemApplicabilityRule, "applicability_rules"),
            (uncertainty, UncertaintyCompositionRule, "uncertainty_rules"),
            (validations, ProvidedCompositionValidation, "validation_protocols"),
        ):
            if any(not isinstance(item, cls) for item in records):
                raise InvalidCompositionPackProvider(
                    f"{label}() returned invalid record type"
                )

        for records, label in (
            (blueprints, "blueprints"),
            (policies, "coupling policy templates"),
            (ports, "port semantics"),
            (couplings, "coupling semantics"),
            (external_inputs, "external input bindings"),
            (applicability, "applicability rules"),
            (uncertainty, "uncertainty rules"),
        ):
            _unique(tuple(records), label)

        actual_blueprints = tuple(
            sorted(
                (BlueprintRef.from_blueprint(item) for item in blueprints),
                key=lambda item: item.key,
            )
        )
        if actual_blueprints != manifest.blueprints:
            raise InvalidCompositionPackProvider(
                "manifest blueprint refs/digests do not match provider"
            )

        actual_policies = tuple(
            sorted(
                (
                    PolicyTemplateRef.from_template(item)
                    for item in policies
                ),
                key=lambda item: item.key,
            )
        )
        if actual_policies != manifest.coupling_policies:
            raise InvalidCompositionPackProvider(
                "manifest coupling policy refs/digests do not match provider"
            )

        contract_digest = system_contract_digest(
            port_semantics=ports,
            coupling_semantics=couplings,
            external_input_bindings=external_inputs,
            applicability_rules=applicability,
            uncertainty_rules=uncertainty,
        )
        if contract_digest != manifest.system_contract_digest:
            raise InvalidCompositionPackProvider(
                "manifest system_contract_digest disagrees with provider "
                f"contracts: {manifest.system_contract_digest} != "
                f"{contract_digest}"
            )

        validation_refs = tuple(sorted(item.ref for item in validations))
        if validation_refs != manifest.validation_protocols:
            raise InvalidCompositionPackProvider(
                "manifest validation_protocols do not match provider"
            )

        blueprint_by_id = {
            item.blueprint_id: item for item in blueprints
        }
        for blueprint in blueprints:
            if blueprint.capability_id not in manifest.capabilities:
                raise InvalidCompositionPackProvider(
                    f"blueprint {blueprint.blueprint_id!r} targets "
                    f"undeclared composition capability "
                    f"{blueprint.capability_id!r}"
                )
            _validate_blueprint_model_ownership(
                blueprint,
                dependencies,
            )
            _validate_port_and_edge_semantics(
                blueprint,
                ports,
                couplings,
            )
            _validate_external_input_bindings(
                blueprint,
                external_inputs,
            )

        for policy in policies:
            blueprint = blueprint_by_id.get(policy.blueprint_id)
            if blueprint is None:
                raise InvalidCompositionPackProvider(
                    f"coupling policy {policy.template_id!r} references "
                    f"unknown blueprint {policy.blueprint_id!r}"
                )
            policy.validate_against_blueprint(blueprint)

        for blueprint in blueprints:
            if not any(
                item.blueprint_id == blueprint.blueprint_id
                for item in policies
            ):
                raise InvalidCompositionPackProvider(
                    f"blueprint {blueprint.blueprint_id!r} has no coupling "
                    "policy template"
                )

        _validate_system_contracts(
            blueprints,
            applicability,
            uncertainty,
            validations,
        )

        validation_fingerprints = []
        for item in validations:
            digest, basis = implementation_fingerprint(
                item.implementation
            )
            validation_fingerprints.append(
                ArtifactImplementationFingerprint(
                    "composition_validation",
                    item.ref.artifact_id,
                    item.ref.version,
                    digest,
                    basis,
                )
            )

        registration = RegisteredCompositionPack(
            manifest=manifest,
            claim_capabilities=tuple(
                sorted(claims, key=lambda item: item.capability_id)
            ),
            blueprints=tuple(
                sorted(blueprints, key=lambda item: item.key)
            ),
            coupling_policy_templates=tuple(
                sorted(policies, key=lambda item: item.key)
            ),
            port_semantics=tuple(sorted(ports)),
            coupling_semantics=tuple(sorted(couplings)),
            external_input_bindings=tuple(sorted(external_inputs)),
            applicability_rules=tuple(sorted(applicability)),
            uncertainty_rules=tuple(sorted(uncertainty)),
            validation_protocols=tuple(
                sorted(
                    validations,
                    key=lambda item: (
                        item.blueprint_id,
                        item.ref.artifact_id,
                        item.ref.version,
                    ),
                )
            ),
            validation_fingerprints=tuple(
                sorted(validation_fingerprints)
            ),
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
            raise CompositionPackNotFound(
                f"cannot enable unregistered composition pack "
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
    ) -> RegisteredCompositionPack:
        key = str(pack_id), str(pack_version)
        try:
            registration = self._packs[key]
        except KeyError:
            raise CompositionPackNotFound(
                f"no composition pack {key[0]}@{key[1]}"
            ) from None
        if require_enabled and key not in self._enabled:
            raise CompositionPackNotEnabled(
                f"composition pack {key[0]}@{key[1]} is not enabled"
            )
        return registration

    def list(
        self,
        *,
        enabled_only: bool = False,
    ) -> tuple[RegisteredCompositionPack, ...]:
        keys = sorted(self._enabled if enabled_only else self._packs)
        return tuple(self._packs[key] for key in keys)

    def providing(
        self,
        capability_id: str,
        *,
        enabled_only: bool = True,
    ) -> tuple[RegisteredCompositionPack, ...]:
        wanted = str(capability_id).strip()
        return tuple(
            item
            for item in self.list(enabled_only=enabled_only)
            if wanted in item.manifest.capabilities
        )

    def __iter__(self) -> Iterator[RegisteredCompositionPack]:
        return iter(self.list())


__all__ = [
    "CompositionPackRegistry",
    "RegisteredCompositionPack",
]
