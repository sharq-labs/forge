"""Physics topology for arbitrary multiphysics systems.

The graph states *what is physically connected*. It deliberately does not state
iteration order, time windows, relaxation, checkpoint policy or solver
scheduling; those belong to CouplingPlan.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import math
from typing import Any, Mapping

from ..composition.conversion import ENERGY_DERIVED_DIMENSIONS, ENERGY_DIMENSIONS, EnergyConversion
from ..composition.dependency import QuantityDependency
from ..errors import InvalidScientificProblem
from ..fields.interface_transfer import InterfaceTransfer
from ..fields import (
    MeshSupport,
    StructuredMesh,
    UnstructuredMesh,
    read_mesh_support,
)
from ..serialization import require_schema, schema_string
from ..semantics import QuantityTransport, extend_payload, semantic_extension
from ..units.quantity import is_ratio_scale
from .conservation import CoupledConservation, TransferMeasure
from .frames import FrameTransform
from .mapping import FieldMappingDefinition
from .participant import ParticipantSpec
from .ports import FieldAlgebra, PortDirection, PortKind, PortRef

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
    transport: QuantityTransport | None = None
    interface_transfer: InterfaceTransfer | None = None

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
        object.__setattr__(self, "transport_declaration", str(self.transport_declaration).strip())
        object.__setattr__(self, "coordinate_transform_id", str(self.coordinate_transform_id).strip())
        object.__setattr__(self, "description", str(self.description).strip())
        if self.transport is not None:
            if not isinstance(self.transport, QuantityTransport):
                raise InvalidScientificProblem("edge transport must be QuantityTransport")
            if self.conversion is not None or self.transport_declaration:
                raise InvalidScientificProblem("structured transport cannot be combined with legacy conversion/prose")
        if self.interface_transfer is not None:
            if not isinstance(self.interface_transfer, InterfaceTransfer):
                raise InvalidScientificProblem("interface transfer must be typed")
            if self.transport is not None or self.conversion is not None or self.transport_declaration or self.coordinate_transform_id:
                raise InvalidScientificProblem("interface transfer cannot mix scalar conversions, prose or frame transforms")

    def to_dict(self) -> dict[str, Any]:
        payload = extend_payload({
            "schema": COUPLING_EDGE_SCHEMA,
            "edge_id": self.edge_id,
            "source": self.source.to_dict(),
            "target": self.target.to_dict(),
            "reduction": self.reduction.value,
            "mapping": None if self.mapping is None else self.mapping.to_dict(),
            "conversion": None if self.conversion is None else self.conversion.to_dict(),
            "transport_declaration": self.transport_declaration,
            "coordinate_transform_id": self.coordinate_transform_id,
            "description": self.description,
        }, "transport", self.transport)
        if self.interface_transfer is not None:
            payload["schema"] = "multiphysics_coupling_edge/3"
            payload["interface_transfer"] = self.interface_transfer.to_dict()
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CouplingEdge":
        raw_interface = None
        if payload.get("schema") == "multiphysics_coupling_edge/3":
            if payload.get("interface_transfer") is None or "transport" in payload:
                raise InvalidScientificProblem("interface edge /3 requires interface_transfer and no scalar transport")
            raw_interface = payload["interface_transfer"]
            raw_transport = None
        else:
            if "interface_transfer" in payload:
                raise InvalidScientificProblem("interface transfer requires explicit edge /3")
            raw_transport = semantic_extension(payload, COUPLING_EDGE_SCHEMA, "transport")
        raw_mapping = payload.get("mapping")
        raw_conversion = payload.get("conversion")
        return cls(
            edge_id=payload["edge_id"],
            source=PortRef.from_dict(payload["source"]),
            target=PortRef.from_dict(payload["target"]),
            reduction=ReductionOperator(payload.get("reduction", "none")),
            mapping=None if raw_mapping is None else FieldMappingDefinition.from_dict(raw_mapping),
            conversion=None if raw_conversion is None else EnergyConversion.from_dict(raw_conversion),
            transport_declaration=payload.get("transport_declaration", ""),
            coordinate_transform_id=payload.get("coordinate_transform_id", ""),
            description=payload.get("description", ""),
            transport=None if raw_transport is None else QuantityTransport.from_dict(raw_transport),
            interface_transfer=None if raw_interface is None else InterfaceTransfer.from_dict(raw_interface),
        )


@dataclass(frozen=True)
class PhysicsGraph:
    graph_id: str
    participants: tuple[ParticipantSpec, ...]
    edges: tuple[CouplingEdge, ...]
    supports: tuple[MeshSupport, ...] = ()
    frame_transforms: tuple[FrameTransform, ...] = ()
    conservation: tuple[CoupledConservation, ...] = ()
    description: str = ""

    def __post_init__(self) -> None:
        graph_id = str(self.graph_id).strip()
        if not graph_id:
            raise InvalidScientificProblem("physics graph requires graph_id")
        object.__setattr__(self, "graph_id", graph_id)
        participants = tuple(self.participants)
        edges = tuple(self.edges)
        supports = tuple(self.supports)
        frame_transforms = tuple(self.frame_transforms)
        conservation = tuple(self.conservation)
        if not participants:
            raise InvalidScientificProblem("physics graph requires at least one participant")
        if any(not isinstance(p, ParticipantSpec) for p in participants):
            raise InvalidScientificProblem("physics graph participants must be ParticipantSpec")
        if any(not isinstance(e, CouplingEdge) for e in edges):
            raise InvalidScientificProblem("physics graph edges must be CouplingEdge")
        if any(
            not isinstance(support, (StructuredMesh, UnstructuredMesh))
            for support in supports
        ):
            raise InvalidScientificProblem(
                "physics graph supports must be declared mesh supports"
            )
        if any(
            not isinstance(transform, FrameTransform)
            for transform in frame_transforms
        ):
            raise InvalidScientificProblem(
                "physics graph frame_transforms must be FrameTransform records"
            )
        if any(not isinstance(item, CoupledConservation) for item in conservation):
            raise InvalidScientificProblem("physics graph conservation entries must be CoupledConservation")
        ids = [p.participant_id for p in participants]
        if len(ids) != len(set(ids)):
            raise InvalidScientificProblem("physics graph participant ids must be unique")
        edge_ids = [e.edge_id for e in edges]
        if len(edge_ids) != len(set(edge_ids)):
            raise InvalidScientificProblem("physics graph edge ids must be unique")
        support_ids = [support.mesh_id for support in supports]
        if len(support_ids) != len(set(support_ids)):
            raise InvalidScientificProblem(
                "physics graph mesh support ids must be unique"
            )
        transform_ids = [
            transform.transform_id for transform in frame_transforms
        ]
        if len(transform_ids) != len(set(transform_ids)):
            raise InvalidScientificProblem(
                "physics graph frame transform ids must be unique"
            )
        balance_ids = [item.balance_id for item in conservation]
        if len(balance_ids) != len(set(balance_ids)):
            raise InvalidScientificProblem("physics graph conservation balance ids must be unique")
        object.__setattr__(self, "participants", tuple(sorted(participants, key=lambda p: p.participant_id)))
        object.__setattr__(self, "edges", tuple(sorted(edges, key=lambda e: e.edge_id)))
        object.__setattr__(self, "supports", tuple(sorted(supports, key=lambda support: support.mesh_id)))
        object.__setattr__(
            self,
            "frame_transforms",
            tuple(sorted(frame_transforms, key=lambda transform: transform.transform_id)),
        )
        object.__setattr__(self, "conservation", tuple(sorted(conservation, key=lambda item: item.balance_id)))
        object.__setattr__(self, "description", str(self.description).strip())
        self._validate_declared_supports()
        self._validate_edges()
        self._validate_fan_in()
        self._validate_conservation()

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

    def support(self, mesh_id: str) -> MeshSupport:
        for support in self.supports:
            if support.mesh_id == mesh_id:
                return support
        raise InvalidScientificProblem(
            f"unknown mesh support {mesh_id!r}"
        )

    def frame_transform(self, transform_id: str) -> FrameTransform:
        for transform in self.frame_transforms:
            if transform.transform_id == transform_id:
                return transform
        raise InvalidScientificProblem(
            f"unknown frame transform {transform_id!r}"
        )

    def _validate_declared_supports(self) -> None:
        declared = {support.mesh_id for support in self.supports}
        for participant in self.participants:
            for port in participant.ports:
                if port.kind is PortKind.FIELD:
                    assert port.field is not None
                    if port.field.mesh_id not in declared:
                        raise InvalidScientificProblem(
                            f"field port {participant.participant_id}."
                            f"{port.port_id} references mesh "
                            f"{port.field.mesh_id!r}, which the PhysicsGraph "
                            "does not declare"
                        )

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
            typed = source.semantics is not None or target.semantics is not None or edge.transport is not None
            typed_field = source.kind is PortKind.FIELD and (typed or source.field.semantics is not None or target.field.semantics is not None)
            if edge.interface_transfer is not None:
                if source.kind is not PortKind.FIELD or source.semantics != edge.interface_transfer.quantity or target.semantics != edge.interface_transfer.quantity:
                    raise InvalidScientificProblem("interface ports require exact typed physical quantity meaning")
                edge.interface_transfer.admit(source.field, self.support(source.field.mesh_id),
                                               target.field, self.support(target.field.mesh_id), edge.mapping)
                if source.algebra is not FieldAlgebra.SCALAR or target.algebra is not FieldAlgebra.SCALAR or edge.reduction is not ReductionOperator.NONE:
                    raise InvalidScientificProblem("interface vector projection/reduction is unsupported")
                typed_field = True
            elif typed_field:
                if (source.field.semantics is None or target.field.semantics is None
                        or source.semantics is None or target.semantics is None):
                    raise InvalidScientificProblem("A-3 typed fields require both field-kind and port quantity semantics")
                if (source.field.semantics.quantity != source.semantics
                        or target.field.semantics.quantity != target.semantics):
                    raise InvalidScientificProblem("port and field quantity meanings disagree")
                dimension = self.support(source.field.mesh_id).spatial_dimension
                source.field.semantics.require_cell_mapping(target.field.semantics, dimension)
                if (edge.transport is not None or source.coordinate_frame != target.coordinate_frame
                        or edge.coordinate_transform_id or source.algebra is not FieldAlgebra.SCALAR
                        or source.field.components != 1 or target.field.components != 1):
                    raise InvalidScientificProblem("typed fields require scalar common-frame mapping; scalar partitions and frame transforms unsupported")
                if edge.reduction is not ReductionOperator.NONE:
                    raise InvalidScientificProblem("typed field reduction requires separate measure-aware admission")
            elif typed:
                if source.semantics is None or target.semantics is None or edge.transport is None:
                    raise InvalidScientificProblem("typed connections require both port semantics and structured transport")
                edge.transport.admit(source.semantics, target.semantics)
            elif source.quantity != target.quantity:
                if (edge.conversion is None
                        or source.quantity != edge.conversion.input_form
                        or target.quantity != edge.conversion.output_form):
                    raise InvalidScientificProblem("legacy quantity meanings differ; explicit semantic migration is required")
            if edge.source.participant_id == edge.target.participant_id:
                raise InvalidScientificProblem(
                    f"edge {edge.edge_id!r} connects two ports of participant "
                    f"{edge.source.participant_id!r}; internal physics belongs inside "
                    f"the participant, not in the inter-participant graph"
                )
            if source.kind is PortKind.FIELD:
                if edge.mapping is None:
                    raise InvalidScientificProblem(
                        f"field edge {edge.edge_id!r} must declare a mapping, "
                        "including identity"
                    )
                if edge.conversion is not None:
                    raise InvalidScientificProblem(
                        f"field edge {edge.edge_id!r} cannot use scalar "
                        "EnergyConversion"
                    )
                if source.algebra is not target.algebra:
                    raise InvalidScientificProblem(
                        f"field edge {edge.edge_id!r} connects "
                        f"{source.algebra.value} algebra to "
                        f"{target.algebra.value}; component count alone is "
                        "not a transform semantic"
                    )
                if source.field.components != target.field.components:
                    raise InvalidScientificProblem(
                        f"field edge {edge.edge_id!r} changes component count "
                        f"{source.field.components}->{target.field.components}"
                    )
                if (
                    not typed_field and source.dimension
                    in ENERGY_DIMENSIONS + ENERGY_DERIVED_DIMENSIONS
                    and not edge.transport_declaration
                ):
                    raise InvalidScientificProblem(
                        f"field edge {edge.edge_id!r} carries an "
                        "energy/power-like dimension and must state that it "
                        "is transported whole; spatial energy conversion is "
                        "not implemented by this runtime"
                    )
            else:
                if edge.mapping is not None:
                    raise InvalidScientificProblem(
                        f"scalar edge {edge.edge_id!r} cannot declare a field mapping"
                    )
                if not typed:
                    self._validate_legacy_scalar(edge, source, target)
            frames_differ = (
                source.coordinate_frame != target.coordinate_frame
            )
            if frames_differ and not edge.coordinate_transform_id:
                raise InvalidScientificProblem(
                    f"edge {edge.edge_id!r} crosses coordinate frames "
                    f"{source.coordinate_frame!r}->{target.coordinate_frame!r} "
                    "without a transform"
                )
            if not frames_differ and edge.coordinate_transform_id:
                raise InvalidScientificProblem(
                    f"edge {edge.edge_id!r} declares coordinate transform "
                    f"{edge.coordinate_transform_id!r} although source and "
                    "target frames are identical"
                )
            if frames_differ and source.algebra not in (
                FieldAlgebra.VECTOR,
                FieldAlgebra.TENSOR_2,
            ):
                raise InvalidScientificProblem(
                    f"edge {edge.edge_id!r} changes frames for "
                    f"{source.algebra.value} algebra, which has no generic "
                    "rotation rule"
                )
            if source.kind is PortKind.FIELD:
                source_support = self.support(source.field.mesh_id)
                target_support = self.support(target.field.mesh_id)
                if (
                    source_support.spatial_dimension
                    != target_support.spatial_dimension
                ):
                    raise InvalidScientificProblem(
                        f"field edge {edge.edge_id!r} maps "
                        f"{source_support.spatial_dimension}D support to "
                        f"{target_support.spatial_dimension}D support"
                    )
            if frames_differ:
                transform = self.frame_transform(
                    edge.coordinate_transform_id
                )
                if (
                    transform.source_frame != source.coordinate_frame
                    or transform.target_frame != target.coordinate_frame
                ):
                    raise InvalidScientificProblem(
                        f"frame transform {transform.transform_id!r} does not "
                        f"match edge {edge.edge_id!r} frame declaration"
                    )
                if source.algebra is FieldAlgebra.VECTOR:
                    expected_dimension = source.field.components
                else:
                    expected_dimension = math.isqrt(
                        source.field.components
                    )
                if transform.dimension != expected_dimension:
                    raise InvalidScientificProblem(
                        f"frame transform {transform.transform_id!r} is "
                        f"{transform.dimension}D but edge {edge.edge_id!r} "
                        f"requires {expected_dimension}D"
                    )

    @staticmethod
    def _validate_legacy_scalar(edge, source, target) -> None:
        QuantityDependency(
            source_problem_id=edge.source.participant_id, source_quantity=source.quantity,
            target_problem_id=edge.target.participant_id, target_quantity=target.quantity,
            unit_exemplar=source.unit, name=edge.edge_id, description=edge.description,
            conversion=edge.conversion, transport_declaration=edge.transport_declaration,
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
            unit = self.participant(target.participant_id).port(target.port_id).unit
            if ReductionOperator.SUM in reductions and not is_ratio_scale(unit):
                # a sum of absolute values on a scale with a conventional zero
                # depends on which unit it is computed in (two 300 K values sum
                # to 600 K, or to 326.85 K in degC); MEAN/MIN/MAX do not
                raise InvalidScientificProblem(
                    f"fan-in SUM to {target.key} is declared in {unit!r}, a scale with a "
                    f"conventional zero; the sum would depend on the unit chosen"
                )

    def _validate_conservation(self) -> None:
        for balance in self.conservation:
            for binding in balance.terms:
                edge = self.edge(binding.edge_id)
                source = self.participant(edge.source.participant_id).port(edge.source.port_id)
                if source.kind is PortKind.FIELD:
                    raise InvalidScientificProblem(
                        f"conservation balance {balance.balance_id!r} binds field edge "
                        f"{edge.edge_id!r}; field conservation belongs to mapping diagnostics"
                    )
                if balance.tolerance.dimensionality != source.dimension:
                    raise InvalidScientificProblem(
                        f"conservation balance {balance.balance_id!r} tolerance "
                        f"[{balance.tolerance.dimensionality}] differs from edge "
                        f"{edge.edge_id!r} [{source.dimension}]"
                    )
                if balance.conserved_quantity is not None:
                    if (edge.transport is None or source.semantics is None
                            or source.semantics.conserved_quantity != balance.conserved_quantity
                            or edge.transport.conserved_quantity != balance.conserved_quantity):
                        raise InvalidScientificProblem("balance and realized edge conserved meanings disagree")
                elif edge.transport is not None:
                    raise InvalidScientificProblem("typed conserved transport requires a typed balance declaration")
                if binding.measure is TransferMeasure.LOSS:
                    if edge.transport is not None:
                        paths = edge.transport.losses
                    elif edge.conversion is not None:
                        paths = edge.conversion.losses
                    else:
                        raise InvalidScientificProblem(
                            f"conservation term {binding.name!r} asks for a loss on "
                            f"edge {edge.edge_id!r} with no conversion"
                        )
                    forms = {loss.form for loss in paths}
                    if binding.loss_form not in forms:
                        raise InvalidScientificProblem(
                            f"conservation term {binding.name!r} asks for loss form "
                            f"{binding.loss_form!r}; edge {edge.edge_id!r} declares {sorted(forms)}"
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
            "supports": [support.to_dict() for support in self.supports],
            "frame_transforms": [
                transform.to_dict() for transform in self.frame_transforms
            ],
            "conservation": [item.to_dict() for item in self.conservation],
            "description": self.description,
        }

    def fingerprint(self) -> str:
        payload = json.dumps(
            self.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "PhysicsGraph":
        require_schema(payload, PHYSICS_GRAPH_SCHEMA)
        return cls(
            graph_id=payload["graph_id"],
            participants=tuple(ParticipantSpec.from_dict(p) for p in payload["participants"]),
            edges=tuple(CouplingEdge.from_dict(e) for e in payload["edges"]),
            supports=tuple(
                read_mesh_support(item)
                for item in payload.get("supports", ())
            ),
            frame_transforms=tuple(
                FrameTransform.from_dict(item)
                for item in payload.get("frame_transforms", ())
            ),
            conservation=tuple(CoupledConservation.from_dict(item) for item in payload.get("conservation", ())),
            description=payload.get("description", ""),
        )
