"""Additive UNKNOWN diagnostics refine causes without changing verdict semantics."""

from __future__ import annotations

import numpy as np
import pytest

from engcore.scientific.fields import (
    FieldDefinition,
    FieldLocation,
    FieldRecord,
    FieldSummary,
    StructuredMesh,
)
from engcore.scientific.models import (
    FieldFiniteCondition,
    FieldRangeCondition,
    MeshResolutionCondition,
    RangeCondition,
    ValidityDomain,
)
from engcore.scientific.models.definition import UnknownReason, ValidityStatus
from engcore.scientific.models.unknown_diagnostics import (
    UnknownCause,
    UnknownDiagnostic,
    diagnose_unknowns,
)
from engcore.scientific.results.data_reference import ScientificDataReference
from engcore.scientific.units.quantity import Quantity


def _mesh() -> StructuredMesh:
    return StructuredMesh(
        mesh_id="plate",
        length_x=Quantity(1.0, "meter"),
        length_y=Quantity(0.5, "meter"),
        nodes_x=4,
        nodes_y=3,
    )


def _field(*, non_finite: int = 0) -> FieldRecord:
    mesh = _mesh()
    definition = FieldDefinition(
        field_id="T",
        unit="kelvin",
        mesh_id=mesh.mesh_id,
        location=FieldLocation.NODE,
        components=1,
    )
    count = definition.expected_count(mesh)
    reference, _ = ScientificDataReference.for_values(
        "T:field", [300.0] * count, unit="kelvin"
    )
    return FieldRecord(
        definition=definition,
        mesh_fingerprint=mesh.fingerprint(),
        shape=definition.expected_shape(mesh),
        reference=reference,
        summary=FieldSummary(
            minimum=Quantity(290.0, "kelvin"),
            maximum=Quantity(310.0, "kelvin"),
            mean=Quantity(300.0, "kelvin"),
            l2_norm=Quantity(310.0, "kelvin"),
            non_finite=non_finite,
        ),
        # R-55 (I-25 part A): a field predicate decides from a summary only when the record says that
        # summary was derived from the bytes its reference names -- an unbound summary is the record's own
        # word about an array nobody resolved, and it used to be believed. This fixture writes its summary
        # by hand for the case under test and declares the binding deliberately, because what this file
        # exercises is the diagnostic channel and not the binding.
        summary_verified_against=reference.digest,
    )


def test_missing_value_refines_not_supplied_to_missing_input():
    domain = ValidityDomain(
        conditions=(
            FieldRangeCondition(
                name="temperature_range",
                field="temperature_field",
                maximum=Quantity(320.0, "kelvin"),
            ),
        )
    )
    assessment = domain.assess({})
    diagnostic = diagnose_unknowns(domain, assessment, {})[0]
    assert diagnostic.stable_reason is UnknownReason.NOT_SUPPLIED
    assert diagnostic.cause is UnknownCause.MISSING_INPUT
    assert diagnostic.context_key == "temperature_field"
    assert diagnostic.actionable


def test_nonfinite_typed_field_is_not_misreported_as_a_raw_shape_problem():
    domain = ValidityDomain(
        conditions=(
            FieldRangeCondition(
                name="temperature_range",
                field="temperature_field",
                maximum=Quantity(320.0, "kelvin"),
            ),
        )
    )
    context = {"temperature_field": _field(non_finite=2)}
    assessment = domain.assess(context)
    assert assessment.status is ValidityStatus.UNKNOWN
    assert assessment.reason_for("temperature_range") is UnknownReason.UNREADABLE_SHAPE

    diagnostic = diagnose_unknowns(domain, assessment, context)[0]
    assert diagnostic.cause is UnknownCause.NONFINITE_FIELD
    assert diagnostic.value_type == "FieldRecord"
    assert not diagnostic.actionable


