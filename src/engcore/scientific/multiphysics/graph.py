"""Scientific topology of a coupled multiphysics system.

PhysicsGraph says *what is connected*.  It does not choose time windows,
iteration order, relaxation or convergence policy; those belong to
CouplingPlan.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from ..composition.conversion import (
    ENERGY_DERIVED_DIMENSIONS,
    ENERGY_DIMENSIONS,
    EnergyConversion,
)
from ..composition.dependency import QuantityDependency
from ..errors import InvalidScientificProblem
from ..serialization import require_schema, schema_string
from .conservation import CoupledConservation, TransferMeasure
from .frames import FrameTransform
from .mapping import FieldMappingDefinition
from .participant import ParticipantSpec
from .ports import (
    FieldAlgebra,
    PortDirection,
    PortKind,
    PortRef,
)

COUPLING_EDGE_SCHEMA = schema_string("multiphysics_coupling_edge")
PHYSICS_GRAPH_SCHEMA = schema_string("multiphysics_physics_graph")


class ReductionOperator(str, Enum):
    NONE = "none"
    SUM = "sum"
    MEAN = "mean"
    MIN = "min"
    MAX = "max"


@dataclass(frozen=True)
class CouplingEdge:
    edge_id: str
    source: PortRef
    target: PortRef
    reduction: ReductionOperator = ReductionOperator.NONE
    mapping: FieldMappingDefinition | None = None
    conversion: EnergyConversion | None = None
    transport_declaration: str = ""
    coordinate_transform_id: str = ""
    description: str = ""

    def __post_init__(self) -> None:
        edge_id = str(self.edge_id).strip()
        if not edge_id:
            raise InvalidScientificProblem("coupling edge requires edge_id")
        if not isinstance(self.source, PortRef) or not isinstance(self.target, PortRef):
            raise InvalidScientificProblem(
                f"edge {edge_id!r} source/target must be PortRef"
            )
        if self.source == self.target:
            raise InvalidScientificProblem(
                f"edge {edge_id!r} cannot feed a port into itself"
            )
        object.__setattr__(self, "edge_id", edge_id)
        object.__setattr__(self, "reduction", ReductionOperator(self.reduction))
        if self.mapping is not None and not isinstance(
            self.mapping, FieldMappingDefinition
        ):
            raise InvalidScientificProblem(
                f"edge {edge_id!r} mapping must be FieldMappingDefinition"
            )
        if self.conversion is not None and not isinstance(
            self.conversion, EnergyConversion
        ):
            raise InvalidScientificProblem(
                f"edge {edge_id!r} conversion must be EnergyConversion"
            )
        object.__setattr__(
            self,
            "transport_declaration",
            str(self.transport_declaration).strip(),
        )
        object.__setattr__(
            self,
            "coordinate_transform_id",
            str(self.coordinate_transform_id).strip(),
        )
        object.__setattr__(
            self, "description", str(self.description).strip()
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": COUPLING_EDGE_SCHEMA,
            "edge_id": self.edge_id,
            "source": self.source.to_dict(),
            "target": self.target.to_dict(),
            "reduction": self.reduction.value,
            "mapping": (
                None if self.mapping is None else self.mapping.to_dict()
            ),
            "conversion": (
                None
                if self.conversion is None
                else self.conversion.to_dict()
            ),
            "transport_declaration": self.transport_declaration,
            "coordinate_transform_id": self.coordinate_transform_id,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CouplingEdge":
        require_schema(payload, COUPLING_EDGE_SCHEMA)
        raw_mapping = payload.get("mapping")
        raw_conversion = payload.get("conversion")
        return cls(
            edge_id=payload["edge_id"],
            source=PortRef.from_dict(payload["source"]),
            target=PortRef.from_dict(payload["target"]),
            reduction=ReductionOperator(
                payload.get("reduction", "none")
            ),
            mapping=(
                None
                if raw_mapping is None
                else FieldMappingDefinition.from_dict(raw_mapping)
            ),
            conversion=(
                None
                if raw_conversion is None
                else EnergyConversion.from_dict(raw_conversion)
            ),
            transport_declaration=payload.get(
                "transport_declaration", ""
            ),
            coordinate_transform_id=payload.get(
                "coordinate_transform_id", ""
            ),
            description=payload.get("description", ""),
        )


@dataclass(frozen=True)
class PhysicsGraph:
    graph_id: str
    participants: tuple[ParticipantSpec, ...]
    edges: tuple[CouplingEdge, ...]
    frame_transforms: tuple[FrameTransform, ...] = ()
    conservation: tuple[CoupledConservation, ...] = ()
    description: str = ""

    def __post_init__(self) -> None:
        graph_id = str(self.graph_id).strip()
        if not graph_id:
            raise InvalidScientificProblem("PhysicsGraph requires graph_id")
        participants = tuple(self.participants)
        edges = tuple(self.edges)
        transforms = tuple(self.frame_transforms)
        conservation = tuple(self.conservation)

        if not participants or any(
            not isinstance(item, ParticipantSpec)
            for item in participants
        ):
            raise InvalidScientificProblem(
                "PhysicsGraph requires ParticipantSpec records"
            )
        if any(not isinstance(item, CouplingEdge) for item in edges):
            raise InvalidScientificProblem(
                "PhysicsGraph edges must be CouplingEdge records"
            )
        if any(
            not isinstance(item, FrameTransform)
            for item in transforms
        ):
            raise InvalidScientificProblem(
                "PhysicsGraph frame_transforms must be FrameTransform records"
            )
        if any(
            not isinstance(item, CoupledConservation)
            for item in conservation
        ):
            raise InvalidScientificProblem(
                "PhysicsGraph conservation entries must be CoupledConservation"
            )

        def unique(label: str, values: list[str]) -> None:
            duplicates = sorted(
                {value for value in values if values.count(value) > 1}
            )
            if duplicates:
                raise InvalidScientificProblem(
                    f"PhysicsGraph duplicate {label}: {duplicates}"
                )

        unique(
            "participant ids",
            [item.participant_id for item in participants],
        )
        unique("edge ids", [item.edge_id for item in edges])
        unique(
            "frame transform ids",
            [item.transform_id for item in transforms],
        )
        unique(
            "conservation ids",
            [item.balance_id for item in conservation],
        )

        object.__setattr__(self, "graph_id", graph_id)
        object.__setattr__(
            self,
            "participants",
            tuple(
                sorted(
                    participants,
                    key=lambda item: item.participant_id,
                )
            ),
        )
        object.__setattr__(
            self,
            "edges",
            tuple(sorted(edges, key=lambda item: item.edge_id)),
        )
        object.__setattr__(
            self,
            "frame_transforms",
            tuple(
                sorted(
                    transforms,
                    key=lambda item: item.transform_id,
                )
            ),
        )
        object.__setattr__(
            self,
            "conservation",
            tuple(
                sorted(
                    conservation,
                    key=lambda item: item.balance_id,
                )
            ),
        )
        object.__setattr__(
            self, "description", str(self.description).strip()
        )

        self._validate_edges()
        self._validate_fan_in()
        self._validate_conservation()

        referenced = {
            edge.coordinate_transform_id
            for edge in self.edges
            if edge.coordinate_transform_id
        }
        declared = {
            transform.transform_id
            for transform in self.frame_transforms
        }
        unused = sorted(declared - referenced)
        if unused:
            raise InvalidScientificProblem(
                f"PhysicsGraph carries unused frame transforms {unused}"
            )

    def participant(self, participant_id: str) -> ParticipantSpec:
        for participant in self.participants:
            if participant.participant_id == participant_id:
                return participant
        raise InvalidScientificProblem(
            f"unknown participant {participant_id!r}"
        )

    def edge(self, edge_id: str) -> CouplingEdge:
        for edge in self.edges:
            if edge.edge_id == edge_id:
                return edge
        raise InvalidScientificProblem(
            f"unknown coupling edge {edge_id!r}"
        )

    def frame_transform(self, transform_id: str) -> FrameTransform:
        for transform in self.frame_transforms:
            if transform.transform_id == transform_id:
                return transform
        raise InvalidScientificProblem(
            f"unknown frame transform {transform_id!r}"
        )

    def incoming(self, participant_id: str) -> tuple[CouplingEdge, ...]:
        self.participant(participant_id)
        return tuple(
            edge
            for edge in self.edges
            if edge.target.participant_id == participant_id
        )

    def outgoing(self, participant_id: str) -> tuple[CouplingEdge, ...]:
        self.participant(participant_id)
        return tuple(
            edge
            for edge in self.edges
            if edge.source.participant_id == participant_id
        )

    def _validate_edges(self) -> None:
        energy_like = set(ENERGY_DIMENSIONS) | set(
            ENERGY_DERIVED_DIMENSIONS
        )
        for edge in self.edges:
            if edge.source.participant_id == edge.target.participant_id:
                raise InvalidScientificProblem(
                    f"edge {edge.edge_id!r} connects two ports of participant "
                    f"{edge.source.participant_id!r}; internal physics belongs "
                    "inside the participant"
                )
            source_participant = self.participant(
                edge.source.participant_id
            )
            target_participant = self.participant(
                edge.target.participant_id
            )
            source = source_participant.port(edge.source.port_id)
            target = target_participant.port(edge.target.port_id)

            if source.direction is not PortDirection.OUTPUT:
                raise InvalidScientificProblem(
                    f"edge {edge.edge_id!r} source {edge.source.key} is not output"
                )
            if target.direction is not PortDirection.INPUT:
                raise InvalidScientificProblem(
                    f"edge {edge.edge_id!r} target {edge.target.key} is not input"
                )
            if source.kind is not target.kind:
                raise InvalidScientificProblem(
                    f"edge {edge.edge_id!r} connects {source.kind.value} to "
                    f"{target.kind.value}"
                )
            if source.dimension != target.dimension:
                raise InvalidScientificProblem(
                    f"edge {edge.edge_id!r} dimension mismatch "
                    f"[{source.dimension}] -> [{target.dimension}]"
                )

            if source.kind is PortKind.FIELD:
                assert source.field is not None
                assert target.field is not None
                if source.algebra is not target.algebra:
                    raise InvalidScientificProblem(
                        f"edge {edge.edge_id!r} connects field algebra "
                        f"{source.algebra.value} to {target.algebra.value}"
                    )
                if edge.mapping is None:
                    raise InvalidScientificProblem(
                        f"field edge {edge.edge_id!r} requires explicit mapping"
                    )
                if edge.conversion is not None:
                    raise InvalidScientificProblem(
                        f"field edge {edge.edge_id!r} cannot use scalar "
                        "EnergyConversion"
                    )
                if (
                    source.dimension in energy_like
                    and not edge.transport_declaration
                ):
                    raise InvalidScientificProblem(
                        f"field edge {edge.edge_id!r} carries an energy/power-like "
                        "dimension and must explicitly state transport semantics"
                    )
            else:
                if edge.mapping is not None:
                    raise InvalidScientificProblem(
                        f"scalar edge {edge.edge_id!r} cannot declare field mapping"
                    )
                QuantityDependency(
                    source_problem_id=edge.source.participant_id,
                    source_quantity=source.quantity,
                    target_problem_id=edge.target.participant_id,
                    target_quantity=target.quantity,
                    unit_exemplar=source.unit,
                    name=edge.edge_id,
                    description=edge.description,
                    conversion=edge.conversion,
                    transport_declaration=edge.transport_declaration,
                )

            if source.coordinate_frame == target.coordinate_frame:
                if edge.coordinate_transform_id:
                    raise InvalidScientificProblem(
                        f"edge {edge.edge_id!r} declares frame transform "
                        f"{edge.coordinate_transform_id!r} but both ports share "
                        f"frame {source.coordinate_frame!r}"
                    )
            else:
                if source.algebra not in (
                    FieldAlgebra.VECTOR,
                    FieldAlgebra.TENSOR_2,
                ):
                    raise InvalidScientificProblem(
                        f"edge {edge.edge_id!r} changes frame for "
                        f"{source.algebra.value} data without defined semantics"
                    )
                if not edge.coordinate_transform_id:
                    raise InvalidScientificProblem(
                        f"edge {edge.edge_id!r} crosses frames "
                        f"{source.coordinate_frame!r}->{target.coordinate_frame!r} "
                        "without transform"
                    )
                transform = self.frame_transform(
                    edge.coordinate_transform_id
                )
                if (
                    transform.source_frame != source.coordinate_frame
                    or transform.target_frame != target.coordinate_frame
                ):
                    raise InvalidScientificProblem(
                        f"edge {edge.edge_id!r} transform frames disagree with ports"
                    )
                expected_components = (
                    transform.dimension
                    if source.algebra is FieldAlgebra.VECTOR
                    else transform.dimension * transform.dimension
                )
                assert source.field is not None
                if source.field.components != expected_components:
                    raise InvalidScientificProblem(
                        f"edge {edge.edge_id!r} transform is "
                        f"{transform.dimension}D but field stores "
                        f"{source.field.components} components"
                    )

    def _validate_fan_in(self) -> None:
        groups: dict[PortRef, list[CouplingEdge]] = {}
        for edge in self.edges:
            groups.setdefault(edge.target, []).append(edge)
        for target, edges in groups.items():
            reductions = {edge.reduction for edge in edges}
            if len(edges) == 1:
                if reductions != {ReductionOperator.NONE}:
                    raise InvalidScientificProblem(
                        f"single-source target {target.key} must not declare a "
                        "fan-in reduction"
                    )
                continue
            if len(reductions) != 1 or ReductionOperator.NONE in reductions:
                raise InvalidScientificProblem(
                    f"fan-in target {target.key} requires one explicit common "
                    f"reduction; got {sorted(item.value for item in reductions)}"
                )

    def _validate_conservation(self) -> None:
        for balance in self.conservation:
            for binding in balance.terms:
                edge = self.edge(binding.edge_id)
                source = self.participant(
                    edge.source.participant_id
                ).port(edge.source.port_id)
                if source.kind is PortKind.FIELD:
                    raise InvalidScientificProblem(
                        f"conservation {balance.balance_id!r} binds field edge "
                        f"{edge.edge_id!r}; spatial conservation belongs to "
                        "mapping diagnostics"
                    )
                if (
                    balance.tolerance.dimensionality
                    != source.dimension
                ):
                    raise InvalidScientificProblem(
                        f"conservation {balance.balance_id!r} tolerance "
                        f"[{balance.tolerance.dimensionality}] differs from "
                        f"edge {edge.edge_id!r} [{source.dimension}]"
                    )
                if binding.measure is TransferMeasure.LOSS:
                    if edge.conversion is None:
                        raise InvalidScientificProblem(
                            f"conservation term {binding.name!r} asks for loss "
                            f"on edge {edge.edge_id!r} without conversion"
                        )
                    forms = {
                        loss.form
                        for loss in edge.conversion.losses
                    }
                    if binding.loss_form not in forms:
                        raise InvalidScientificProblem(
                            f"conservation term {binding.name!r} asks for "
                            f"{binding.loss_form!r}; edge declares {sorted(forms)}"
                        )

    def strongly_connected_components(
        self,
    ) -> tuple[tuple[str, ...], ...]:
        """Tarjan SCCs in deterministic order."""
        adjacency = {
            participant.participant_id: []
            for participant in self.participants
        }
        for edge in self.edges:
            adjacency[edge.source.participant_id].append(
                edge.target.participant_id
            )
        for values in adjacency.values():
            values.sort()

        index = 0
        indices: dict[str, int] = {}
        low: dict[str, int] = {}
        stack: list[str] = []
        on_stack: set[str] = set()
        components: list[tuple[str, ...]] = []

        def visit(node: str) -> None:
            nonlocal index
            indices[node] = index
            low[node] = index
            index += 1
            stack.append(node)
            on_stack.add(node)
            for target in adjacency[node]:
                if target not in indices:
                    visit(target)
                    low[node] = min(low[node], low[target])
                elif target in on_stack:
                    low[node] = min(low[node], indices[target])
            if low[node] == indices[node]:
                component: list[str] = []
                while True:
                    item = stack.pop()
                    on_stack.remove(item)
                    component.append(item)
                    if item == node:
                        break
                components.append(tuple(sorted(component)))

        for node in sorted(adjacency):
            if node not in indices:
                visit(node)
        return tuple(sorted(components))

    def cyclic_edge_ids(self) -> frozenset[str]:
        cyclic_groups = [
            set(component)
            for component in self.strongly_connected_components()
            if len(component) > 1
        ]
        return frozenset(
            edge.edge_id
            for edge in self.edges
            if any(
                edge.source.participant_id in group
                and edge.target.participant_id in group
                for group in cyclic_groups
            )
        )

    @property
    def cyclic(self) -> bool:
        return bool(self.cyclic_edge_ids())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": PHYSICS_GRAPH_SCHEMA,
            "graph_id": self.graph_id,
            "participants": [
                participant.to_dict()
                for participant in self.participants
            ],
            "edges": [edge.to_dict() for edge in self.edges],
            "frame_transforms": [
                transform.to_dict()
                for transform in self.frame_transforms
            ],
            "conservation": [
                item.to_dict() for item in self.conservation
            ],
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "PhysicsGraph":
        require_schema(payload, PHYSICS_GRAPH_SCHEMA)
        return cls(
            graph_id=payload["graph_id"],
            participants=tuple(
                ParticipantSpec.from_dict(item)
                for item in payload["participants"]
            ),
            edges=tuple(
                CouplingEdge.from_dict(item)
                for item in payload["edges"]
            ),
            frame_transforms=tuple(
                FrameTransform.from_dict(item)
                for item in payload.get("frame_transforms", ())
            ),
            conservation=tuple(
                CoupledConservation.from_dict(item)
                for item in payload.get("conservation", ())
            ),
            description=payload.get("description", ""),
        )
