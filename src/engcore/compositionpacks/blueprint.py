"""Cross-domain topology blueprints and execution-policy templates.

SystemGraphBlueprint owns scientific topology only. CouplingPolicyTemplate owns
iteration/convergence policy only. TimePolicy is supplied later by the planner
or execution request, so the same system topology is reusable across studies.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ..planning.blueprint import ParticipantBinding, ParticipantBlueprint
from ..scientific.errors import InvalidScientificProblem
from ..scientific.fields import MeshSupport, read_mesh_support
from ..scientific.multiphysics import (
    CoupledConservation,
    CouplingEdge,
    CouplingPlan,
    CouplingScheme,
    ConvergenceCriterion,
    FrameTransform,
    IterationSemantics,
    PhysicsGraph,
    RelaxationPolicy,
    TimePolicy,
)
from ..scientific.serialization import require_schema, schema_string

SYSTEM_GRAPH_BLUEPRINT_SCHEMA = schema_string(
    "composition_system_graph_blueprint"
)
COUPLING_POLICY_TEMPLATE_SCHEMA = schema_string(
    "composition_coupling_policy_template"
)


@dataclass(frozen=True)
class SystemGraphBlueprint:
    blueprint_id: str
    version: str
    capability_id: str
    participants: tuple[ParticipantBlueprint, ...]
    edges: tuple[CouplingEdge, ...]
    supports: tuple[MeshSupport, ...] = ()
    frame_transforms: tuple[FrameTransform, ...] = ()
    conservation: tuple[CoupledConservation, ...] = ()
    description: str = ""

    def __post_init__(self) -> None:
        for label in ("blueprint_id", "version", "capability_id"):
            value = str(getattr(self, label)).strip()
            if not value:
                raise InvalidScientificProblem(
                    f"system graph blueprint requires {label}"
                )
            object.__setattr__(self, label, value)
        participants = tuple(self.participants)
        edges = tuple(self.edges)
        if not participants or any(
            not isinstance(item, ParticipantBlueprint)
            for item in participants
        ):
            raise InvalidScientificProblem(
                "system graph blueprint requires ParticipantBlueprint records"
            )
        if any(not isinstance(item, CouplingEdge) for item in edges):
            raise InvalidScientificProblem(
                "system graph blueprint edges must be CouplingEdge records"
            )
        ids = [item.participant_id for item in participants]
        if len(ids) != len(set(ids)):
            raise InvalidScientificProblem(
                "system graph blueprint participant ids must be unique"
            )
        by_id = {item.participant_id: item for item in participants}
        for edge in edges:
            for ref in (edge.source, edge.target):
                participant = by_id.get(ref.participant_id)
                if participant is None:
                    raise InvalidScientificProblem(
                        f"edge {edge.edge_id!r} references undeclared "
                        f"participant {ref.participant_id!r}"
                    )
                if ref.port_id not in {
                    port.port_id for port in participant.ports
                }:
                    raise InvalidScientificProblem(
                        f"edge {edge.edge_id!r} references undeclared "
                        f"port {ref.key}"
                    )
        object.__setattr__(
            self,
            "participants",
            tuple(sorted(participants, key=lambda item: item.participant_id)),
        )
        object.__setattr__(
            self,
            "edges",
            tuple(sorted(edges, key=lambda item: item.edge_id)),
        )
        object.__setattr__(
            self,
            "supports",
            tuple(sorted(self.supports, key=lambda item: item.mesh_id)),
        )
        object.__setattr__(
            self,
            "frame_transforms",
            tuple(
                sorted(
                    self.frame_transforms,
                    key=lambda item: item.transform_id,
                )
            ),
        )
        object.__setattr__(
            self,
            "conservation",
            tuple(
                sorted(
                    self.conservation,
                    key=lambda item: item.balance_id,
                )
            ),
        )
        object.__setattr__(self, "description", str(self.description).strip())

    @property
    def key(self) -> tuple[str, str]:
        return self.blueprint_id, self.version

    def materialize(
        self,
        bindings: Mapping[str, ParticipantBinding],
        *,
        graph_id: str,
    ) -> PhysicsGraph:
        expected = {item.participant_id for item in self.participants}
        if set(bindings) != expected:
            raise InvalidScientificProblem(
                "system blueprint bindings mismatch; "
                f"missing={sorted(expected-set(bindings))}, "
                f"extra={sorted(set(bindings)-expected)}"
            )
        return PhysicsGraph(
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

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SYSTEM_GRAPH_BLUEPRINT_SCHEMA,
            "blueprint_id": self.blueprint_id,
            "version": self.version,
            "capability_id": self.capability_id,
            "participants": [
                item.to_dict() for item in self.participants
            ],
            "edges": [item.to_dict() for item in self.edges],
            "supports": [item.to_dict() for item in self.supports],
            "frame_transforms": [
                item.to_dict() for item in self.frame_transforms
            ],
            "conservation": [
                item.to_dict() for item in self.conservation
            ],
            "description": self.description,
        }

    @classmethod
    def from_dict(
        cls,
        payload: Mapping[str, Any],
    ) -> "SystemGraphBlueprint":
        require_schema(payload, SYSTEM_GRAPH_BLUEPRINT_SCHEMA)
        return cls(
            blueprint_id=payload["blueprint_id"],
            version=payload["version"],
            capability_id=payload["capability_id"],
            participants=tuple(
                ParticipantBlueprint.from_dict(item)
                for item in payload["participants"]
            ),
            edges=tuple(
                CouplingEdge.from_dict(item)
                for item in payload["edges"]
            ),
            supports=tuple(
                read_mesh_support(item)
                for item in payload.get("supports", ())
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


@dataclass(frozen=True)
class CouplingPolicyTemplate:
    template_id: str
    version: str
    blueprint_id: str
    scheme: CouplingScheme
    iteration_semantics: IterationSemantics
    participant_order: tuple[str, ...] = ()
    criteria: tuple[ConvergenceCriterion, ...] = ()
    relaxation: RelaxationPolicy = RelaxationPolicy()
    max_iterations: int = 1
    fail_on_nonconvergence: bool = True

    def __post_init__(self) -> None:
        for label in ("template_id", "version", "blueprint_id"):
            value = str(getattr(self, label)).strip()
            if not value:
                raise InvalidScientificProblem(
                    f"coupling policy template requires {label}"
                )
            object.__setattr__(self, label, value)
        object.__setattr__(self, "scheme", CouplingScheme(self.scheme))
        object.__setattr__(
            self,
            "iteration_semantics",
            IterationSemantics(self.iteration_semantics),
        )
        order = tuple(str(item).strip() for item in self.participant_order)
        if any(not item for item in order) or len(order) != len(set(order)):
            raise InvalidScientificProblem(
                "participant_order must contain unique non-empty ids"
            )
        object.__setattr__(self, "participant_order", order)
        criteria = tuple(self.criteria)
        if any(
            not isinstance(item, ConvergenceCriterion)
            for item in criteria
        ):
            raise InvalidScientificProblem(
                "template criteria must be ConvergenceCriterion records"
            )
        object.__setattr__(
            self,
            "criteria",
            tuple(sorted(criteria, key=lambda item: item.edge_id)),
        )
        if not isinstance(self.relaxation, RelaxationPolicy):
            raise InvalidScientificProblem(
                "template relaxation must be RelaxationPolicy"
            )
        if (
            isinstance(self.max_iterations, bool)
            or not isinstance(self.max_iterations, int)
            or self.max_iterations < 1
        ):
            raise InvalidScientificProblem(
                "template max_iterations must be positive int"
            )
        if not isinstance(self.fail_on_nonconvergence, bool):
            raise InvalidScientificProblem(
                "template fail_on_nonconvergence must be boolean"
            )

    @property
    def key(self) -> tuple[str, str]:
        return self.template_id, self.version

    def materialize(
        self,
        time: TimePolicy,
        *,
        plan_id: str | None = None,
    ) -> CouplingPlan:
        if not isinstance(time, TimePolicy):
            raise TypeError(
                "CouplingPolicyTemplate.materialize requires TimePolicy"
            )
        return CouplingPlan(
            plan_id=plan_id or f"{self.template_id}.{self.version}",
            scheme=self.scheme,
            iteration_semantics=self.iteration_semantics,
            time=time,
            participant_order=self.participant_order,
            criteria=self.criteria,
            relaxation=self.relaxation,
            max_iterations=self.max_iterations,
            fail_on_nonconvergence=self.fail_on_nonconvergence,
        )

    def validate_against_blueprint(
        self,
        blueprint: SystemGraphBlueprint,
    ) -> None:
        if self.blueprint_id != blueprint.blueprint_id:
            raise InvalidScientificProblem(
                f"coupling template {self.template_id!r} targets "
                f"{self.blueprint_id!r}, not {blueprint.blueprint_id!r}"
            )
        participants = {
            item.participant_id for item in blueprint.participants
        }
        if self.participant_order and set(self.participant_order) != participants:
            raise InvalidScientificProblem(
                "coupling template participant_order does not match blueprint"
            )
        edge_ids = {item.edge_id for item in blueprint.edges}
        unknown = sorted(
            item.edge_id
            for item in self.criteria
            if item.edge_id not in edge_ids
        )
        if unknown:
            raise InvalidScientificProblem(
                f"coupling template criteria reference unknown edges {unknown}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": COUPLING_POLICY_TEMPLATE_SCHEMA,
            "template_id": self.template_id,
            "version": self.version,
            "blueprint_id": self.blueprint_id,
            "scheme": self.scheme.value,
            "iteration_semantics": self.iteration_semantics.value,
            "participant_order": list(self.participant_order),
            "criteria": [item.to_dict() for item in self.criteria],
            "relaxation": self.relaxation.to_dict(),
            "max_iterations": self.max_iterations,
            "fail_on_nonconvergence": self.fail_on_nonconvergence,
        }

    @classmethod
    def from_dict(
        cls,
        payload: Mapping[str, Any],
    ) -> "CouplingPolicyTemplate":
        require_schema(payload, COUPLING_POLICY_TEMPLATE_SCHEMA)
        return cls(
            template_id=payload["template_id"],
            version=payload["version"],
            blueprint_id=payload["blueprint_id"],
            scheme=CouplingScheme(payload["scheme"]),
            iteration_semantics=IterationSemantics(
                payload["iteration_semantics"]
            ),
            participant_order=tuple(
                payload.get("participant_order", ())
            ),
            criteria=tuple(
                ConvergenceCriterion.from_dict(item)
                for item in payload.get("criteria", ())
            ),
            relaxation=RelaxationPolicy.from_dict(
                payload["relaxation"]
            ),
            max_iterations=payload.get("max_iterations", 1),
            fail_on_nonconvergence=payload.get(
                "fail_on_nonconvergence",
                True,
            ),
        )


__all__ = [
    "COUPLING_POLICY_TEMPLATE_SCHEMA",
    "SYSTEM_GRAPH_BLUEPRINT_SCHEMA",
    "CouplingPolicyTemplate",
    "SystemGraphBlueprint",
]
