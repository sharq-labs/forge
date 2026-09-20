"""Deterministic coupling-candidate discovery for PhysicsGraph composition.

This module does not create scientific wiring. It discovers connections that
are structurally compatible under declared port semantics, then exposes
ambiguity explicitly. A domain blueprint or trusted planning policy still owns
the decision to establish an edge.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..errors import InvalidScientificProblem
from .participant import ParticipantSpec
from .ports import PortKind, PortRef


@dataclass(frozen=True)
class CouplingCandidate:
    source: PortRef
    target: PortRef
    quantity: str
    dimension: str
    kind: PortKind
    requires_field_mapping: bool
    requires_frame_transform: bool

    def __post_init__(self) -> None:
        if self.source.participant_id == self.target.participant_id:
            raise InvalidScientificProblem(
                "coupling candidate must cross participant boundaries"
            )
        object.__setattr__(self, "kind", PortKind(self.kind))

    @property
    def key(self) -> str:
        return f"{self.source.key}->{self.target.key}"

    @property
    def directly_connectable(self) -> bool:
        return (
            not self.requires_field_mapping
            and not self.requires_frame_transform
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source.to_dict(),
            "target": self.target.to_dict(),
            "quantity": self.quantity,
            "dimension": self.dimension,
            "kind": self.kind.value,
            "requires_field_mapping": self.requires_field_mapping,
            "requires_frame_transform": self.requires_frame_transform,
            "directly_connectable": self.directly_connectable,
        }


@dataclass(frozen=True)
class CompositionAnalysis:
    candidates: tuple[CouplingCandidate, ...]
    external_inputs: tuple[PortRef, ...]
    unique_targets: tuple[PortRef, ...]
    ambiguous_targets: tuple[PortRef, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "candidates",
            tuple(sorted(self.candidates, key=lambda item: item.key)),
        )
        for label in (
            "external_inputs",
            "unique_targets",
            "ambiguous_targets",
        ):
            object.__setattr__(
                self,
                label,
                tuple(
                    sorted(
                        getattr(self, label),
                        key=lambda ref: ref.key,
                    )
                ),
            )

    def candidates_for(
        self,
        target: PortRef,
    ) -> tuple[CouplingCandidate, ...]:
        return tuple(
            item for item in self.candidates if item.target == target
        )

    @property
    def has_ambiguity(self) -> bool:
        return bool(self.ambiguous_targets)

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidates": [item.to_dict() for item in self.candidates],
            "external_inputs": [
                item.to_dict() for item in self.external_inputs
            ],
            "unique_targets": [
                item.to_dict() for item in self.unique_targets
            ],
            "ambiguous_targets": [
                item.to_dict() for item in self.ambiguous_targets
            ],
            "has_ambiguity": self.has_ambiguity,
        }


def _compatible(source, target) -> bool:
    if source.kind is not target.kind:
        return False
    if source.quantity != target.quantity:
        return False
    if source.dimension != target.dimension:
        return False
    if source.kind is PortKind.FIELD:
        if source.algebra is not target.algebra:
            return False
        assert source.field is not None and target.field is not None
        if source.field.components != target.field.components:
            return False
    return True


def analyze_composition(
    participants: tuple[ParticipantSpec, ...],
) -> CompositionAnalysis:
    """Discover candidate coupling sources without establishing any edge."""

    participants = tuple(participants)
    if not participants:
        raise InvalidScientificProblem(
            "composition analysis requires participants"
        )
    if any(not isinstance(item, ParticipantSpec) for item in participants):
        raise TypeError(
            "composition analysis requires ParticipantSpec records"
        )
    ids = [item.participant_id for item in participants]
    if len(ids) != len(set(ids)):
        raise InvalidScientificProblem(
            "composition analysis participant ids must be unique"
        )

    outputs = [
        (participant, port)
        for participant in participants
        for port in participant.outputs
    ]

    candidates: list[CouplingCandidate] = []
    external: list[PortRef] = []
    unique: list[PortRef] = []
    ambiguous: list[PortRef] = []

    for target_participant in participants:
        for target in target_participant.inputs:
            target_ref = PortRef(
                target_participant.participant_id,
                target.port_id,
            )
            matches: list[CouplingCandidate] = []
            for source_participant, source in outputs:
                if (
                    source_participant.participant_id
                    == target_participant.participant_id
                ):
                    continue
                if not _compatible(source, target):
                    continue

                matches.append(
                    CouplingCandidate(
                        source=PortRef(
                            source_participant.participant_id,
                            source.port_id,
                        ),
                        target=target_ref,
                        quantity=target.quantity,
                        dimension=target.dimension,
                        kind=target.kind,
                        requires_field_mapping=(
                            target.kind is PortKind.FIELD
                            and (
                                source.field.mesh_id
                                != target.field.mesh_id
                            )
                        ),
                        requires_frame_transform=(
                            source.coordinate_frame
                            != target.coordinate_frame
                        ),
                    )
                )

            candidates.extend(matches)
            if not matches:
                external.append(target_ref)
            elif len(matches) == 1:
                unique.append(target_ref)
            else:
                ambiguous.append(target_ref)

    return CompositionAnalysis(
        candidates=tuple(candidates),
        external_inputs=tuple(external),
        unique_targets=tuple(unique),
        ambiguous_targets=tuple(ambiguous),
    )


__all__ = [
    "CompositionAnalysis",
    "CouplingCandidate",
    "analyze_composition",
]
