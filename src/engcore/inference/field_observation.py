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
from ..scientific.fields.regions import BoundaryEdge, MeshRegion
from ..scientific.serialization import require_schema_any, schema_string
from ..scientific.units.quantity import Quantity, dimensionality, normalize_unit
from .grid import InferenceProblemError

FIELD_OBSERVATION_SCHEMA = schema_string("field_observation_operator")
#: Bumped to /2 by the region's declared content, written only when a record
#: carries it: an operator that declares none keeps its /1 bytes and its digest.
FIELD_OBSERVATION_SCHEMA_V2 = schema_string("field_observation_operator", 2)

#: How far outside the support's own extent a declared probe may sit and still
#: count as on it.
#:
#: R-73 (I-25 part B): a representation allowance so a probe declared exactly at
#: an edge is inside it whatever the float arithmetic of the axis coordinates
#: gives. Not a modelling tolerance: a probe outside the rectangle by more than
#: a part in a billion of its extent is outside it, and the audited case was
#: metres away from a 10 mm plate.
PROBE_CONTAINMENT_RTOL = 1e-9
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
    #: The support the named region is declared on, and which edge it is.
    #:
    #: R-73 (I-25 part B): ``apply`` compared the region's LABEL, so the same
    #: operator, the same digest and the same region id returned the mean of the
    #: left edge (400 K) or the right edge (300 K) depending on which
    #: ``MeshRegion`` object was handed over -- and the region decides which
    #: nodes are averaged. These two are the region's content, they are in the
    #: canonical form and therefore in the digest, and ``apply`` refuses a
    #: region that does not match them. Empty means the operator does not say,
    #: which is the honest state of every record written before these fields
    #: existed and is refused a region it cannot check.
    region_mesh_id: str = ""
    region_edge: str = ""

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
            if self.region_mesh_id or self.region_edge:
                raise FieldObservationError(
                    "a probe operator declares no region, and so no region content"
                )
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
            object.__setattr__(self, "region_mesh_id", str(self.region_mesh_id).strip())
            object.__setattr__(self, "region_edge", str(self.region_edge).strip())
            if self.region_edge and self.region_edge not in {edge.value for edge in BoundaryEdge}:
                raise FieldObservationError(
                    f"operator {self.operator_id!r} declares region edge "
                    f"{self.region_edge!r}, which is no BoundaryEdge"
                )
        else:  # FIELD_MAXIMUM
            if self.region_mesh_id or self.region_edge:
                raise FieldObservationError(
                    "only a region-mean operator declares a region's content"
                )
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
        self._require_the_probe_is_on_the_support(xs, ys, target_x, target_y)
        i = int(np.argmin([abs(x - target_x) for x in xs]))
        j = int(np.argmin([abs(y - target_y) for y in ys]))
        return (mesh.node_index(i, j),)

    def _require_the_probe_is_on_the_support(
        self, xs: Sequence[float], ys: Sequence[float], target_x: float, target_y: float
    ) -> None:
        """R-73: a probe metres from a 10 mm plate is not a measurement of that plate.

        ``argmin`` answers any location with SOME node, so a probe declared 2 m and -5 m away returned a
        corner node's value under the declared name, and the observation entered a calibration as a value
        at a different physical place. ``probe_offset`` could always report 5.38 m, and ``apply`` never
        asked.

        Only containment in the support's rectangle is checked. A probe inside it that snaps half a cell
        is still answered -- refusing there would delete every legitimate coarse-mesh probe -- and
        ``probe_offset`` remains the place that says how far it moved.
        """
        for axis, target, coordinates in (("x", target_x, xs), ("y", target_y, ys)):
            low, high = min(coordinates), max(coordinates)
            allowance = PROBE_CONTAINMENT_RTOL * max(abs(high - low), abs(low), abs(high), 1.0)
            if target < low - allowance or target > high + allowance:
                raise FieldObservationError(
                    f"operator {self.operator_id!r} declares {axis} = {target} "
                    f"{CANONICAL_LENGTH}, which is outside the support's extent "
                    f"[{low}, {high}] {CANONICAL_LENGTH}. The nearest node is on the edge of a support "
                    f"the probe is not on, and reading it would report a value at a different physical "
                    f"place under this operator's name"
                )

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
        """The scalar this operator declares, read off one solved field.

        ``values`` may be a bare sequence or a TYPED field -- anything carrying a ``definition`` and
        ``values`` (a :class:`~engcore.data.field.FieldValue`). R-73 (I-25 part B): the unit and the
        ``field_id`` on this record were assertions about an array nobody checked, so a velocity field
        read through a temperature operator came back as a Quantity in kelvin. When the typed field is
        given, its id, its dimension and its support are checked against what this operator declares.
        Passing a sequence is still accepted, and still leaves the caller asserting both.
        """
        self.require_support(mesh)
        values = self._values_of_the_field_it_names(values, mesh)
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
            self._require_the_region_is_the_declared_one(region)
            indices = region.node_indices(mesh)
            return Quantity(float(np.mean(array[list(indices)])), self.unit)
        index = self.resolve_indices(mesh)[0]
        return Quantity(float(array[index]), self.unit)

    def _values_of_the_field_it_names(self, values: Any, mesh: StructuredMesh) -> Any:
        """The array, and -- for a typed field -- the check that it is the field this operator names."""
        definition = getattr(values, "definition", None)
        if definition is None:
            return values
        field_id = str(getattr(definition, "field_id", ""))
        if field_id != self.field_id:
            raise FieldObservationError(
                f"operator {self.operator_id!r} reads field {self.field_id!r} and was given "
                f"{field_id!r}"
            )
        unit = str(getattr(definition, "unit", ""))
        if dimensionality(unit) != dimensionality(self.unit):
            raise FieldObservationError(
                f"operator {self.operator_id!r} reports in {self.unit!r} and was given a field in "
                f"{unit!r}; a scalar read off it would carry this operator's unit and that field's "
                f"numbers"
            )
        mesh_id = str(getattr(definition, "mesh_id", ""))
        if mesh_id and mesh_id != mesh.mesh_id:
            raise FieldObservationError(
                f"operator {self.operator_id!r} was given a field declared on support {mesh_id!r} and a "
                f"support named {mesh.mesh_id!r}"
            )
        array = getattr(values, "values", None)
        if array is None:  # pragma: no cover - a definition with no values is not a field
            raise FieldObservationError(
                f"operator {self.operator_id!r} was given a field-shaped object carrying no values"
            )
        return array

    def _require_the_region_is_the_declared_one(self, region: MeshRegion) -> None:
        """R-73: the region decides WHICH nodes are averaged, and it was matched by label alone.

        The same operator, digest and region id returned the left edge or the right edge depending on
        which object was supplied. The operator now declares the region's content -- its support and its
        edge -- and those are in the digest, so two observations of two edges are two observations.

        An operator that declares neither is refused the region it cannot check: it was written before
        there was anywhere to say which content it reads, and answering from it would be the audited
        state with a field added.
        """
        if not self.region_mesh_id or not self.region_edge:
            raise FieldObservationError(
                f"operator {self.operator_id!r} names region {self.region_id!r} by id alone and declares "
                f"neither the support it is on nor which edge it is, so any region carrying that id "
                f"would be applied -- and the region decides which nodes are averaged. Declare "
                f"region_mesh_id and region_edge"
            )
        edge = getattr(region.edge, "value", str(region.edge))
        if region.mesh_id != self.region_mesh_id or edge != self.region_edge:
            raise FieldObservationError(
                f"operator {self.operator_id!r} reads region {self.region_id!r} on support "
                f"{self.region_mesh_id!r} at its {self.region_edge!r} edge, and was given a region on "
                f"{region.mesh_id!r} at its {edge!r} edge. Same label, different nodes"
            )

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
            # R-73: written only when declared, so an operator that says nothing
            # about the region's content keeps the digest it always had.
            **(
                {}
                if not (self.region_mesh_id or self.region_edge)
                else {
                    "region_mesh_id": self.region_mesh_id,
                    "region_edge": self.region_edge,
                }
            ),
        }

    @property
    def digest(self) -> str:
        blob = json.dumps(self._canonical(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "schema": (
                FIELD_OBSERVATION_SCHEMA_V2
                if (self.region_mesh_id or self.region_edge)
                else FIELD_OBSERVATION_SCHEMA
            ),
            **self._canonical(),
            "description": self.description,
            "digest": self.digest,
        }
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "FieldObservationOperator":
        version = require_schema_any(
            payload, (FIELD_OBSERVATION_SCHEMA, FIELD_OBSERVATION_SCHEMA_V2)
        )
        content = (
            str(payload.get("region_mesh_id", "")).strip(),
            str(payload.get("region_edge", "")).strip(),
        )
        if any(content) and version != FIELD_OBSERVATION_SCHEMA_V2:
            raise FieldObservationError(
                f"serialized operator declares schema {version!r} and carries a region's content, which "
                f"{FIELD_OBSERVATION_SCHEMA_V2!r} introduced"
            )
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
                region_mesh_id=content[0],
                region_edge=content[1],
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
