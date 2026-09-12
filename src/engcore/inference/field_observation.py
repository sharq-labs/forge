"""How a scalar observation is derived from a field, stated rather than coded.

The thing this refuses
----------------------
``field[31, 17]``.

An array index is not a scientific identity. It means "the 17th node along y of
the 31st along x", which is a statement about a *discretisation*, and the same
pair of integers on a refined mesh is a different physical place. A study that
records its thermocouple as ``field[31, 17]`` has recorded something that stops
being true the moment anybody remeshes, and nothing in the record can detect
that it has stopped being true.

So an observation operator is declared in the units of the world -- a probe at
x = 12 mm, y = 4 mm; the mean over a declared region -- and the index is
*derived* from whichever mesh it is applied to. The operator additionally binds
to one support by fingerprint, so applying it to a different mesh is a refusal
rather than a silent answer about a different point.

This is the same discipline :class:`MeshRegion` already uses, and the reason it
lives here rather than there is that this is the INFERENCE side of the
boundary: it produces the scalar an observation is compared against.

Scope
-----
A spike, deliberately. It proves the inference stack can consume a declared
scalar derived from a field; it does not calibrate a field model, and nothing
here solves a PDE.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Sequence

import numpy as np

from ..scientific.fields.mesh import StructuredMesh
from ..scientific.fields.regions import MeshRegion
from ..scientific.serialization import require_schema, schema_string
from ..scientific.units.quantity import Quantity, normalize_unit
from .grid import InferenceProblemError

FIELD_OBSERVATION_SCHEMA = schema_string("field_observation_operator")
CANONICAL_LENGTH = "meter"


class FieldObservationError(InferenceProblemError):
    """An observation operator that does not name one observable quantity."""


class FieldObservationKind(str, Enum):
    """What scalar is taken, each defined without reference to an index."""

    #: The value at the node nearest a declared physical location. "Nearest"
    #: is resolved against the mesh at application time and the distance is
    #: reported, so a probe that lands far from any node is visible rather than
    #: silently snapped.
    PROBE_AT_LOCATION = "probe_at_location"
    #: The arithmetic mean over the nodes of a declared region.
    REGION_MEAN = "region_mean"
    #: The largest value anywhere on the support. Defined without a location,
    #: which is exactly why it needs saying that it IS the whole support.
    FIELD_MAXIMUM = "field_maximum"


@dataclass(frozen=True)
class FieldObservationOperator:
    """A declared map from a solved field to one scalar observation.

    ``mesh_fingerprint`` binds the operator to one support. It is not
    decoration: without it, "the probe at (12 mm, 4 mm)" applied to a coarser
    mesh returns a different node's value under the same name, and a
    calibration would compare two different measurements as though they were
    one.
    """

    operator_id: str
    kind: FieldObservationKind
    field_id: str
    mesh_fingerprint: str
    unit: str
    probe_x: Quantity | None = None
    probe_y: Quantity | None = None
    region_id: str | None = None
    description: str = ""

    def __post_init__(self) -> None:
        for label in ("operator_id", "field_id"):
            text = str(getattr(self, label)).strip()
            if not text:
                raise FieldObservationError(f"an operator requires a non-empty {label}")
            object.__setattr__(self, label, text)
        object.__setattr__(self, "kind", FieldObservationKind(self.kind))
        object.__setattr__(self, "unit", normalize_unit(self.unit))

        fingerprint = str(self.mesh_fingerprint).strip().lower()
        if len(fingerprint) != 64 or any(c not in "0123456789abcdef" for c in fingerprint):
            raise FieldObservationError(
                f"an operator names its support by fingerprint; got "
                f"{self.mesh_fingerprint!r}. A mesh_id is a label and two "
                f"different discretisations routinely share one"
            )
        object.__setattr__(self, "mesh_fingerprint", fingerprint)

        if self.kind is FieldObservationKind.PROBE_AT_LOCATION:
            if self.probe_x is None or self.probe_y is None:
                raise FieldObservationError(
                    f"operator {self.operator_id!r} is a probe and must declare "
                    f"probe_x and probe_y as physical LOCATIONS. An index would "
                    f"name a node of one discretisation, not a place"
                )
            for label in ("probe_x", "probe_y"):
                value = getattr(self, label)
                if not isinstance(value, Quantity):
                    raise FieldObservationError(f"{label} must be a Quantity")
                value.require_compatible(
                    Quantity(0.0, CANONICAL_LENGTH), context=f"probe {label}"
                )
            if self.region_id is not None:
                raise FieldObservationError("a probe operator declares no region")
        elif self.kind is FieldObservationKind.REGION_MEAN:
            if not str(self.region_id or "").strip():
                raise FieldObservationError(
                    f"operator {self.operator_id!r} is a region mean and must "
                    f"declare which region"
                )
            object.__setattr__(self, "region_id", str(self.region_id).strip())
            if self.probe_x is not None or self.probe_y is not None:
                raise FieldObservationError("a region operator declares no probe")
        else:  # FIELD_MAXIMUM
            if self.probe_x is not None or self.probe_y is not None or self.region_id:
                raise FieldObservationError(
                    "a field-maximum operator declares neither probe nor region: "
                    "it is over the whole support by definition"
                )

    def require_support(self, mesh: StructuredMesh) -> None:
        """Refuse a support this operator was not declared against."""
        if not isinstance(mesh, StructuredMesh):
            raise FieldObservationError(
                f"operator {self.operator_id!r} resolves against a "
                f"StructuredMesh, got {type(mesh).__name__}"
            )
        if mesh.fingerprint() != self.mesh_fingerprint:
            raise FieldObservationError(
                f"operator {self.operator_id!r} was declared against support "
                f"{self.mesh_fingerprint[:12]}… and was given "
                f"{mesh.fingerprint()[:12]}…. Same operator, different "
                f"discretisation: the node it would read is a different "
                f"physical place, so this is a different observation and not "
                f"this one"
            )

    def resolve_indices(self, mesh: StructuredMesh) -> tuple[int, ...]:
        """The node indices this operator reads ON THIS MESH. Derived, never stored.

        Recomputed from the declaration every time, which is what makes the
        declaration the identity and the indices an implementation detail.
        """
        self.require_support(mesh)
        if self.kind is FieldObservationKind.FIELD_MAXIMUM:
            return tuple(range(mesh.node_count))
        if self.kind is FieldObservationKind.REGION_MEAN:
            raise FieldObservationError(
                "a region mean resolves its indices through the MeshRegion it "
                "names; call apply() with that region"
            )
        xs, ys = mesh.axis_coordinates()
        target_x = self.probe_x.magnitude_in(CANONICAL_LENGTH)
        target_y = self.probe_y.magnitude_in(CANONICAL_LENGTH)
        i = int(np.argmin([abs(x - target_x) for x in xs]))
        j = int(np.argmin([abs(y - target_y) for y in ys]))
        return (mesh.node_index(i, j),)

    def probe_offset(self, mesh: StructuredMesh) -> Quantity:
        """How far the nearest node is from the declared location.

        Reported rather than hidden: a probe that snaps 4 mm to the nearest
        node on a coarse mesh is measuring somewhere else, and the caller is
        entitled to see that before trusting the number.
        """
        if self.kind is not FieldObservationKind.PROBE_AT_LOCATION:
            raise FieldObservationError("only a probe has an offset")
        self.require_support(mesh)
        xs, ys = mesh.axis_coordinates()
        target_x = self.probe_x.magnitude_in(CANONICAL_LENGTH)
        target_y = self.probe_y.magnitude_in(CANONICAL_LENGTH)
        dx = min(abs(x - target_x) for x in xs)
        dy = min(abs(y - target_y) for y in ys)
        return Quantity(math.hypot(dx, dy), CANONICAL_LENGTH)

    def apply(
        self,
        mesh: StructuredMesh,
        values: Sequence[float] | np.ndarray,
        *,
        region: MeshRegion | None = None,
    ) -> Quantity:
        """The scalar this operator declares, read off one solved field."""
        self.require_support(mesh)
        array = np.asarray(values, dtype=np.float64).reshape(-1)
        if array.size != mesh.node_count:
            raise FieldObservationError(
                f"operator {self.operator_id!r} was given {array.size} value(s) "
                f"for a support with {mesh.node_count} nodes"
            )
        if not np.all(np.isfinite(array)):
            raise FieldObservationError(
                f"operator {self.operator_id!r} was given a field containing "
                f"non-finite values; a scalar read off it would be an "
                f"interpreted quantity built on one"
            )

        if self.kind is FieldObservationKind.FIELD_MAXIMUM:
            return Quantity(float(np.max(array)), self.unit)
        if self.kind is FieldObservationKind.REGION_MEAN:
            if region is None:
                raise FieldObservationError(
                    f"operator {self.operator_id!r} names region "
                    f"{self.region_id!r} and must be given it"
                )
            if region.region_id != self.region_id:
                raise FieldObservationError(
                    f"operator {self.operator_id!r} names region "
                    f"{self.region_id!r} and was given {region.region_id!r}"
                )
            indices = region.node_indices(mesh)
            return Quantity(float(np.mean(array[list(indices)])), self.unit)
        index = self.resolve_indices(mesh)[0]
        return Quantity(float(array[index]), self.unit)

    def _canonical(self) -> dict[str, Any]:
        return {
            "operator_id": self.operator_id,
            "kind": self.kind.value,
            "field_id": self.field_id,
            "mesh_fingerprint": self.mesh_fingerprint,
            "unit": self.unit,
            "probe_x": (
                self.probe_x.magnitude_in(CANONICAL_LENGTH)
                if self.probe_x is not None
                else None
            ),
            "probe_y": (
                self.probe_y.magnitude_in(CANONICAL_LENGTH)
                if self.probe_y is not None
                else None
            ),
            "region_id": self.region_id,
        }

    @property
    def digest(self) -> str:
        blob = json.dumps(self._canonical(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "schema": FIELD_OBSERVATION_SCHEMA,
            **self._canonical(),
            "description": self.description,
            "digest": self.digest,
        }
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "FieldObservationOperator":
        require_schema(payload, FIELD_OBSERVATION_SCHEMA)
        try:
            operator = cls(
                operator_id=payload["operator_id"],
                kind=FieldObservationKind(payload["kind"]),
                field_id=payload["field_id"],
                mesh_fingerprint=payload["mesh_fingerprint"],
                unit=payload["unit"],
                probe_x=(
                    Quantity(payload["probe_x"], CANONICAL_LENGTH)
                    if payload.get("probe_x") is not None
                    else None
                ),
                probe_y=(
                    Quantity(payload["probe_y"], CANONICAL_LENGTH)
                    if payload.get("probe_y") is not None
                    else None
                ),
                region_id=payload.get("region_id"),
                description=payload.get("description", ""),
            )
        except KeyError as exc:
            raise FieldObservationError(
                f"serialized observation operator is missing {exc.args[0]!r}"
            ) from None
        declared = payload.get("digest")
        if declared != operator.digest:
            raise FieldObservationError(
                f"serialized operator {operator.operator_id!r} carries digest "
                f"{str(declared)[:12]}… but its fields hash to "
                f"{operator.digest[:12]}…"
            )
        return operator
