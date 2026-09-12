"""When may one solve's field be another solve's input?

Sprint 4, Phases 12 and 13. A scalar crossing is checked by dimension, and a
field crossing has three more questions in it that a dimension check cannot
reach: which support the values sit on, how many there are and where, and
whether the consumer's support is the same one.

The compatibility matrix is enumerated rather than sampled, because the
interesting entries are the ones that look fine. Two fields of equal length
are two arrays and an array is assignable to an array, so every pair below
would cross silently under any contract that compares shapes or counts.
"""

from __future__ import annotations

import pytest

from engcore.data.field import FieldValue
from engcore.data.store import InMemoryBulkStore
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.fields import (
    FieldDefinition,
    FieldDependency,
    FieldLocation,
    FieldTransferVerdict,
    StructuredMesh,
    TransferKind,
    check_field_transfer,
)
from engcore.scientific.units.quantity import Quantity

import numpy as np


def mesh(mesh_id="plate", nx=16, ny=16, lx=1.0, ly=1.0, ox=0.0):
    return StructuredMesh(
        mesh_id,
        Quantity(lx, "meter"),
        Quantity(ly, "meter"),
        nx,
        ny,
        origin_x=Quantity(ox, "meter"),
    )


def field(field_id="T", unit="kelvin", mesh_id="plate", **changes):
    return FieldDefinition(field_id, unit, mesh_id, **changes)


# ---- Phase 13: the matrix -----------------------------------------------------------
#: ``(label, producer, producer mesh, consumer, consumer mesh, verdict)``.
#: Every row has equal or plausibly-equal data on both sides.
MATRIX = [
    (
        "identical",
        field(), mesh(), field(), mesh(),
        FieldTransferVerdict.COMPATIBLE,
    ),
    (
        "same geometry, renamed support",
        field(), mesh(), field(mesh_id="other"), mesh("other"),
        FieldTransferVerdict.COMPATIBLE,
    ),
    (
        "same geometry, twice the resolution",
        field(), mesh(),
        field(mesh_id="fine"), mesh("fine", nx=31, ny=31),
        FieldTransferVerdict.REQUIRES_PROJECTION,
    ),
    (
        "nodes against cells",
        field(), mesh(),
        field(location=FieldLocation.CELL), mesh(),
        FieldTransferVerdict.REQUIRES_PROJECTION,
    ),
    (
        "one support, two units of one dimension",
        field(), mesh(), field(unit="degC"), mesh(),
        FieldTransferVerdict.REQUIRES_UNIT_CONVERSION,
    ),
    (
        "equal counts, transposed support",
        field(), mesh(nx=32, ny=16, lx=2.0),
        field(mesh_id="turned"), mesh("turned", nx=16, ny=32, lx=1.0, ly=2.0),
        FieldTransferVerdict.REFUSED,
    ),
    (
        "same resolution, different rectangle",
        field(), mesh(),
        field(mesh_id="bigger"), mesh("bigger", lx=2.0),
        FieldTransferVerdict.REFUSED,
    ),
    (
        "same rectangle, moved",
        field(), mesh(),
        field(mesh_id="shifted"), mesh("shifted", ox=5.0),
        FieldTransferVerdict.REFUSED,
    ),
    (
        "different dimension",
        field(), mesh(), field(unit="volt"), mesh(),
        FieldTransferVerdict.REFUSED,
    ),
    (
        "scalar against a vector field",
        field(), mesh(), field(components=2), mesh(),
        FieldTransferVerdict.REFUSED,
    ),
]


@pytest.mark.parametrize(
    "label, producer, producer_mesh, consumer, consumer_mesh, expected",
    MATRIX,
    ids=[row[0] for row in MATRIX],
)
def test_the_compatibility_matrix(
    label, producer, producer_mesh, consumer, consumer_mesh, expected
):
    contract = check_field_transfer(producer, producer_mesh, consumer, consumer_mesh)
    assert contract.verdict is expected, f"{label}: {contract.reason}"
    assert contract.may_cross_directly == (expected is FieldTransferVerdict.COMPATIBLE)
    assert contract.reason.strip(), "every verdict states why it was reached"


#: Matrix rows whose two sides differ in length, so a count comparison would
#: have caught them too. Named rather than filtered, because the value of the
#: matrix is in the rows that are *not* here: those cross silently under any
#: check that compares shapes or counts, and they are the majority.
CAUGHT_BY_LENGTH_TOO = {
    "same geometry, twice the resolution",
    "nodes against cells",
    "scalar against a vector field",
}


def test_every_matrix_pair_would_have_matched_on_length():
    """The matrix is only worth something if a naive check would pass it all."""
    for label, producer, producer_mesh, consumer, consumer_mesh, _ in MATRIX:
        produced = producer.expected_count(producer_mesh)
        consumed = consumer.expected_count(consumer_mesh)
        if label in CAUGHT_BY_LENGTH_TOO:
            continue
        assert produced == consumed, (
            f"{label} differs in length ({produced} against {consumed}), so it "
            f"does not test what this matrix exists to test"
        )


