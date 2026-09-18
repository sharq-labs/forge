"""Core re-audit 2026-09-16, batch 52: a field summary is bound to the field it summarizes.

Problem R-55 (the audit's findings 67 and 70), improvement I-25 part A of two, under
benchmarks/core_v4_false_confidence/BATCH52_THRESHOLD_PROTOCOL.json.

The summary is what every reader acts on without resolving a mesh-sized array, and it is the record's own
word: nothing binds it to the bytes the reference names, to the field's unit, or even to itself. A record
whose bytes hold a 900 K hot spot reads IN_DOMAIN under a 500 K maximum once its summary says 310 K, with
the reference digest unchanged. And a 3-component velocity of (1, 1, 1) m/s -- magnitude 1.732 -- passes a
1.2 m/s maximum, because the envelope is taken over flattened components.

Recorded as strict xfails in commit 2e5b9565, each seen failing on its own assertion, before the fix.
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pytest

from engcore.data.field import FieldValue
from engcore.data.resolver import BulkDataResolver
from engcore.data.store import InMemoryBulkStore
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.fields.definition import FieldDefinition, FieldLocation
from engcore.scientific.fields.mesh import StructuredMesh
from engcore.scientific.fields.result import FieldRecord, FieldSummary
from engcore.scientific.models.definition import ValidityStatus
from engcore.scientific.models.structured_validity import (
    FieldFiniteCondition,
    FieldRangeCondition,
)
from engcore.scientific.results.data_reference import ScientificDataReference
from engcore.scientific.units.quantity import Quantity


def _mesh(nx: int = 3, ny: int = 2) -> StructuredMesh:
    return StructuredMesh(
        mesh_id="plate", length_x=Quantity(1.0, "meter"), length_y=Quantity(0.5, "meter"),
        nodes_x=nx, nodes_y=ny,
    )


def _definition(*, components: int = 1, unit: str = "kelvin") -> FieldDefinition:
    return FieldDefinition(
        field_id="T", unit=unit, mesh_id="plate", location=FieldLocation.NODE,
        components=components,
    )


def _stored(values, *, components: int = 1, unit: str = "kelvin"):
    """A field put in a store, with the record its own values produced."""
    mesh = _mesh()
    definition = _definition(components=components, unit=unit)
    field = FieldValue(definition=definition, mesh=mesh,
                       values=np.asarray(values, dtype=np.float64).reshape(
                           definition.expected_shape(mesh)))
    store = InMemoryBulkStore()
    record, _reference = field.store(store)
    return record, BulkDataResolver(store), mesh


def _record(*, summary: FieldSummary | None = None, components: int = 1,
            values: float = 300.0, unit: str = "kelvin") -> FieldRecord:
    mesh = _mesh()
    definition = _definition(components=components, unit=unit)
    count = definition.expected_count(mesh)
    reference, _payload = ScientificDataReference.for_values(
        "T:field", [values] * count, unit=unit)
    return FieldRecord(
        definition=definition, mesh_fingerprint=mesh.fingerprint(),
        shape=definition.expected_shape(mesh), reference=reference,
        summary=summary or FieldSummary(
            minimum=Quantity(290.0, unit), maximum=Quantity(310.0, unit),
            mean=Quantity(300.0, unit), l2_norm=Quantity(310.0, unit),
        ),
    )


# ---------------------------------------------------------------------------
# a_summary_agrees_with_itself_and_with_the_field_it_summarizes
# ---------------------------------------------------------------------------
def test_r55_an_honest_summary_is_unchanged():
    """The control."""
    assert _record().summary.mean.magnitude_in("kelvin") == pytest.approx(300.0)


def test_r55_a_mean_outside_its_own_range_is_refused():
    with pytest.raises(InvalidScientificProblem, match="mean"):
        FieldSummary(minimum=Quantity(290.0, "kelvin"), maximum=Quantity(310.0, "kelvin"),
                     mean=Quantity(900.0, "kelvin"), l2_norm=Quantity(310.0, "kelvin"))


def test_r55_a_negative_norm_is_refused():
    with pytest.raises(InvalidScientificProblem, match="l2_norm|norm"):
        FieldSummary(minimum=Quantity(290.0, "kelvin"), maximum=Quantity(310.0, "kelvin"),
                     mean=Quantity(300.0, "kelvin"), l2_norm=Quantity(-1.0, "kelvin"))


def test_r55_a_summary_in_another_dimension_is_refused():
    with pytest.raises(InvalidScientificProblem, match="dimension|kelvin|pascal"):
        _record(summary=FieldSummary(
            minimum=Quantity(290.0, "pascal"), maximum=Quantity(310.0, "pascal"),
            mean=Quantity(300.0, "pascal"), l2_norm=Quantity(310.0, "pascal")))


def test_r55_more_non_finite_values_than_values_is_refused():
    with pytest.raises(InvalidScientificProblem, match="non_finite|count"):
        _record(summary=FieldSummary(
            minimum=Quantity(290.0, "kelvin"), maximum=Quantity(310.0, "kelvin"),
            mean=Quantity(300.0, "kelvin"), l2_norm=Quantity(310.0, "kelvin"),
            non_finite=10_000))


# ---------------------------------------------------------------------------
# a_summary_is_re_derived_from_the_bytes_it_claims_to_summarize
# ---------------------------------------------------------------------------
def test_r55_a_field_read_back_from_its_own_record_still_works():
    """The control, and the path the rule lives on."""
    record, store, mesh = _stored([300.0] * 6)
    field = FieldValue.from_record(record, mesh, store)
    assert field.values.max() == pytest.approx(300.0)


def test_r55_a_summary_that_does_not_match_the_bytes_is_refused_on_read():
    record, store, mesh = _stored([300.0, 300.0, 300.0, 300.0, 300.0, 900.0])
    forged = dataclasses.replace(record, summary=FieldSummary(
        minimum=Quantity(290.0, "kelvin"), maximum=Quantity(310.0, "kelvin"),
        mean=Quantity(300.0, "kelvin"), l2_norm=Quantity(310.0, "kelvin")))
    assert forged.reference == record.reference, "the reference digest is unchanged, which is the point"
    with pytest.raises(InvalidScientificProblem, match="summary"):
        FieldValue.from_record(forged, mesh, store)


# ---------------------------------------------------------------------------
# a_predicate_that_decides_from_a_summary_needs_a_verified_record
# ---------------------------------------------------------------------------
def test_r55_a_range_predicate_will_not_decide_from_an_unbound_summary():
    condition = FieldRangeCondition(name="T", maximum=Quantity(500.0, "kelvin"))
    assert condition.evaluate(_record()) is ValidityStatus.UNKNOWN


def test_r55_a_finiteness_predicate_will_not_decide_from_an_unbound_summary():
    condition = FieldFiniteCondition(name="T")
    assert condition.evaluate(_record()) is ValidityStatus.UNKNOWN


def test_r55_a_record_bound_to_its_bytes_is_decided_as_before():
    record, _store, _mesh = _stored([300.0] * 6)
    condition = FieldRangeCondition(name="T", maximum=Quantity(500.0, "kelvin"))
    assert condition.evaluate(record) is ValidityStatus.IN_DOMAIN
    assert FieldFiniteCondition(name="T").evaluate(record) is ValidityStatus.IN_DOMAIN


# ---------------------------------------------------------------------------
# an_envelope_over_a_vector_field_is_about_its_magnitude
# ---------------------------------------------------------------------------
def test_r55_a_vector_field_is_judged_on_its_magnitude():
    record, _store, _mesh = _stored([1.0] * 18, components=3, unit="meter / second")
    condition = FieldRangeCondition(name="T", maximum=Quantity(1.2, "meter / second"))
    assert condition.evaluate(record) is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN


def test_r55_a_vector_field_inside_the_bound_still_passes():
    record, _store, _mesh = _stored([0.5] * 18, components=3, unit="meter / second")
    condition = FieldRangeCondition(name="T", maximum=Quantity(1.2, "meter / second"))
    assert condition.evaluate(record) is ValidityStatus.IN_DOMAIN


def test_r55_a_vector_record_without_a_magnitude_is_unknown():
    names = {field.name for field in dataclasses.fields(FieldSummary)}
    assert "magnitude_maximum" in names, "a vector field's envelope has nowhere to be recorded"
    record = _record(components=3, unit="meter / second", values=1.0, summary=FieldSummary(
        minimum=Quantity(1.0, "meter / second"), maximum=Quantity(1.0, "meter / second"),
        mean=Quantity(1.0, "meter / second"), l2_norm=Quantity(4.24, "meter / second")))
    condition = FieldRangeCondition(name="T", maximum=Quantity(1.2, "meter / second"))
    assert condition.evaluate(record) is ValidityStatus.UNKNOWN


def test_r55_a_bound_vector_record_without_a_magnitude_is_still_unknown():
    """The case only the magnitude rule sees, found while running this batch's mutations: the record IS
    bound to its own bytes and still carries no magnitude, because it was written before the field
    existed. The per-component envelope cannot answer the question the bound asks."""
    mesh = _mesh()
    definition = _definition(components=3, unit="meter / second")
    count = definition.expected_count(mesh)
    reference, _payload = ScientificDataReference.for_values(
        "T:field", [1.0] * count, unit="meter / second")
    record = FieldRecord(
        definition=definition, mesh_fingerprint=mesh.fingerprint(),
        shape=definition.expected_shape(mesh), reference=reference,
        summary=FieldSummary(
            minimum=Quantity(1.0, "meter / second"), maximum=Quantity(1.0, "meter / second"),
            mean=Quantity(1.0, "meter / second"), l2_norm=Quantity(4.24, "meter / second")),
        summary_verified_against=reference.digest,
    )
    assert record.summary_is_bound_to_its_values is True
    condition = FieldRangeCondition(name="T", maximum=Quantity(1.2, "meter / second"))
    assert condition.evaluate(record) is ValidityStatus.UNKNOWN