def test_raw_numpy_array_is_named_as_untyped_structured_value():
    domain = ValidityDomain(
        conditions=(
            FieldRangeCondition(
                name="temperature_range",
                field="temperature_field",
                maximum=Quantity(320.0, "kelvin"),
            ),
        )
    )
    context = {"temperature_field": np.array([290.0, 300.0, 310.0])}
    assessment = domain.assess(context)
    diagnostic = diagnose_unknowns(domain, assessment, context)[0]
    assert diagnostic.stable_reason is UnknownReason.UNREADABLE_SHAPE
    assert diagnostic.cause is UnknownCause.UNTYPED_STRUCTURED_VALUE
    assert diagnostic.actionable
    assert "FieldRecord" in diagnostic.detail


def test_scalar_range_receiving_a_typed_field_names_the_contract_mismatch():
    domain = ValidityDomain(
        conditions=(
            RangeCondition(name="temperature", maximum=Quantity(320.0, "kelvin")),
        )
    )
    context = {"temperature": _field()}
    assessment = domain.assess(context)
    diagnostic = diagnose_unknowns(domain, assessment, context)[0]
    assert diagnostic.cause is UnknownCause.STRUCTURED_VALUE_FOR_SCALAR_CONDITION
    assert not diagnostic.actionable
    assert "field-aware" in diagnostic.detail


def test_field_condition_given_scalar_names_field_record_requirement():
    domain = ValidityDomain(
        conditions=(FieldFiniteCondition(name="finite_T", field="temperature_field"),)
    )
    context = {"temperature_field": Quantity(300.0, "kelvin")}
    assessment = domain.assess(context)
    diagnostic = diagnose_unknowns(domain, assessment, context)[0]
    assert diagnostic.cause is UnknownCause.FIELD_RECORD_REQUIRED
    assert diagnostic.actionable


def test_mesh_condition_given_field_names_structured_mesh_requirement():
    domain = ValidityDomain(
        conditions=(
            MeshResolutionCondition(name="resolution", mesh="support", min_nodes_x=3),
        )
    )
    context = {"support": _field()}
    assessment = domain.assess(context)
    diagnostic = diagnose_unknowns(domain, assessment, context)[0]
    assert diagnostic.cause is UnknownCause.STRUCTURED_MESH_REQUIRED
    assert diagnostic.context_key == "support"


def test_prerequisite_reason_stays_distinct_from_the_value_shape():
    domain = ValidityDomain(
        conditions=(
            FieldFiniteCondition(name="finite_T", field="temperature_field"),
            FieldRangeCondition(
                name="range_T",
                field="temperature_field",
                maximum=Quantity(320.0, "kelvin"),
                requires=("finite_T",),
            ),
        )
    )
    context = {"temperature_field": _field(non_finite=1)}
    assessment = domain.assess(context)
    diagnostics = {item.condition: item for item in diagnose_unknowns(domain, assessment, context)}

    # finite_T is violated, not UNKNOWN. range_T is skipped because its
    # prerequisite failed, and diagnostics must preserve that causal order.
    assert set(diagnostics) == {"range_T"}
    assert diagnostics["range_T"].stable_reason is UnknownReason.PREREQUISITE_NOT_ESTABLISHED
    assert diagnostics["range_T"].cause is UnknownCause.PREREQUISITE_NOT_ESTABLISHED
    assert not diagnostics["range_T"].actionable


def test_diagnostics_do_not_reassess_or_change_the_original_verdict():
    domain = ValidityDomain(
        conditions=(FieldFiniteCondition(name="finite_T", field="temperature_field"),)
    )
    context = {"temperature_field": Quantity(300.0, "kelvin")}
    assessment = domain.assess(context)
    before = assessment.to_dict()
    diagnose_unknowns(domain, assessment, context)
    assert assessment.to_dict() == before
    assert assessment.status is ValidityStatus.UNKNOWN


def test_diagnostic_round_trip_derives_actionability_from_cause():
    item = UnknownDiagnostic(
        condition="T",
        stable_reason=UnknownReason.UNREADABLE_SHAPE,
        cause=UnknownCause.FIELD_RECORD_REQUIRED,
        context_key="temperature",
        value_type="Quantity",
        detail="typed field required",
    )
    payload = item.to_dict()
    assert UnknownDiagnostic.from_dict(payload) == item

    forged = dict(payload)
    forged["actionable"] = False
    with pytest.raises(Exception, match="actionable"):
        UnknownDiagnostic.from_dict(forged)
