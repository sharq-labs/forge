"""Optional multiphysics extension for Forge Domain Packs.

The base DomainPackProvider contract remains unchanged. Providers may opt in to
multiphysics planning/execution by exposing zero-argument methods named
multiphysics_blueprints and/or multiphysics_participant_factories.

The extension is validated against the pack's existing atomic manifest so a
plugin cannot smuggle undeclared models, realizations or solvers into a graph.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any

from ..execution.multiphysics.factory import ParticipantFactoryDeclaration
from ..planning.blueprint import PhysicsGraphBlueprint
from .errors import InvalidDomainPackProvider
from .manifest import DomainPackManifest


@dataclass(frozen=True)
class MultiphysicsPackExtension:
    pack_id: str
    pack_version: str
    blueprints: tuple[PhysicsGraphBlueprint, ...] = ()
    participant_factories: tuple[ParticipantFactoryDeclaration, ...] = ()

    def __post_init__(self) -> None:
        for label in ("pack_id", "pack_version"):
            value = str(getattr(self, label)).strip()
            if not value:
                raise InvalidDomainPackProvider(
                    f"multiphysics extension requires {label}"
                )
            object.__setattr__(self, label, value)

        blueprints = tuple(self.blueprints)
        factories = tuple(self.participant_factories)
        if any(
            not isinstance(item, PhysicsGraphBlueprint)
            for item in blueprints
        ):
            raise InvalidDomainPackProvider(
                "multiphysics_blueprints() must return "
                "PhysicsGraphBlueprint records only"
            )
        if any(
            not isinstance(item, ParticipantFactoryDeclaration)
            for item in factories
        ):
            raise InvalidDomainPackProvider(
                "multiphysics_participant_factories() must return "
                "ParticipantFactoryDeclaration records only"
            )

        blueprint_keys = [item.key for item in blueprints]
        if len(blueprint_keys) != len(set(blueprint_keys)):
            raise InvalidDomainPackProvider(
                "multiphysics extension contains duplicate blueprint identities"
            )
        factory_keys = [item.key for item in factories]
        if len(factory_keys) != len(set(factory_keys)):
            raise InvalidDomainPackProvider(
                "multiphysics extension contains duplicate participant "
                "factory identities"
            )

        object.__setattr__(
            self,
            "blueprints",
            tuple(sorted(blueprints, key=lambda item: item.key)),
        )
        object.__setattr__(
            self,
            "participant_factories",
            tuple(sorted(factories, key=lambda item: item.key)),
        )

    @property
    def empty(self) -> bool:
        return not self.blueprints and not self.participant_factories

    @property
    def fingerprint(self) -> str:
        payload = {
            "pack_id": self.pack_id,
            "pack_version": self.pack_version,
            "blueprints": [item.to_dict() for item in self.blueprints],
            "participant_factories": [
                item.identity_dict() for item in self.participant_factories
            ],
        }
        return hashlib.sha256(
            json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()


def _optional_records(provider: Any, name: str) -> tuple[Any, ...]:
    getter = getattr(provider, name, None)
    if getter is None:
        return ()
    if not callable(getter):
        raise InvalidDomainPackProvider(
            f"{name} must be a zero-argument callable when provided"
        )
    try:
        return tuple(getter())
    except Exception as exc:
        raise InvalidDomainPackProvider(
            f"provider.{name}() failed during multiphysics admission"
        ) from exc


def load_multiphysics_extension(
    provider: Any,
) -> MultiphysicsPackExtension:
    manifest = getattr(provider, "manifest", None)
    if not isinstance(manifest, DomainPackManifest):
        raise InvalidDomainPackProvider(
            "multiphysics extension requires a valid DomainPackManifest"
        )

    extension = MultiphysicsPackExtension(
        pack_id=manifest.pack_id,
        pack_version=manifest.pack_version,
        blueprints=_optional_records(
            provider,
            "multiphysics_blueprints",
        ),
        participant_factories=_optional_records(
            provider,
            "multiphysics_participant_factories",
        ),
    )

    model_keys = {
        (item.artifact_id, item.version)
        for item in manifest.models
    }
    realization_keys = {
        (item.artifact_id, item.version)
        for item in manifest.realizations
    }
    solver_keys = {
        (item.artifact_id, item.version)
        for item in manifest.solvers
    }

    errors: list[str] = []
    for blueprint in extension.blueprints:
        for participant in blueprint.participants:
            model_key = (
                participant.model_id,
                participant.model_version,
            )
            if model_key not in model_keys:
                errors.append(
                    f"blueprint {blueprint.blueprint_id}@"
                    f"{blueprint.version} participant "
                    f"{participant.participant_id} references model "
                    f"{participant.model_id}@{participant.model_version} "
                    "outside the pack manifest"
                )

            compatible_factories = [
                declaration
                for declaration in extension.participant_factories
                if declaration.model_id == participant.model_id
                and declaration.model_version == participant.model_version
                and declaration.adapter_id == participant.adapter_id
                and declaration.adapter_version
                == participant.adapter_version
            ]
            if (
                extension.participant_factories
                and not compatible_factories
            ):
                errors.append(
                    f"blueprint {blueprint.blueprint_id}@"
                    f"{blueprint.version} participant "
                    f"{participant.participant_id} has no declared factory "
                    f"for model {participant.model_id}@"
                    f"{participant.model_version} and adapter "
                    f"{participant.adapter_id}@{participant.adapter_version}"
                )

    for declaration in extension.participant_factories:
        if (
            declaration.model_id,
            declaration.model_version,
        ) not in model_keys:
            errors.append(
                "participant factory references undeclared model "
                f"{declaration.model_id}@{declaration.model_version}"
            )
        if (
            declaration.realization_id,
            declaration.realization_version,
        ) not in realization_keys:
            errors.append(
                "participant factory references undeclared realization "
                f"{declaration.realization_id}@"
                f"{declaration.realization_version}"
            )
        if (
            declaration.solver_id,
            declaration.solver_version,
        ) not in solver_keys:
            errors.append(
                "participant factory references undeclared solver "
                f"{declaration.solver_id}@{declaration.solver_version}"
            )

    if errors:
        raise InvalidDomainPackProvider(
            f"domain pack {manifest.pack_id}@{manifest.pack_version} "
            "multiphysics extension is invalid: "
            + "; ".join(errors)
        )

    return extension


__all__ = [
    "MultiphysicsPackExtension",
    "load_multiphysics_extension",
]
