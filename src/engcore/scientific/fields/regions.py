"""Where on a support a condition applies, resolved rather than labelled.

``BoundaryCondition.region`` in the scalar IR is a string the core does not
interpret, and its docstring says so. That is right for a problem with no
support: the domain owns the tag because nothing else could. It is exactly
wrong for a field problem, where "left" has to name a definite set of nodes
before a solver can impose anything on it, and where two records naming "left"
on two different supports mean two different things.

A region here is therefore a *resolvable* record: it names an edge of a
structured support and it names the support, and asking it for its nodes
against the wrong support is refused rather than answered.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from ..errors import InvalidScientificProblem
from ..serialization import require_schema, schema_string
from .mesh import StructuredMesh

REGION_SCHEMA = schema_string("mesh_region")


class BoundaryEdge(str, Enum):
    """The four edges of a rectangular support.

    A closed vocabulary, deliberately. An open one would be the opaque label
    again with an enum's spelling, and the whole point of this record is that a
    region resolves to nodes rather than to a reader's assumption.
    """

    LEFT = "left"
    RIGHT = "right"
    BOTTOM = "bottom"
    TOP = "top"


@dataclass(frozen=True)
class MeshRegion:
    """One edge of one support, able to say which nodes it is.

    ``mesh_id`` binds the region to the support it was declared against.
    :meth:`node_indices` refuses any other support, because a region that
    answered for whatever mesh it was handed would be the silent alignment this
    layer exists to prevent.
    """

    region_id: str
    mesh_id: str
    edge: BoundaryEdge
    description: str = ""

    def __post_init__(self) -> None:
        for label in ("region_id", "mesh_id"):
            text = str(getattr(self, label)).strip()
            if not text:
                raise InvalidScientificProblem(f"a region requires a non-empty {label}")
            object.__setattr__(self, label, text)
        object.__setattr__(self, "edge", BoundaryEdge(self.edge))

    def require_support(self, mesh: StructuredMesh) -> None:
        """Refuse a support this region was not declared against."""
        if not isinstance(mesh, StructuredMesh):
            raise InvalidScientificProblem(
                f"region {self.region_id!r} resolves against a StructuredMesh, "
                f"got {type(mesh).__name__}"
            )
        if mesh.mesh_id != self.mesh_id:
            raise InvalidScientificProblem(
                f"region {self.region_id!r} is declared on mesh "
                f"{self.mesh_id!r} and was resolved against {mesh.mesh_id!r}; "
                f"an edge of one support names no nodes of another"
            )

    def node_indices(self, mesh: StructuredMesh) -> tuple[int, ...]:
        """Row-major indices of every node on this edge, ascending.

        Corners belong to both edges that meet at them, which is a statement
        rather than an accident: a corner node is on the left edge and on the
        bottom edge, and a solver imposing two conditions there has a conflict
        worth refusing (see :mod:`.conditions`) instead of a silent winner.
        """
        self.require_support(mesh)
        nx, ny = mesh.nodes_x, mesh.nodes_y
        if self.edge is BoundaryEdge.LEFT:
            return tuple(mesh.node_index(0, j) for j in range(ny))
        if self.edge is BoundaryEdge.RIGHT:
            return tuple(mesh.node_index(nx - 1, j) for j in range(ny))
        if self.edge is BoundaryEdge.BOTTOM:
            return tuple(mesh.node_index(i, 0) for i in range(nx))
        return tuple(mesh.node_index(i, ny - 1) for i in range(nx))

    def node_count(self, mesh: StructuredMesh) -> int:
        self.require_support(mesh)
        if self.edge in (BoundaryEdge.LEFT, BoundaryEdge.RIGHT):
            return mesh.nodes_y
        return mesh.nodes_x

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": REGION_SCHEMA,
            "region_id": self.region_id,
            "mesh_id": self.mesh_id,
            "edge": self.edge.value,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "MeshRegion":
        require_schema(payload, REGION_SCHEMA)
        return cls(
            region_id=payload["region_id"],
            mesh_id=payload["mesh_id"],
            edge=BoundaryEdge(payload["edge"]),
            description=payload.get("description", ""),
        )


def boundary_regions(mesh: StructuredMesh) -> tuple[MeshRegion, ...]:
    """The four edges of ``mesh``, named after the edge they are.

    A convenience with one rule in it: the ids are derived from the support, so
    a caller cannot end up with two regions that claim one edge under two names.
    """
    return tuple(
        MeshRegion(
            region_id=f"{mesh.mesh_id}:{edge.value}",
            mesh_id=mesh.mesh_id,
            edge=edge,
            description=f"the {edge.value} edge of {mesh.mesh_id}",
        )
        for edge in BoundaryEdge
    )
