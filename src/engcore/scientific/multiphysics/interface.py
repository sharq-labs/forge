"""Auditable interface/admission view of a PhysicsGraph.

A PhysicsGraph already validates scientific wiring. This module exposes the
remaining execution boundary explicitly: which inputs must be supplied from
outside the graph, which outputs leave the graph unused, and how participants
are connected. Nothing here invents coupling or solver policy.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping

from ...scientific.errors import InvalidScientificProblem
from ...scientific.serialization import require_schema, schema_string
from .graph import PhysicsGraph
from .ports import PortRef

GRAPH_INTERFACE_SCHEMA = schema_string("multiphysics_graph_interface")


@dataclass(frozen=True)
class GraphInterfaceManifest:
    graph_id: str
    graph_fingerprint: str
    required_external_inputs: tuple[PortRef, ...]
    unconsumed_outputs: tuple[PortRef, ...]
    weakly_connected_components: tuple[tuple[str, ...], ...]
    strongly_connected_components: tuple[tuple[str, ...], ...]
    cyclic: bool
    transient_participants: tuple[str, ...]
    checkpointable_participants: tuple[str, ...]
    field_edges: tuple[str, ...]
    scalar_edges: tuple[str, ...]

    def __post_init__(self) -> None:
        if not str(self.graph_id).strip():
            raise InvalidScientificProblem("graph interface requires graph_id")
        digest = str(self.graph_fingerprint).strip().lower()
        if (
            len(digest) != 64
            or any(char not in "0123456789abcdef" for char in digest)
        ):
            raise InvalidScientificProblem(
                "graph interface graph_fingerprint must be sha256 hex"
            )
        object.__setattr__(self, "graph_fingerprint", digest)
        object.__setattr__(
            self,
            "required_external_inputs",
            tuple(sorted(self.required_external_inputs, key=lambda ref: ref.key)),
        )
        object.__setattr__(
            self,
            "unconsumed_outputs",
            tuple(sorted(self.unconsumed_outputs, key=lambda ref: ref.key)),
        )
        object.__setattr__(
            self,
            "weakly_connected_components",
            tuple(
                sorted(
                    (tuple(sorted(group)) for group in self.weakly_connected_components),
                    key=lambda group: group[0],
                )
            ),
        )
        object.__setattr__(
            self,
            "strongly_connected_components",
            tuple(
                sorted(
                    (tuple(sorted(group)) for group in self.strongly_connected_components),
                    key=lambda group: group[0],
                )
            ),
        )
        for label in (
            "transient_participants",
            "checkpointable_participants",
            "field_edges",
            "scalar_edges",
        ):
            object.__setattr__(
                self,
                label,
                tuple(sorted(set(str(item) for item in getattr(self, label)))),
            )

    @property
    def disconnected(self) -> bool:
        return len(self.weakly_connected_components) > 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": GRAPH_INTERFACE_SCHEMA,
            "graph_id": self.graph_id,
            "graph_fingerprint": self.graph_fingerprint,
            "required_external_inputs": [
                ref.to_dict() for ref in self.required_external_inputs
            ],
            "unconsumed_outputs": [
                ref.to_dict() for ref in self.unconsumed_outputs
            ],
            "weakly_connected_components": [
                list(group) for group in self.weakly_connected_components
            ],
            "strongly_connected_components": [
                list(group) for group in self.strongly_connected_components
            ],
            "cyclic": self.cyclic,
            "disconnected": self.disconnected,
            "transient_participants": list(self.transient_participants),
            "checkpointable_participants": list(self.checkpointable_participants),
            "field_edges": list(self.field_edges),
            "scalar_edges": list(self.scalar_edges),
        }

    @property
    def fingerprint(self) -> str:
        payload = json.dumps(
            self.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "GraphInterfaceManifest":
        require_schema(payload, GRAPH_INTERFACE_SCHEMA)
        return cls(
            graph_id=payload["graph_id"],
            graph_fingerprint=payload["graph_fingerprint"],
            required_external_inputs=tuple(
                PortRef.from_dict(item)
                for item in payload.get("required_external_inputs", ())
            ),
            unconsumed_outputs=tuple(
                PortRef.from_dict(item)
                for item in payload.get("unconsumed_outputs", ())
            ),
            weakly_connected_components=tuple(
                tuple(group)
                for group in payload.get("weakly_connected_components", ())
            ),
            strongly_connected_components=tuple(
                tuple(group)
                for group in payload.get("strongly_connected_components", ())
            ),
            cyclic=bool(payload.get("cyclic", False)),
            transient_participants=tuple(
                payload.get("transient_participants", ())
            ),
            checkpointable_participants=tuple(
                payload.get("checkpointable_participants", ())
            ),
            field_edges=tuple(payload.get("field_edges", ())),
            scalar_edges=tuple(payload.get("scalar_edges", ())),
        )


def graph_interface_manifest(graph: PhysicsGraph) -> GraphInterfaceManifest:
    if not isinstance(graph, PhysicsGraph):
        raise TypeError("graph_interface_manifest requires PhysicsGraph")

    connected_inputs = {edge.target for edge in graph.edges}
    consumed_outputs = {edge.source for edge in graph.edges}

    external = tuple(
        PortRef(participant.participant_id, port.port_id)
        for participant in graph.participants
        for port in participant.inputs
        if PortRef(participant.participant_id, port.port_id)
        not in connected_inputs
    )
    unconsumed = tuple(
        PortRef(participant.participant_id, port.port_id)
        for participant in graph.participants
        for port in participant.outputs
        if PortRef(participant.participant_id, port.port_id)
        not in consumed_outputs
    )

    adjacency = {
        participant.participant_id: set()
        for participant in graph.participants
    }
    for edge in graph.edges:
        source = edge.source.participant_id
        target = edge.target.participant_id
        adjacency[source].add(target)
        adjacency[target].add(source)

    remaining = set(adjacency)
    components: list[tuple[str, ...]] = []
    while remaining:
        seed = min(remaining)
        stack = [seed]
        seen: set[str] = set()
        while stack:
            node = stack.pop()
            if node in seen:
                continue
            seen.add(node)
            stack.extend(sorted(adjacency[node] - seen, reverse=True))
        remaining -= seen
        components.append(tuple(sorted(seen)))

    field_edges: list[str] = []
    scalar_edges: list[str] = []
    for edge in graph.edges:
        source = graph.participant(edge.source.participant_id).port(
            edge.source.port_id
        )
        if source.kind.value == "field":
            field_edges.append(edge.edge_id)
        else:
            scalar_edges.append(edge.edge_id)

    return GraphInterfaceManifest(
        graph_id=graph.graph_id,
        graph_fingerprint=graph.fingerprint(),
        required_external_inputs=external,
        unconsumed_outputs=unconsumed,
        weakly_connected_components=tuple(components),
        strongly_connected_components=graph.strongly_connected_components(),
        cyclic=graph.cyclic,
        transient_participants=tuple(
            participant.participant_id
            for participant in graph.participants
            if participant.transient
        ),
        checkpointable_participants=tuple(
            participant.participant_id
            for participant in graph.participants
            if participant.checkpointable
        ),
        field_edges=tuple(field_edges),
        scalar_edges=tuple(scalar_edges),
    )


__all__ = [
    "GRAPH_INTERFACE_SCHEMA",
    "GraphInterfaceManifest",
    "graph_interface_manifest",
]
