"""Canonical semantic authority snapshot for Composition Packs."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any

from .errors import InvalidCompositionPackProvider


def _digest(payload) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True)
class CompositionSemanticAuthoritySnapshot:
    pack_id: str
    pack_version: str
    capability_qois: tuple[tuple[str, str, str, str], ...]
    participant_models: tuple[
        tuple[str, str, tuple[str, ...]], ...
    ]
    port_quantities: tuple[
        tuple[str, str, str, str, str, str], ...
    ]
    coupling_laws: tuple[
        tuple[str, str, str, str, str, str], ...
    ]
    digest: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "pack_id": self.pack_id,
            "pack_version": self.pack_version,
            "capability_qois": [
                {
                    "capability_id": capability_id,
                    "quantity": quantity,
                    "dimension": dimension,
                    "model_id": model_id,
                }
                for capability_id, quantity, dimension, model_id
                in self.capability_qois
            ],
            "participant_models": [
                {
                    "blueprint_id": blueprint_id,
                    "participant_id": participant_id,
                    "models": list(models),
                }
                for blueprint_id, participant_id, models
                in self.participant_models
            ],
            "port_quantities": [
                {
                    "blueprint_id": blueprint_id,
                    "participant_id": participant_id,
                    "port_id": port_id,
                    "quantity_id": quantity_id,
                    "direction": direction,
                    "dimension": dimension,
                }
                for (
                    blueprint_id,
                    participant_id,
                    port_id,
                    quantity_id,
                    direction,
                    dimension,
                )
                in self.port_quantities
            ],
            "coupling_laws": [
                {
                    "blueprint_id": blueprint_id,
                    "edge_id": edge_id,
                    "source_quantity_id": source_quantity,
                    "target_quantity_id": target_quantity,
                    "transfer_law_id": transfer_law,
                    "sign_convention": sign_convention,
                }
                for (
                    blueprint_id,
                    edge_id,
                    source_quantity,
                    target_quantity,
                    transfer_law,
                    sign_convention,
                )
                in self.coupling_laws
            ],
            "digest": self.digest,
        }


def bind_composition_semantic_authority(
    *,
    manifest,
    claims,
    blueprints,
    port_semantics,
    coupling_semantics,
) -> CompositionSemanticAuthoritySnapshot:
    port_by_key = {item.key: item for item in port_semantics}
    capability_qois = tuple(
        sorted(
            (
                declaration.capability_id,
                quantity.name,
                quantity.dimension,
                quantity.model_id or "",
            )
            for declaration in claims
            for quantity in declaration.produces
        )
    )

    participant_models = tuple(
        sorted(
            (
                blueprint.blueprint_id,
                participant.participant_id,
                tuple(
                    f"{model_id}@{version}"
                    for model_id, version in participant.model_keys
                ),
            )
            for blueprint in blueprints
            for participant in blueprint.participants
        )
    )

    port_quantities = []
    for blueprint in blueprints:
        for participant in blueprint.participants:
            for port in participant.ports:
                key = (
                    blueprint.blueprint_id,
                    participant.participant_id,
                    port.port_id,
                )
                binding = port_by_key.get(key)
                if binding is None:
                    raise InvalidCompositionPackProvider(
                        "semantic authority cannot bind an undeclared port "
                        f"quantity for {key}"
                    )
                if binding.quantity_id != port.quantity:
                    raise InvalidCompositionPackProvider(
                        "port semantic binding disagrees with PortDefinition "
                        f"for {key}: {binding.quantity_id!r} != "
                        f"{port.quantity!r}"
                    )
                port_quantities.append(
                    (
                        blueprint.blueprint_id,
                        participant.participant_id,
                        port.port_id,
                        binding.quantity_id,
                        port.direction.value,
                        port.dimension,
                    )
                )
    port_quantities = tuple(sorted(port_quantities))

    coupling_laws = tuple(
        sorted(
            (
                item.blueprint_id,
                item.edge_id,
                item.source_quantity_id,
                item.target_quantity_id,
                item.transfer_law_id,
                item.sign_convention.value,
            )
            for item in coupling_semantics
        )
    )

    payload = {
        "pack_id": manifest.pack_id,
        "pack_version": manifest.pack_version,
        "capability_qois": [list(item) for item in capability_qois],
        "participant_models": [
            [blueprint_id, participant_id, list(models)]
            for blueprint_id, participant_id, models
            in participant_models
        ],
        "port_quantities": [list(item) for item in port_quantities],
        "coupling_laws": [list(item) for item in coupling_laws],
    }
    digest = _digest(payload)
    return CompositionSemanticAuthoritySnapshot(
        pack_id=manifest.pack_id,
        pack_version=manifest.pack_version,
        capability_qois=capability_qois,
        participant_models=participant_models,
        port_quantities=port_quantities,
        coupling_laws=coupling_laws,
        digest=digest,
    )


__all__ = [
    "CompositionSemanticAuthoritySnapshot",
    "bind_composition_semantic_authority",
]
