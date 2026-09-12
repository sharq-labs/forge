"""The values half: an array bound to a declaration, and the boundary it crosses.

Sprint 4, Phase 5 and Phase 6. The control plane holds identity, shape, units
and a summary; the numbers live here and reach a record only as a
content-addressed reference. These tests exercise that boundary in both
directions and the refusals on the way.
"""

from __future__ import annotations

import numpy as np
import pytest

from engcore.data.errors import BulkDataIntegrityError
from engcore.data.field import FieldValue
from engcore.data.resolver import BulkDataResolver
from engcore.data.store import InMemoryBulkStore
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.fields import (
    FieldDefinition,
    FieldLocation,
    StructuredMesh,
)
from engcore.scientific.units.quantity import Quantity


def mesh(mesh_id: str = "plate", nx: int = 5, ny: int = 3, lx: float = 1.0) -> StructuredMesh:
    return StructuredMesh(mesh_id, Quantity(lx, "meter"), Quantity(0.5, "meter"), nx, ny)


def temperature(**changes) -> FieldDefinition:
    return FieldDefinition("T", changes.pop("unit", "K"), changes.pop("mesh_id", "plate"), **changes)


def field(values=None, **changes) -> FieldValue:
    plate = changes.pop("mesh", None) or mesh()
    definition = changes.pop("definition", None) or temperature()
    if values is None:
        values = np.full(definition.expected_shape(plate), 300.0)
    return FieldValue(definition=definition, mesh=plate, values=values)


# ---- what the container refuses ---------------------------------------------------
def test_an_array_of_the_wrong_shape_is_refused():
    with pytest.raises(InvalidScientificProblem, match="equal counts are not equal fields"):
        field(np.full((5, 3), 300.0))  # the support is (3, 5)


def test_a_flat_array_of_the_right_length_is_still_refused():
    with pytest.raises(InvalidScientificProblem, match="expects shape"):
        field(np.full(15, 300.0))


def test_a_non_finite_entry_is_refused_and_named():
    values = np.full((3, 5), 300.0)
    values[1, 2] = np.nan
    with pytest.raises(InvalidScientificProblem, match=r"non-finite value\(s\), the first at index \(1, 2\)"):
        field(values)


def test_a_field_on_a_support_it_was_not_declared_on_is_refused():
    with pytest.raises(InvalidScientificProblem, match="is not a field of another"):
        FieldValue(temperature(), mesh("elsewhere"), np.full((3, 5), 300.0))


# ---- immutability ------------------------------------------------------------------
def test_the_values_are_copied_and_read_only():
    source = np.full((3, 5), 300.0)
    held = field(source)
    source[0, 0] = 999.0
    assert held.values[0, 0] == 300.0, "a record built from this must not move"
    with pytest.raises(ValueError):
        held.values[0, 0] = 1.0


# ---- units and summary -------------------------------------------------------------
def test_the_summary_is_unit_bearing_and_not_four_floats():
    values = np.arange(15, dtype=float).reshape(3, 5)
    summary = field(values).summary()
    assert summary.minimum == Quantity(0.0, "kelvin")
    assert summary.maximum == Quantity(14.0, "kelvin")
    assert summary.mean == Quantity(7.0, "kelvin")
    assert summary.l2_norm.units == "kelvin"
    assert summary.non_finite == 0


def test_a_unit_conversion_is_affine_and_not_a_scale_factor():
    """0 degC is 273.15 K, not 0 K: a factor alone gets this wrong."""
    kelvin = field(np.full((3, 5), 300.0))
    celsius = kelvin.to_unit("degC")
    assert celsius.unit == "degree_Celsius"
    assert celsius.values[0, 0] == pytest.approx(26.85)
    assert celsius.to_unit("kelvin").values[0, 0] == pytest.approx(300.0)


# ---- crossing the boundary ----------------------------------------------------------
def test_a_field_stores_its_values_and_reads_back_identical():
    store = InMemoryBulkStore()
    values = np.linspace(300.0, 400.0, 15).reshape(3, 5)
    original = field(values)
    record, reference = original.store(store)

    assert record.shape == (3, 5)
    assert reference.count == 15
    assert reference.unit == "kelvin"
    assert record.mesh_fingerprint == mesh().fingerprint()
    assert record.summary.maximum == Quantity(400.0, "kelvin")

    restored = FieldValue.from_record(record, mesh(), BulkDataResolver(store))
    assert restored == original
    assert np.array_equal(restored.values, values)


def test_a_record_cannot_be_read_back_against_another_support():
    store = InMemoryBulkStore()
    record, _ = field().store(store)
    resolver = BulkDataResolver(store)
    with pytest.raises(InvalidScientificProblem, match="same name, different geometry"):
        FieldValue.from_record(record, mesh(nx=9), resolver)


def test_tampered_bytes_are_refused_by_the_resolver():
    store = InMemoryBulkStore()
    record, reference = field().store(store)
    store._blobs[reference.digest] = b"\x00" * reference.byte_length  # noqa: SLF001
    with pytest.raises(BulkDataIntegrityError, match="modified or substituted"):
        FieldValue.from_record(record, mesh(), BulkDataResolver(store))


def test_a_cell_field_stores_the_cell_shape():
    store = InMemoryBulkStore()
    cells = temperature(location=FieldLocation.CELL)
    value = FieldValue(cells, mesh(), np.full((2, 4), 300.0))
    record, reference = value.store(store)
    assert record.shape == (2, 4)
    assert reference.count == 8
    assert FieldValue.from_record(record, mesh(), BulkDataResolver(store)) == value


def test_the_record_names_the_values_and_never_holds_them():
    record, _ = field().store(InMemoryBulkStore())
    payload = record.to_dict()
    assert "values" not in payload and "data" not in payload
    assert payload["reference"]["count"] == 15
    assert len(str(payload)) < 2000, "a record stays small however large the field is"
