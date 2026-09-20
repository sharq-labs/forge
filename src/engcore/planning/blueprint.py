"""Declarative bridge from planner selections to the generic multiphysics graph.

A blueprint is owned by a domain/system pack.  The generic planner never knows
what a battery, motor or HVAC loop is; it only materializes declared participant
ports/edges after model, realization and solver choices have been made.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from ..scientific.errors import InvalidScientificProblem
from ..scientific.fields import MeshSupport, StructuredMesh, UnstructuredMesh, read_mesh_support
from ..scientific.multiphysics import (
    CoupledConservation,
    CouplingEdge,
    CouplingPlan,
    FrameTransform,
    ParticipantSpec,
    PhysicsGraph,
    PortDefinition,
)
from ..scientific.serialization import require_schema, schema_string
from ..scientific.units.quantity import Quantity

PARTICIPANT_BLUEPRINT_SCHEMA = schema_string("planning_participant_blueprint")
GRAPH_BLUEPRINT_SCHEMA = schema_string("planning_graph_blueprint")
PARTICIPANT_BINDING_SCHEMA = schema_string("planning_participant_binding")


@dataclass(frozen=True)
class ParticipantBinding:
    participant_id: str
    realization_id: str
    realization_version: str
    solver_id: str
    solver_version: str

    def __post_init__(self) -> None:
        for label in (
            "participant_id",
            "realization_id",
            "realization_version",
            "solver_id",
            "solver_version",
        ):
            value = str(getattr(self, label)).strip()
            if not value:
                raise InvalidScientificProblem(f"participant binding requires {label}")
            object.__setattr__(self, label, value)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": PARTICIPANT_BINDING_SCHEMA,
            "participant_id": self.participant_id,
            "realization_id": self.realization_id,
            "realization_version": self.realization_version,
            "solver_id": self.solver_id,
            "solver_version": self.solver_version,
        }


@dataclass(frozen=True)
class ParticipantBlueprint:
    participant_id: str
    model_id: str
    model_version: str
    adapter_id: str
    adapter_version: str
    ports: tuple[PortDefinition, ...]
    transient: bool = False
    checkpointable: bool = False
    deterministic_restore: bool = False
    event_capable: bool = False
    preferred_time_step: Quantity | None = None
    maximum_time_step: Quantity | None = None
    description: str = ""

    def __post_init__(self) -> None:
        for label in (
            "participant_id",
            "model_id",
            "model_version",
            "adapter_id",
            "adapter_version",
        ):
            value = str(getattr(self, label)).strip()
            if not value:
                raise InvalidScientificProblem(f"participant blueprint requires {label}")
            object.__setattr__(self, label, value)
        ports = tuple(self.ports)
        if not ports or any(not isinstance(port, PortDefinition) for port in ports):
            raise InvalidScientificProblem(
                f"participant blueprint {self.participant_id!r} requires PortDefinition records"
            )
        ids = [port.port_id for port in ports]
        if len(ids) != len(set(ids)):
            raise InvalidScientificProblem(
                f"participant blueprint {self.participant_id!r} has duplicate ports"
            )
        object.__setattr__(self, "ports", tuple(sorted(ports, key=lambda port: port.port_id)))
        object.__setattr__(self, "description", str(self.description).strip())

    def materialize(self, binding: ParticipantBinding) -> ParticipantSpec:
        if binding.participant_id != self.participant_id:
            raise InvalidScientificProblem(
                f"binding {binding.participant_id!r} cannot materialize participant {self.participant_id!r}"
            )
        return ParticipantSpec(
            participant_id=self.participant_id,
            model_id=self.model_id,
            model_version=self.model_version,
            realization_id=binding.realization_id,
            realization_version=binding.realization_version,
            solver_id=binding.solver_id,
            solver_version=binding.solver_version,
            adapter_id=self.adapter_id,
            adapter_version=self.adapter_version,
            ports=self.ports,
            transient=self.transient,
            checkpointable=self.checkpointable,
            deterministic_restore=self.deterministic_restore,
            event_capable=self.event_capable,
            preferred_time_step=self.preferred_time_step,
            maximum_time_step=self.maximum_time_step,
            description=self.description,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": PARTICIPANT_BLUEPRINT_SCHEMA,
            "participant_id": self.participant_id,
            "model_id": self.model_id,
            "model_version": self.model_version,
            "adapter_id": self.adapter_id,
            "adapter_version": self.adapter_version,
            "ports": [port.to_dict() for port in self.ports],
            "transient": self.transient,
            "checkpointable": self.checkpointable,
            "deterministic_restore": self.deterministic_restore,
            "event_capable": self.event_capable,
            "preferred_time_step": None if self.preferred_time_step is None else self.preferred_time_step.to_dict(),
            "maximum_time_step": None if self.maximum_time_step is None else self.maximum_time_step.to_dict(),
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ParticipantBlueprint":
        require_schema(payload, PARTICIPANT_BLUEPRINT_SCHEMA)
        preferred = payload.get("preferred_time_step")
        maximum = payload.get("maximum_time_step")
        return cls(
            participant_id=payload["participant_id"],
            model_id=payload["model_id"],
            model_version=payload["model_version"],
            adapter_id=payload["adapter_id"],
            adapter_version=payload["adapter_version"],
            ports=tuple(PortDefinition.from_dict(item) for item in payload["ports"]),
            transient=payload.get("transient", False),
            checkpointable=payload.get("checkpointable", False),
            deterministic_restore=payload.get("deterministic_restore", False),
            event_capable=payload.get("event_capable", False),
            preferred_time_step=None if preferred is None else Quantity.from_dict(preferred),
            maximum_time_step=None if maximum is None else Quantity.from_dict(maximum),
            description=payload.get("description", ""),
        )


@dataclass(frozen=True)
class PhysicsGraphBlueprint:
    blueprint_id: str
    version: str
    capability_id: str
    participants: tuple[ParticipantBlueprint, ...]
    edges: tuple[CouplingEdge, ...]
    coupling_plan: CouplingPlan
    supports: tuple[MeshSupport, ...] = ()
    frame_transforms: tuple[FrameTransform, ...] = ()
    conservation: tuple[CoupledConservation, ...] = ()
    description: str = ""

    def __post_init__(self) -> None:
        for label in ("blueprint_id", "version", "capability_id"):
            value = str(getattr(self, label)).strip()
            if not value:
                raise InvalidScientificProblem(f"graph blueprint requires {label}")
            object.__setattr__(self, label, value)
        participants = tuple(self.participants)
        edges = tuple(self.edges)
        if not participants or any(not isinstance(item, ParticipantBlueprint) for item in participants):
            raise InvalidScientificProblem("graph blueprint requires participant blueprints")
        if any(not isinstance(item, CouplingEdge) for item in edges):
            raise InvalidScientificProblem("graph blueprint edges must be CouplingEdge records")
        ids = [item.participant_id for item in participants]
        if len(ids) != len(set(ids)):
            raise InvalidScientificProblem("graph blueprint participant ids must be unique")
        by_id = {item.participant_id: item for item in participants}
        for edge in edges:
            for ref in (edge.source, edge.target):
                participant = by_id.get(ref.participant_id)
                if participant is None:
                    raise InvalidScientificProblem(
                        f"edge {edge.edge_id!r} references undeclared participant {ref.participant_id!r}"
                    )
                if ref.port_id not in {port.port_id for port in participant.ports}:
                    raise InvalidScientificProblem(
                        f"edge {edge.edge_id!r} references undeclared port {ref.key}"
                    )
        if not isinstance(self.coupling_plan, CouplingPlan):
            raise InvalidScientificProblem("graph blueprint requires a CouplingPlan")
        object.__setattr__(self, "participants", tuple(sorted(participants, key=lambda x: x.participant_id)))
        object.__setattr__(self, "edges", tuple(sorted(edges, key=lambda x: x.edge_id)))
        object.__setattr__(self, "supports", tuple(sorted(self.supports, key=lambda x: x.mesh_id)))
        object.__setattr__(self, "frame_transforms", tuple(sorted(self.frame_transforms, key=lambda x: x.transform_id)))
        object.__setattr__(self, "conservation", tuple(sorted(self.conservation, key=lambda x: x.balance_id)))
        object.__setattr__(self, "description", str(self.description).strip())

    @property
    def key(self) -> tuple[str, str]:
        return (self.blueprint_id, self.version)

    def materialize(
        self,
        bindings: Mapping[str, ParticipantBinding],
        *,
        graph_id: str,
    ) -> tuple[PhysicsGraph, CouplingPlan]:
        expected = {item.participant_id for item in self.participants}
        if set(bindings) != expected:
            raise InvalidScientificProblem(
                f"blueprint bindings mismatch; missing={sorted(expected-set(bindings))}, "
                f"extra={sorted(set(bindings)-expected)}"
            )
        graph = PhysicsGraph(
            graph_id=graph_id,
            participants=tuple(
                item.materialize(bindings[item.participant_id])
                for item in self.participants
            ),
            edges=self.edges,
            supports=self.supports,
            frame_transforms=self.frame_transforms,
            conservation=self.conservation,
            description=self.description,
        )
        self.coupling_plan.validate_against(graph)
        return graph, self.coupling_plan

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": GRAPH_BLUEPRINT_SCHEMA,
            "blueprint_id": self.blueprint_id,
            "version": self.version,
            "capability_id": self.capability_id,
            "participants": [item.to_dict() for item in self.participants],
            "edges": [item.to_dict() for item in self.edges],
            "coupling_plan": self.coupling_plan.to_dict(),
            "supports": [item.to_dict() for item in self.supports],
            "frame_transforms": [item.to_dict() for item in self.frame_transforms],
            "conservation": [item.to_dict() for item in self.conservation],
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "PhysicsGraphBlueprint":
        require_schema(payload, GRAPH_BLUEPRINT_SCHEMA)
        return cls(
            blueprint_id=payload["blueprint_id"],
            version=payload["version"],
            capability_id=payload["capability_id"],
            participants=tuple(ParticipantBlueprint.from_dict(item) for item in payload["participants"]),
            edges=tuple(CouplingEdge.from_dict(item) for item in payload["edges"]),
            coupling_plan=CouplingPlan.from_dict(payload["coupling_plan"]),
            supports=tuple(read_mesh_support(item) for item in payload.get("supports", ())),
            frame_transforms=tuple(FrameTransform.from_dict(item) for item in payload.get("frame_transforms", ())),
            conservation=tuple(CoupledConservation.from_dict(item) for item in payload.get("conservation", ())),
            description=payload.get("description", ""),
        )


class BlueprintRegistry:
    def __init__(self, blueprints: Iterable[PhysicsGraphBlueprint] = ()) -> None:
        self._items: dict[tuple[str, str], PhysicsGraphBlueprint] = {}
        for blueprint in blueprints:
            if not isinstance(blueprint, PhysicsGraphBlueprint):
                raise TypeError("BlueprintRegistry accepts PhysicsGraphBlueprint only")
            if blueprint.key in self._items:
                raise InvalidScientificProblem(f"duplicate planning blueprint {blueprint.key}")
            self._items[blueprint.key] = blueprint

    def for_capability(self, capability_id: str) -> tuple[PhysicsGraphBlueprint, ...]:
        return tuple(
            self._items[key]
            for key in sorted(self._items)
            if self._items[key].capability_id == capability_id
        )

    def get(self, blueprint_id: str, version: str) -> PhysicsGraphBlueprint:
        try:
            return self._items[(blueprint_id, version)]
        except KeyError:
            raise InvalidScientificProblem(
                f"no graph blueprint {blueprint_id!r}@{version!r}"
            ) from None

    def __iter__(self):
        for key in sorted(self._items):
            yield self._items[key]


__all__ = [
    "GRAPH_BLUEPRINT_SCHEMA",
    "PARTICIPANT_BINDING_SCHEMA",
    "PARTICIPANT_BLUEPRINT_SCHEMA",
    "BlueprintRegistry",
    "ParticipantBinding",
    "ParticipantBlueprint",
    "PhysicsGraphBlueprint",
]
