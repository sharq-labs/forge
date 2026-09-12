"""The discrete support a field lives on, as a record rather than a shape guess.

A scalar problem states quantities. A field problem states quantities *somewhere*,
and the somewhere has to be a record the core can check: a count of values is not
a grid, and two arrays of equal length are not the same support.

What this module is, and is not
-------------------------------
It is the smallest mesh a structured two-dimensional solve needs, written so the
things that must be checkable are fields rather than conventions:

* the topology, so nobody infers one from an array's length;
* the extents, unit-bearing, so a grid over 1 m and a grid over 1 mm are two
  different supports;
* the node counts, so a shape is declared rather than recovered;
* a fingerprint over all of it, so a field, a region and a result can each say
  *which* support they mean and be refused when they disagree.

It is not a mesh library. There is no unstructured connectivity, no refinement,
no curvilinear mapping, no ghost layer and no partitioning. Those are real and
they are absent on purpose: this record exists to carry one vertical slice and
to be replaced honestly rather than extended quietly.

Uniform spacing is a property of this record, not a limitation hidden in it.
``STRUCTURED_RECTILINEAR`` means equal spacing per axis, and the spacing is
derived from the extents and the counts rather than stored beside them, so a
record cannot state a spacing that disagrees with its own geometry.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from ..errors import InvalidScientificProblem
from ..serialization import require_schema, schema_string
from ..units.quantity import Quantity
from ..units.validation import require_same_dimension

MESH_SCHEMA = schema_string("structured_mesh")

#: The unit every coordinate is canonicalised into before it is hashed, so two
#: records of one geometry written in different length units share a
#: fingerprint. The declaration keeps whatever unit its author wrote.
CANONICAL_LENGTH = "meter"

#: The fewest nodes an axis can carry and still be a discretisation: two nodes
#: are one cell. One node is a point, and a point has no spacing.
MINIMUM_NODES = 2


class MeshTopology(str, Enum):
    """How the nodes are connected. One member, and it is a statement.

    A record that names its topology cannot be mistaken for one that assumed a
    topology, and the day an unstructured support arrives it is a new member
    here rather than a different meaning for this one.
    """

    STRUCTURED_RECTILINEAR = "structured_rectilinear"


def _require_positive_length(value: Any, *, label: str) -> Quantity:
    if not isinstance(value, Quantity):
        raise InvalidScientificProblem(
            f"mesh {label} must be a Quantity, got {type(value).__name__}; an "
            f"extent without a unit is a number, and a number is not a geometry"
        )
    require_same_dimension(value, CANONICAL_LENGTH, context=f"mesh {label}")
    magnitude = value.magnitude_in(CANONICAL_LENGTH)
    if not math.isfinite(magnitude) or magnitude <= 0.0:
        raise InvalidScientificProblem(
            f"mesh {label} must be finite and strictly positive, got {value}"
        )
    return value


def _require_node_count(value: Any, *, label: str) -> int:
    # `bool` is an `int` in Python, and `True` nodes is not a count. The same
    # refusal `IntegerValue` and `ScientificDataReference.count` already make.
    if isinstance(value, bool) or not isinstance(value, int):
        raise InvalidScientificProblem(
            f"mesh {label} must be an int, got {type(value).__name__} "
            f"({value!r}); a node count is exact and discrete"
        )
    if value < MINIMUM_NODES:
        raise InvalidScientificProblem(
            f"mesh {label} must be at least {MINIMUM_NODES}, got {value}; two "
            f"nodes are one cell, and one node has no spacing"
        )
    return value


@dataclass(frozen=True)
class StructuredMesh:
    """A rectangular grid of nodes over a rectangular extent.

    Identity is :meth:`fingerprint`, which covers the topology, the extents and
    the counts. Two meshes with the same fingerprint are the same support; two
    with different fingerprints are not, whatever their arrays happen to
    measure.
    """

    mesh_id: str
    length_x: Quantity
    length_y: Quantity
    nodes_x: int
    nodes_y: int
    origin_x: Quantity = Quantity(0.0, CANONICAL_LENGTH)
    origin_y: Quantity = Quantity(0.0, CANONICAL_LENGTH)
    topology: MeshTopology = MeshTopology.STRUCTURED_RECTILINEAR
    description: str = ""

    def __post_init__(self) -> None:
        mesh_id = str(self.mesh_id).strip()
        if not mesh_id:
            raise InvalidScientificProblem("a mesh requires a non-empty mesh_id")
        object.__setattr__(self, "mesh_id", mesh_id)
        object.__setattr__(self, "topology", MeshTopology(self.topology))

        object.__setattr__(
            self, "length_x", _require_positive_length(self.length_x, label="length_x")
        )
        object.__setattr__(
            self, "length_y", _require_positive_length(self.length_y, label="length_y")
        )
        for label in ("origin_x", "origin_y"):
            origin = getattr(self, label)
            if not isinstance(origin, Quantity):
                raise InvalidScientificProblem(
                    f"mesh {label} must be a Quantity, got {type(origin).__name__}"
                )
            require_same_dimension(origin, CANONICAL_LENGTH, context=f"mesh {label}")
            if not math.isfinite(origin.magnitude_in(CANONICAL_LENGTH)):
                raise InvalidScientificProblem(f"mesh {label} must be finite")
        object.__setattr__(
            self, "nodes_x", _require_node_count(self.nodes_x, label="nodes_x")
        )
        object.__setattr__(
            self, "nodes_y", _require_node_count(self.nodes_y, label="nodes_y")
        )

    # ---- what the support is ------------------------------------------------
    @property
    def dimensionality(self) -> int:
        return 2

    @property
    def node_count(self) -> int:
        return self.nodes_x * self.nodes_y

    @property
    def cell_count(self) -> int:
        return (self.nodes_x - 1) * (self.nodes_y - 1)

    @property
    def node_shape(self) -> tuple[int, int]:
        """``(rows, columns)`` — y varies down, x across, as the arrays are laid out."""
        return (self.nodes_y, self.nodes_x)

    @property
    def cell_shape(self) -> tuple[int, int]:
        return (self.nodes_y - 1, self.nodes_x - 1)

    @property
    def spacing_x(self) -> Quantity:
        """Derived, never stored: a record cannot contradict its own geometry."""
        return Quantity(
            self.length_x.magnitude_in(CANONICAL_LENGTH) / (self.nodes_x - 1),
            CANONICAL_LENGTH,
        )

    @property
    def spacing_y(self) -> Quantity:
        return Quantity(
            self.length_y.magnitude_in(CANONICAL_LENGTH) / (self.nodes_y - 1),
            CANONICAL_LENGTH,
        )

    def axis_coordinates(self) -> tuple[tuple[float, ...], tuple[float, ...]]:
        """Node coordinates along each axis, in :data:`CANONICAL_LENGTH`.

        Two sequences rather than a grid of pairs: a rectilinear support is the
        product of its axes, and materialising the product would hand back an
        O(nodes) structure the control plane has no business holding.
        """
        x0 = self.origin_x.magnitude_in(CANONICAL_LENGTH)
        y0 = self.origin_y.magnitude_in(CANONICAL_LENGTH)
        dx = self.spacing_x.magnitude_in(CANONICAL_LENGTH)
        dy = self.spacing_y.magnitude_in(CANONICAL_LENGTH)
        return (
            tuple(x0 + dx * i for i in range(self.nodes_x)),
            tuple(y0 + dy * j for j in range(self.nodes_y)),
        )

    def node_index(self, i: int, j: int) -> int:
        """Row-major index of node ``(i, j)``; refuses one that is not on the mesh."""
        if not (0 <= i < self.nodes_x) or not (0 <= j < self.nodes_y):
            raise InvalidScientificProblem(
                f"node ({i}, {j}) is not on mesh {self.mesh_id!r}, which is "
                f"{self.nodes_x} x {self.nodes_y} nodes"
            )
        return j * self.nodes_x + i

    # ---- identity -----------------------------------------------------------
    def _canonical(self) -> dict[str, Any]:
        return {
            "topology": self.topology.value,
            "origin_x": repr(self.origin_x.magnitude_in(CANONICAL_LENGTH)),
            "origin_y": repr(self.origin_y.magnitude_in(CANONICAL_LENGTH)),
            "length_x": repr(self.length_x.magnitude_in(CANONICAL_LENGTH)),
            "length_y": repr(self.length_y.magnitude_in(CANONICAL_LENGTH)),
            "nodes_x": self.nodes_x,
            "nodes_y": self.nodes_y,
            "unit": CANONICAL_LENGTH,
        }

    def fingerprint(self) -> str:
        """SHA-256 over the geometry and the discretisation, recomputed on read.

        The id is **not** in the preimage: a fingerprint answers "is this the
        same support", and renaming a mesh does not move a node. Two records
        that disagree about a name and agree about everything else are the same
        support, and a consumer that cares about the name can compare names.
        """
        blob = json.dumps(self._canonical(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def same_support_as(self, other: "StructuredMesh") -> bool:
        return isinstance(other, StructuredMesh) and self.fingerprint() == other.fingerprint()

    def __str__(self) -> str:  # pragma: no cover - display only
        return (
            f"{self.mesh_id}[{self.nodes_x}x{self.nodes_y} nodes over "
            f"{self.length_x} x {self.length_y}]@{self.fingerprint()[:12]}"
        )

    # ---- serialization ------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": MESH_SCHEMA,
            "mesh_id": self.mesh_id,
            "topology": self.topology.value,
            "length_x": self.length_x.to_dict(),
            "length_y": self.length_y.to_dict(),
            "origin_x": self.origin_x.to_dict(),
            "origin_y": self.origin_y.to_dict(),
            "nodes_x": self.nodes_x,
            "nodes_y": self.nodes_y,
            "description": self.description,
            # Derived, emitted for a reader, and recomputed on the way back in.
            "fingerprint": self.fingerprint(),
            "node_count": self.node_count,
            "cell_count": self.cell_count,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "StructuredMesh":
        require_schema(payload, MESH_SCHEMA)
        mesh = cls(
            mesh_id=payload["mesh_id"],
            length_x=Quantity.from_dict(payload["length_x"]),
            length_y=Quantity.from_dict(payload["length_y"]),
            nodes_x=payload["nodes_x"],
            nodes_y=payload["nodes_y"],
            origin_x=Quantity.from_dict(payload["origin_x"]),
            origin_y=Quantity.from_dict(payload["origin_y"]),
            topology=MeshTopology(payload.get("topology", MeshTopology.STRUCTURED_RECTILINEAR)),
            description=payload.get("description", ""),
        )
        declared = payload.get("fingerprint")
        if declared is not None and declared != mesh.fingerprint():
            raise InvalidScientificProblem(
                f"serialized mesh {mesh.mesh_id!r} carries fingerprint "
                f"{str(declared)[:12]}… but its geometry hashes to "
                f"{mesh.fingerprint()[:12]}…; a support whose identity was "
                f"edited is not the support it names"
            )
        return mesh
