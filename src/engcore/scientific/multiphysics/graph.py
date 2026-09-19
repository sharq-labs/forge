"""Physics topology for arbitrary multiphysics systems.

The graph states *what is physically connected*. It deliberately does not state
iteration order, time windows, relaxation, checkpoint policy or solver
scheduling; those belong to CouplingPlan.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Mapping

from ..composition.conversion import EnergyConversion
from ..errors import InvalidScientificProblem
from ..serialization import require_schema, schema_string
from .mapping import FieldMappingDefinition
from .participant import ParticipantSpec
from .ports import PortDirection, PortKind, PortRef

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
    coordinate_transform_id: str = ""
    conservation_group: str = ""
    description: str = ""

    def __post_init__(self) -> None:
        edge_id = str(self.edge_id).strip()
        if not edge_id:
            raise InvalidScientificProblem("coupling edge requires edge_id")
        object.__setattr__(self, "edge_id", edge_id)
        if not isinstance(self.source, PortRef) or not isinstance(self.target, PortRef):
            raise InvalidScientificProblem("coupling edge endpoints must be PortRef")
        if self.source == self.target:
            raise InvalidScientificProblem("a coupling edge cannot feed a port into itself")
        object.__setattr__(self, "reduction", ReductionOperator(self.reduction))
        if self.mapping is not None and not isinstance(self.mapping, FieldMappingDefinition):
            raise InvalidScientificProblem("edge mapping must be FieldMappingDefinition")
        if self.conversion is not None and not isinstance(self.conversion, EnergyConversion):
            raise InvalidScientificProblem("edge conversion must be EnergyConversion")
        object.__setattr__(self, "coordinate_transform_id", str(self.coordinate_transform_id).strip())
        object.__setattr__(self, "conservation_group", str(self.conservation_group).strip())
        object.__setattr__(self, "description", str(self.description).strip())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": COUPLING_EDGE_SCHEMA,
            "edge_id": self.edge_id,
            "source": self.source.to_dict(),
            "target": self.target.to_dict(),
            "reduction": self.reduction.value,
            "mapping": None if self.mapping is None else self.mapping.to_dict(),
            "conversion": None if self.conversion is None else self.conversion.to_dict(),
            "coordinate_transform_id": self.coordinate_transform_id,
            "conservation_group": self.conservation_group,
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
            reduction=ReductionOperator(payload.get("reduction", "none")),
            mapping=None if raw_mapping is None else FieldMappingDefinition.from_dict(raw_mapping),
            conversion=None if raw_conversion is None else EnergyConversion.from_dict(raw_conversion),
            coordinate_transform_id=payload.get("coordinate_transform_id", ""),
            conservation_group=payload.get("conservation_group", ""),
            description=payload.get("description", ""),
        )


@dataclass(frozen=True)
class PhysicsGraph:
    graph_id: str
    participants: tuple[ParticipantSpec, ...]
    edges: tuple[CouplingEdge, ...]
    description: str = ""

    def __post_init__(self) -> None:
        graph_id = str(self.graph_id).strip()
        if not graph_id:
            raise InvalidScientificProblem("physics graph requires graph_id")
        object.__setattr__(self, "graph_id", graph_id)
        participants = tuple(self.participants)
        edges = tuple(self.edges)
        if not participants:
            raise InvalidScientificProblem("physics graph requires at least one participant")
        if any(not isinstance(p, ParticipantSpec) for p in participants):
            raise InvalidScientificProblem("physics graph participants must be ParticipantSpec")
        if any(not isinstance(e, CouplingEdge) for e in edges):
            raise InvalidScientificProblem("physics graph edges must be CouplingEdge")
        ids = [p.participant_id for p in participants]
        if len(ids) != len(set(ids)):
            raise InvalidScientificProblem("physics graph participant ids must be unique")
        edge_ids = [e.edge_id for e in edges]
        if len(edge_ids) != len(set(edge_ids)):
            raise InvalidScientificProblem("physics graph edge ids must be unique")
        object.__setattr__(self, "participants", tuple(sorted(participants, key=lambda p: p.participant_id)))
        object.__setattr__(self, "edges", tuple(sorted(edges, key=lambda e: e.edge_id)))
        object.__setattr__(self, "description", str(self.description).strip())
        self._validate_edges()
        self._validate_fan_in()

    def participant(self, participant_id: str) -> ParticipantSpec:
        for participant in self.participants:
            if participant.participant_id == participant_id:
                return participant
        raise InvalidScientificProblem(f"unknown participant {participant_id!r}")

    def edge(self, edge_id: str) -> CouplingEdge:
        for edge in self.edges:
            if edge.edge_id == edge_id:
                return edge
        raise InvalidScientificProblem(f"unknown coupling edge {edge_id!r}")

    def incoming(self, participant_id: str) -> tuple[CouplingEdge, ...]:
        return tuple(e for e in self.edges if e.target.participant_id == participant_id)

    def outgoing(self, participant_id: str) -> tuple[CouplingEdge, ...]:
        return tuple(e for e in self.edges if e.source.participant_id == participant_id)

    def _validate_edges(self) -> None:
        for edge in self.edges:
            source_participant = self.participant(edge.source.participant_id)
            target_participant = self.participant(edge.target.participant_id)
            source = source_participant.port(edge.source.port_id)
            target = target_participant.port(edge.target.port_id)
            if source.direction is not PortDirection.OUTPUT:
                raise InvalidScientificProblem(
                    f"edge {edge.edge_id!r} source {edge.source.key} is not an output"
                )
            if target.direction is not PortDirection.INPUT:
                raise InvalidScientificProblem(
                    f"edge {edge.edge_id!r} target {edge.target.key} is not an input"
                )
            if source.kind is not target.kind:
                raise InvalidScientificProblem(
                    f"edge {edge.edge_id!r} connects {source.kind.value} to {target.kind.value}"
                )
            if source.dimension != target.dimension:
                raise InvalidScientificProblem(
                    f"edge {edge.edge_id!r} connects [{source.dimension}] to [{target.dimension}]"
                )
            if source.kind is PortKind.FIELD:
                if edge.mapping is None:
                    raise InvalidScientificProblem(
                        f"field edge {edge.edge_id!r} must declare a mapping, including identity"
                    )
                if edge.conversion is not None:
                    raise InvalidScientificProblem(
                        f"field edge {edge.edge_id!r} cannot use scalar EnergyConversion"
                    )
            elif edge.mapping is not None:
                raise InvalidScientificProblem(
                    f"scalar edge {edge.edge_id!r} cannot declare a field mapping"
                )
            if (
                source.coordinate_frame != target.coordinate_frame
                and not edge.coordinate_transform_id
            ):
                raise InvalidScientificProblem(
                    f"edge {edge.edge_id!r} crosses coordinate frames "
                    f"{source.coordinate_frame!r}->{target.coordinate_frame!r} "
                    f"without a transform"
                )

    def _validate_fan_in(self) -> None:
        groups: dict[PortRef, list[CouplingEdge]] = {}
        for edge in self.edges:
            groups.setdefault(edge.target, []).append(edge)
        for target, edges in groups.items():
            if len(edges) == 1:
                continue
            reductions = {e.reduction for e in edges}
            if ReductionOperator.NONE in reductions or len(reductions) != 1:
                raise InvalidScientificProblem(
                    f"fan-in to {target.key} requires one explicit reduction operator; "
                    f"found {[e.reduction.value for e in edges]}"
                )

    def strongly_connected_components(self) -> tuple[tuple[str, ...], ...]:
        """Tarjan SCCs in stable order; cycles are topology, not an error."""
        adjacency = {
            p.participant_id: sorted(
                {e.target.participant_id for e in self.outgoing(p.participant_id)}
            )
            for p in self.participants
        }
        index = 0
        stack: list[str] = []
        on_stack: set[str] = set()
        indices: dict[str, int] = {}
        low: dict[str, int] = {}
        components: list[tuple[str, ...]] = []

        def visit(node: str) -> None:
            nonlocal index
            indices[node] = low[node] = index
            index += 1
            stack.append(node)
            on_stack.add(node)
            for other in adjacency[node]:
                if other not in indices:
                    visit(other)
                    low[node] = min(low[node], low[other])
                elif other in on_stack:
                    low[node] = min(low[node], indices[other])
            if low[node] == indices[node]:
                group = []
                while True:
                    other = stack.pop()
                    on_stack.remove(other)
                    group.append(other)
                    if other == node:
                        break
                components.append(tuple(sorted(group)))

        for participant in sorted(adjacency):
            if participant not in indices:
                visit(participant)
        return tuple(sorted(components, key=lambda group: group[0]))

    @property
    def cyclic(self) -> bool:
        for component in self.strongly_connected_components():
            if len(component) > 1:
                return True
            pid = component[0]
            if any(
                e.source.participant_id == pid and e.target.participant_id == pid
                for e in self.edges
            ):
                return True
        return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": PHYSICS_GRAPH_SCHEMA,
            "graph_id": self.graph_id,
            "participants": [p.to_dict() for p in self.participants],
            "edges": [e.to_dict() for e in self.edges],
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "PhysicsGraph":
        require_schema(payload, PHYSICS_GRAPH_SCHEMA)
        return cls(
            graph_id=payload["graph_id"],
            participants=tuple(ParticipantSpec.from_dict(p) for p in payload["participants"]),
            edges=tuple(CouplingEdge.from_dict(e) for e in payload["edges"]),
            description=payload.get("description", ""),
        )