def test_a_contract_round_trips():
    contract = check_field_transfer(field(), mesh(), field(unit="degC"), mesh())
    from engcore.scientific.fields import FieldTransferContract

    assert FieldTransferContract.from_dict(contract.to_dict()) == contract


# ---- Phase 12: declaring the crossing ------------------------------------------------
def test_a_field_dependency_names_both_sides_and_round_trips():
    dependency = FieldDependency("upstream", "T", "downstream", "T_ambient")
    assert dependency.name == "upstream.T->downstream.T_ambient"
    assert dependency.kind is TransferKind.FIELD_TRANSFER
    assert FieldDependency.from_dict(dependency.to_dict()) == dependency


def stored_record(definition=None, support=None):
    support = support or mesh()
    definition = definition or field(mesh_id=support.mesh_id)
    values = FieldValue(definition, support, np.full(definition.expected_shape(support), 300.0))
    record, _ = values.store(InMemoryBulkStore())
    return record


def test_a_field_dependency_refuses_a_scalar_summary_of_the_field():
    """The failure this record exists for: a mean has the field's dimension."""
    dependency = FieldDependency("upstream", "T", "downstream", "T_in")
    with pytest.raises(InvalidScientificProblem, match="summary of a field is not"):
        dependency.admit(Quantity(300.0, "kelvin"))


def test_a_scalar_dependency_refuses_a_whole_field():
    dependency = FieldDependency(
        "upstream", "T", "downstream", "T_in", kind=TransferKind.SCALAR_TRANSFER
    )
    with pytest.raises(InvalidScientificProblem, match="which number of it was meant"):
        dependency.admit(stored_record())
    dependency.admit(Quantity(300.0, "kelvin"))  # and this is what it wanted


def test_a_dependency_refuses_a_field_that_is_not_the_one_it_names():
    dependency = FieldDependency("upstream", "T", "downstream", "T_in")
    with pytest.raises(InvalidScientificProblem, match="names 'T' as its source"):
        dependency.admit(stored_record(definition=field(field_id="pressure")))
    dependency.admit(stored_record())


def test_a_dependency_resolves_to_the_contract_for_its_own_two_sides():
    dependency = FieldDependency("upstream", "T", "downstream", "T_in")
    contract = dependency.resolve(
        field(), mesh(), field(field_id="T_in", mesh_id="fine"), mesh("fine", nx=31, ny=31)
    )
    assert contract.verdict is FieldTransferVerdict.REQUIRES_PROJECTION

    with pytest.raises(InvalidScientificProblem, match="names 'T_in' as its target"):
        dependency.resolve(field(), mesh(), field(field_id="elsewhere"), mesh())


# ---- Sprint 5, Phase 16: a law is not a payload -------------------------------------
def profile():
    from engcore.scientific.fields import LinearProfile1D, ProfileAxis

    return LinearProfile1D(
        ProfileAxis.Y, Quantity(300.0, "kelvin"), Quantity(20.0, "kelvin/meter")
    )


@pytest.mark.parametrize(
    "kind", [TransferKind.FIELD_TRANSFER, TransferKind.SCALAR_TRANSFER]
)
def test_a_spatial_law_is_not_something_that_crosses(kind):
    """Profiles are declarations; results are what cross.

    The two are easy to conflate now that both carry a unit and both describe a
    field. A law says what a field *should* be everywhere, and is an input; a
    record names values that were computed, and is an output. A dependency
    satisfied by a law would have been satisfied by nothing at all.
    """
    dependency = FieldDependency("upstream", "T", "downstream", "T_in", kind=kind)
    with pytest.raises(InvalidScientificProblem, match="was offered"):
        dependency.admit(profile())


def test_a_law_and_a_field_on_one_support_are_not_interchangeable():
    record = stored_record()
    law = profile()
    assert law.unit == record.definition.unit
    assert not hasattr(law, "reference"), "a law names no bytes"
    assert not hasattr(record, "evaluate"), "a record evaluates nothing"
    assert law.fingerprint() != record.mesh_fingerprint


def test_the_transfer_matrix_is_unchanged_by_profiles():
    """Sprint 4's verdicts still hold, with the profile layer present."""
    for label, producer, producer_mesh, consumer, consumer_mesh, expected in MATRIX:
        contract = check_field_transfer(
            producer, producer_mesh, consumer, consumer_mesh
        )
        assert contract.verdict is expected, label


def test_a_scalar_dependency_has_no_field_contract_to_resolve():
    dependency = FieldDependency(
        "upstream", "T", "downstream", "T_in", kind=TransferKind.SCALAR_TRANSFER
    )
    with pytest.raises(InvalidScientificProblem, match="no field contract"):
        dependency.resolve(field(), mesh(), field(field_id="T_in"), mesh())
