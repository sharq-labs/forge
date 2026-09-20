"""Deterministic coupling-candidate discovery for PhysicsGraph composition.

This module does not create scientific wiring. It discovers connections that
are structurally compatible under declared port semantics, then exposes
ambiguity explicitly. A domain blueprint or trusted planning policy still owns
the decision to establish an edge.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping

from ..errors import InvalidScientificProblem
from ..serialization import require_schema_any, schema_string
from .participant import ParticipantSpec
from .ports import PortKind, PortRef

COUPLING_CANDIDATE_SCHEMA_V1 = schema_string(
    "multiphysics_coupling_candidate"
)
COUPLING_CANDIDATE_SCHEMA = schema_string(
    "multiphysics_coupling_candidate",
    2,
)
COMPOSITION_ANALYSIS_SCHEMA_V1 = schema_string(
    "multiphysics_composition_analysis"
)
COMPOSITION_ANALYSIS_SCHEMA = schema_string(
    "multiphysics_composition_analysis",
    2,
)


@dataclass(frozen=True)
class CouplingCandidate:
    source: PortRef
    target: PortRef
    quantity: str
    dimension: str
    kind: PortKind
    requires_field_mapping: bool
    requires_frame_transform: bool
    semantic_id: str = ""

    def __post_init__(self) -> None:
        if self.source.participant_id == self.target.participant_id:
            raise InvalidScientificProblem(
                "coupling candidate must cross participant boundaries"
            )
        object.__setattr__(self, "kind", PortKind(self.kind))
        object.__setattr__(
            self,
            "semantic_id",
            str(self.semantic_id).strip(),
        )

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
            "schema": COUPLING_CANDIDATE_SCHEMA,
            "source": self.source.to_dict(),
            "target": self.target.to_dict(),
            "quantity": self.quantity,
            "dimension": self.dimension,
            "kind": self.kind.value,
            "requires_field_mapping": self.requires_field_mapping,
            "requires_frame_transform": self.requires_frame_transform,
            "semantic_id": self.semantic_id,
            "directly_connectable": self.directly_connectable,
        }

    @classmethod
    def from_dict(
        cls,
        payload: Mapping[str, Any],
    ) -> "CouplingCandidate":
        require_schema_any(
            payload,
            (
                COUPLING_CANDIDATE_SCHEMA_V1,
                COUPLING_CANDIDATE_SCHEMA,
            ),
        )
        return cls(
            source=PortRef.from_dict(payload["source"]),
            target=PortRef.from_dict(payload["target"]),
            quantity=payload["quantity"],
            dimension=payload["dimension"],
            kind=PortKind(payload["kind"]),
            requires_field_mapping=bool(
                payload["requires_field_mapping"]
            ),
            requires_frame_transform=bool(
                payload["requires_frame_transform"]
            ),
            semantic_id=payload.get("semantic_id", ""),
        )


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
            "schema": COMPOSITION_ANALYSIS_SCHEMA,
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
            "record_fingerprint": self.fingerprint,
        }

    @property
    def fingerprint(self) -> str:
        payload = {
            key: value
            for key, value in self.to_dict().items()
            if key != "record_fingerprint"
        }
        return hashlib.sha256(
            json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()

    @classmethod
    def from_dict(
        cls,
        payload: Mapping[str, Any],
    ) -> "CompositionAnalysis":
        require_schema_any(
            payload,
            (
                COMPOSITION_ANALYSIS_SCHEMA_V1,
                COMPOSITION_ANALYSIS_SCHEMA,
            ),
        )
        made = cls(
            candidates=tuple(
                CouplingCandidate.from_dict(item)
                for item in payload.get("candidates", ())
            ),
            external_inputs=tuple(
                PortRef.from_dict(item)
                for item in payload.get("external_inputs", ())
            ),
            unique_targets=tuple(
                PortRef.from_dict(item)
                for item in payload.get("unique_targets", ())
            ),
            ambiguous_targets=tuple(
                PortRef.from_dict(item)
                for item in payload.get("ambiguous_targets", ())
            ),
        )
        supplied = payload.get("record_fingerprint")
        if supplied is not None and supplied != made.fingerprint:
            raise ValueError(
                "composition analysis fingerprint disagrees with its content"
            )
        return made


def _compatible(
    source,
    target,
    *,
    source_semantic: str = "",
    target_semantic: str = "",
) -> bool:
    if source.kind is not target.kind:
        return False
    if source_semantic or target_semantic:
        if not source_semantic or not target_semantic:
            return False
        if source_semantic != target_semantic:
            return False
    elif source.quantity != target.quantity:
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
    *,
    semantic_ids: Mapping[PortRef, str] | None = None,
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

    semantic_map: dict[PortRef, str] = {}
    if semantic_ids is not None:
        semantic_map = {
            key: str(value).strip()
            for key, value in semantic_ids.items()
        }
        expected = {
            PortRef(participant.participant_id, port.port_id)
            for participant in participants
            for port in participant.ports
        }
        if set(semantic_map) != expected:
            raise InvalidScientificProblem(
                "canonical semantic_ids must cover every participant port "
                f"exactly; missing={sorted(ref.key for ref in expected-set(semantic_map))}, "
                f"extra={sorted(ref.key for ref in set(semantic_map)-expected)}"
            )
        if any(not value for value in semantic_map.values()):
            raise InvalidScientificProblem(
                "canonical semantic_ids may not contain empty identities"
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
                source_ref = PortRef(
                    source_participant.participant_id,
                    source.port_id,
                )
                source_semantic = semantic_map.get(source_ref, "")
                target_semantic = semantic_map.get(target_ref, "")
                if not _compatible(
                    source,
                    target,
                    source_semantic=source_semantic,
                    target_semantic=target_semantic,
                ):
                    continue

                matches.append(
                    CouplingCandidate(
                        source=source_ref,
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
                        semantic_id=target_semantic,
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
    "COMPOSITION_ANALYSIS_SCHEMA",
    "COMPOSITION_ANALYSIS_SCHEMA_V1",
    "COUPLING_CANDIDATE_SCHEMA",
    "COUPLING_CANDIDATE_SCHEMA_V1",
    "CompositionAnalysis",
    "CouplingCandidate",
    "analyze_composition",
]
