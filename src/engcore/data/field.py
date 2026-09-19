"""One field's values, in the plane that is allowed to hold them.

``scientific/fields`` declares what a field is and carries no numbers: the core
imports no array library, and a mesh-sized array in a scientific record would
travel with every provenance payload that quotes it. This module is the other
half — the runtime object that actually holds the values, checks them against
the declaration, and hands them to the data plane through the reference the
control plane already understands.

    FieldDefinition + MeshSupport         what it is and where       (control)
    FieldValue                            the numbers                (here)
    ScientificDataReference               which numbers, by digest   (boundary)
    BulkDataStore / BulkDataResolver      where the bytes are        (runtime)

What it refuses, and why each one is a real state
-------------------------------------------------
* an array whose shape is not the shape the declaration and the support imply.
  A 16 x 32 array is not a 32 x 16 field, and nothing downstream can tell once
  it is flattened;
* a non-finite entry. A field with a NaN in it is not a solved field, and the
  summary a reader would act on — a mean, an extremum — is silently poisoned by
  one;
* a support the field was not declared on, which is the same refusal the
  declaration makes, applied where the values are.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from ..scientific.errors import InvalidScientificProblem
from ..scientific.fields.definition import FieldDefinition
from ..scientific.fields.mesh import CANONICAL_LENGTH, StructuredMesh
from ..scientific.fields.support import MeshSupport
from ..scientific.fields.profiles import SpatialProfile
from ..scientific.fields.regions import MeshRegion
from ..scientific.fields.result import (
    SUMMARY_AGREEMENT_RTOL,
    FieldRecord,
    FieldSummary,
)
from ..scientific.results.data_reference import ScientificDataReference
from ..scientific.units.quantity import Quantity
from .resolver import BulkDataResolver
from .store import BulkDataStore, store_values


def evaluate_on_mesh(
    profile: SpatialProfile, mesh: StructuredMesh, *, unit: str | None = None
) -> np.ndarray:
    """A law's values at every node of a support, shaped ``(ny, nx)``.

    The bridge between a law and an array, and the reason the law itself needs
    no array library: a profile answers one point at a time, and this is the
    one place that asks it for all of them.

    Coordinates come from the support in canonical length, so what a law is
    asked is a position and never an index.
    """
    profile.require_output_dimension(
        unit or profile.unit, context=f"evaluating a law over {mesh.mesh_id!r}"
    )
    scale = 1.0
    if unit is not None and unit != profile.unit:
        zero = Quantity(0.0, profile.unit).magnitude_in(unit)
        one = Quantity(1.0, profile.unit).magnitude_in(unit)
        scale = one - zero
    else:
        zero = 0.0

    xs, ys = mesh.axis_coordinates()
    values = np.empty((len(ys), len(xs)), dtype=np.float64)
    for j, y in enumerate(ys):
        for i, x in enumerate(xs):
            values[j, i] = profile.evaluate(x=x, y=y) * scale + zero
    return values


def evaluate_on_region(
    profile: SpatialProfile,
    region: MeshRegion,
    mesh: StructuredMesh,
    *,
    unit: str | None = None,
) -> dict[int, float]:
    """A law's value at each node of one edge, keyed by row-major node index.

    Keyed rather than ordered: the caller assembling a matrix needs to reach a
    node by its index, and a sequence would make the association positional
    again — which is the mistake the whole region record exists to remove.
    """
    region.require_support(mesh)
    lower, upper = region.span(mesh)
    profile.require_covers(
        lower, upper, context=f"a law bound to region {region.region_id!r}"
    )
    xs, ys = mesh.axis_coordinates()
    scale, zero = 1.0, 0.0
    if unit is not None and unit != profile.unit:
        profile.require_output_dimension(
            unit, context=f"a law bound to region {region.region_id!r}"
        )
        zero = Quantity(0.0, profile.unit).magnitude_in(unit)
        scale = Quantity(1.0, profile.unit).magnitude_in(unit) - zero

    values: dict[int, float] = {}
    for node in region.node_indices(mesh):
        j, i = divmod(node, mesh.nodes_x)
        values[node] = profile.evaluate(x=xs[i], y=ys[j]) * scale + zero
    return values


@dataclass(frozen=True)
class FieldValue:
    """A unit-bearing array bound to the declaration it satisfies.

    Immutable in the way the rest of this repository means it: the array is
    copied on construction and marked read-only, so a caller holding the
    original cannot edit a field that a record has already been built from.
    """

    definition: FieldDefinition
    mesh: MeshSupport
    values: np.ndarray

    def __post_init__(self) -> None:
        if not isinstance(self.definition, FieldDefinition):
            raise InvalidScientificProblem(
                f"a field value is bound to a FieldDefinition, got "
                f"{type(self.definition).__name__}"
            )
        self.definition.require_support(self.mesh)

        array = np.array(self.values, dtype=np.float64, copy=True)
        expected = self.definition.expected_shape(self.mesh)
        if array.shape != tuple(expected):
            raise InvalidScientificProblem(
                f"field {self.definition.field_id!r} on support "
                f"{self.mesh.mesh_id!r} expects shape {tuple(expected)} and was "
                f"given {array.shape}; equal counts are not equal fields"
            )
        if not np.all(np.isfinite(array)):
            bad = int(np.count_nonzero(~np.isfinite(array)))
            first = np.argwhere(~np.isfinite(array))[0]
            raise InvalidScientificProblem(
                f"field {self.definition.field_id!r} carries {bad} non-finite "
                f"value(s), the first at index {tuple(int(i) for i in first)}; a "
                f"field with one is not a solved field, and every summary a "
                f"reader would act on is poisoned by it"
            )
        array.setflags(write=False)
        object.__setattr__(self, "values", array)

    # ---- what it is ---------------------------------------------------------
    @property
    def unit(self) -> str:
        return self.definition.unit

    @property
    def shape(self) -> tuple[int, ...]:
        return tuple(self.values.shape)

    @property
    def count(self) -> int:
        return int(self.values.size)

    def summary(self) -> FieldSummary:
        """Statistics a reader can act on without resolving the bytes."""
        flat = self.values.reshape(-1)
        return FieldSummary(
            minimum=Quantity(float(flat.min()), self.unit),
            maximum=Quantity(float(flat.max()), self.unit),
            mean=Quantity(float(flat.mean()), self.unit),
            l2_norm=Quantity(float(math.sqrt(float(np.dot(flat, flat)))), self.unit),
            non_finite=0,
            magnitude_maximum=self._magnitude_maximum(),
        )

    def _magnitude_maximum(self) -> Quantity | None:
        """The largest per-node component magnitude, for a vector field (R-55).

        ``minimum`` and ``maximum`` above are the envelope over flattened components, which for a vector
        field is a BOX: (1, 1, 1) m/s sits inside a 1.2 m/s box per component and its speed is 1.732. The
        bound a declarer writes for a vector field is the bound on the speed, and it cannot be recovered
        from the box, so it is computed here where the array is in hand. ``None`` for a scalar field,
        where the two questions are the same one.
        """
        components = int(self.definition.components)
        if components <= 1:
            return None
        # The component axis is the last one: `expected_shape` appends it, which
        # is the layout every field record in this repository carries.
        per_node = self.values.reshape(-1, components)
        magnitudes = np.sqrt(np.sum(per_node * per_node, axis=1))
        return Quantity(float(magnitudes.max()), self.unit)

    def to_unit(self, unit: str) -> "FieldValue":
        """The same field in another unit of the same dimension.

        Two-point rather than a scale factor, so an affine scale converts
        correctly: a factor alone turns 0 degC into 0 K.
        """
        zero = Quantity(0.0, self.unit).magnitude_in(unit)
        one = Quantity(1.0, self.unit).magnitude_in(unit)
        converted = self.values * (one - zero) + zero
        return FieldValue(
            definition=FieldDefinition(
                field_id=self.definition.field_id,
                unit=unit,
                mesh_id=self.definition.mesh_id,
                location=self.definition.location,
                components=self.definition.components,
                description=self.definition.description,
            ),
            mesh=self.mesh,
            values=converted,
        )

    # ---- crossing the boundary ---------------------------------------------
    def store(
        self, store: BulkDataStore, *, name: str | None = None
    ) -> tuple[FieldRecord, ScientificDataReference]:
        """Put the values in ``store`` and return the record naming them.

        The record is what a ``ScientificResult`` carries; the store is a
        runtime fact the caller owns. Nothing about which store was used reaches
        the record, which is the property DATA-BOUNDARY0 established.
        """
        reference = store_values(
            store,
            name or f"{self.definition.field_id}:field",
            self.values.reshape(-1).tolist(),
            unit=self.unit,
        )
        record = FieldRecord(
            definition=self.definition,
            mesh_fingerprint=self.mesh.fingerprint(),
            shape=self.shape,
            reference=reference,
            summary=self.summary(),
            # R-55 (I-25 part A): the summary was derived from exactly these
            # bytes, and this is the record saying so. It is what lets a
            # validity predicate act on a summary at all without holding the
            # array itself.
            summary_verified_against=reference.digest,
        )
        return record, reference

    @classmethod
    def from_record(
        cls, record: FieldRecord, mesh: MeshSupport, resolver: BulkDataResolver
    ) -> "FieldValue":
        """Read a field back, against the support it says it was solved on.

        ``verify_against`` runs first: resolving bytes for a record that belongs
        to another support would produce an array of the right length and the
        wrong meaning, which is the whole failure this layer exists to prevent.
        """
        record.verify_against(mesh)
        values = resolver.resolve(record.reference)
        array = np.asarray(values, dtype=np.float64).reshape(record.shape)
        field = cls(definition=record.definition, mesh=mesh, values=array)
        field._require_the_summary_describes_these_values(record)
        return field

    def _require_the_summary_describes_these_values(self, record: FieldRecord) -> None:
        """R-55: the one place the bytes and the summary are both in hand, and it did not look.

        The bytes are content-addressed and the summary is not, so a record whose values held a 900 K hot
        spot carried a summary saying 310 K with its reference digest unchanged -- and every reader that
        acts on the summary, including two registered validity predicates, believed it.

        Compared relatively, within ``SUMMARY_AGREEMENT_RTOL``: a sum is order-dependent in floating point
        and a store may hand the same values back in a different layout.
        """
        derived = self.summary()
        unit = self.unit
        for label in ("minimum", "maximum", "mean", "l2_norm", "magnitude_maximum"):
            claimed = getattr(record.summary, label)
            actual = getattr(derived, label)
            if claimed is None or actual is None:
                # A summary written before `magnitude_maximum` existed states
                # nothing about it, and an absence is not a disagreement. What
                # it costs is stated on the record: a predicate over a vector
                # field without it answers UNKNOWN.
                continue
            left = claimed.magnitude_in(unit)
            right = actual.magnitude_in(unit)
            scale = max(abs(left), abs(right))
            if abs(left - right) > SUMMARY_AGREEMENT_RTOL * scale:
                raise InvalidScientificProblem(
                    f"field {record.definition.field_id!r} summarizes its {label} as {claimed} and its "
                    f"own values give {actual}. A summary is what a reader acts on without resolving a "
                    f"mesh-sized array, and these bytes do not say what it says"
                )
        if record.summary.non_finite != derived.non_finite:
            raise InvalidScientificProblem(
                f"field {record.definition.field_id!r} counts {record.summary.non_finite} non-finite "
                f"value(s) and its own values hold {derived.non_finite}"
            )

    def __str__(self) -> str:  # pragma: no cover - display only
        return (
            f"{self.definition.field_id}{self.shape} in {self.unit} on "
            f"{self.mesh.mesh_id}@{self.mesh.fingerprint()[:12]}"
        )

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, FieldValue):
            return NotImplemented
        return (
            self.definition == other.definition
            and self.mesh == other.mesh
            and self.values.shape == other.values.shape
            and bool(np.array_equal(self.values, other.values))
        )
