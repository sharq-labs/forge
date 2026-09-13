"""Field-aware model validity without weakening the scalar scientific IR."""

from __future__ import annotations

import numpy as np

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
    FieldStructureCondition,
    MeshResolutionCondition,
    RangeCondition,
    UnknownReason,
    ValidityDomain,
    ValidityStatus,
)
from engcore.scientific.results.data_reference import ScientificDataReference
from engcore.scientific.units.quantity import Quantity


def _mesh(*, nx: int = 5, ny: int = 3) -> StructuredMesh:
    return StructuredMesh(
        mesh_id="plate",
        length_x=Quantity(1.0, "meter"),
        length_y=Quantity(0.5, "meter"),
        nodes_x=nx,
        nodes_y=ny,
    )


def _record(
    *,
    components: int = 1,
    location: FieldLocation = FieldLocation.NODE,
    minimum: float = 290.0,
    maximum: float = 310.0,
    non_finite: int = 0,
) -> FieldRecord:
    mesh = _mesh()
    definition = FieldDefinition(
        field_id="T",
        unit="kelvin",
        mesh_id=mesh.mesh_id,
        location=location,
        components=components,
    )
    shape = definition.expected_shape(mesh)
    count = definition.expected_count(mesh)
    reference, _ = ScientificDataReference.for_values(
        "T:field", [300.0] * count, unit="kelvin"
    )
    return FieldRecord(
        definition=definition,
        mesh_fingerprint=mesh.fingerprint(),
        shape=shape,
        reference=reference,
        summary=FieldSummary(
            minimum=Quantity(minimum, "kelvin"),
            maximum=Quantity(maximum, "kelvin"),
            mean=Quantity((minimum + maximum) / 2.0, "kelvin"),
            l2_norm=Quantity(max(abs(minimum), abs(maximum)), "kelvin"),
            non_finite=non_finite,
        ),
    )


def test_field_range_checks_the_whole_envelope_without_resolving_values():
    field = _record(minimum=290.0, maximum=310.0)
    admitted = FieldRangeCondition(
        name="temperature_envelope",
        field="temperature_field",
        minimum=Quantity(280.0, "kelvin"),
        maximum=Quantity(320.0, "kelvin"),
    )
    too_hot = FieldRangeCondition(
        name="temperature_envelope",
        field="temperature_field",
        maximum=Quantity(305.0, "kelvin"),
    )

    assert admitted.evaluate(field) is ValidityStatus.IN_DOMAIN
    assert too_hot.evaluate(field) is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
    assert admitted.evaluate_in({"temperature_field": field}) is ValidityStatus.IN_DOMAIN


def test_open_field_range_endpoints_are_exact_contract_logic():
    field = _record(minimum=290.0, maximum=310.0)
    closed = FieldRangeCondition(
        name="closed", field="T", maximum=Quantity(310.0, "kelvin")
    )
    open_ = FieldRangeCondition(
        name="open",
        field="T",
        maximum=Quantity(310.0, "kelvin"),
        maximum_inclusive=False,
    )
    assert closed.evaluate(field) is ValidityStatus.IN_DOMAIN
    assert open_.evaluate(field) is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN


def test_field_conditions_refuse_the_raw_array_escape_hatch():
    condition = FieldRangeCondition(
        name="temperature_envelope",
        field="temperature_field",
        maximum=Quantity(320.0, "kelvin"),
    )
    array = np.array([290.0, 300.0, 310.0])
    assert condition.evaluate(array) is ValidityStatus.UNKNOWN
    assert (
        condition.explain_in({"temperature_field": array})
        is UnknownReason.UNREADABLE_SHAPE
    )
    assert condition.explain_in({}) is UnknownReason.NOT_SUPPLIED

    # The existing scalar path remains scalar as well.
    scalar = RangeCondition(name="temperature", maximum=Quantity(320.0, "kelvin"))
    assert scalar.evaluate(array) is ValidityStatus.UNKNOWN


def test_finiteness_is_a_first_class_field_condition():
    finite = FieldFiniteCondition(name="finite_temperature", field="temperature_field")
    assert finite.evaluate(_record()) is ValidityStatus.IN_DOMAIN
    assert finite.evaluate(_record(non_finite=1)) is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN


def test_nonfinite_range_is_unknown_and_can_be_gated_by_finiteness():
    field = _record(non_finite=1)
    ungated = FieldRangeCondition(
        name="temperature_envelope",
        field="temperature_field",
        maximum=Quantity(320.0, "kelvin"),
    )
    assert ungated.evaluate(field) is ValidityStatus.UNKNOWN

    domain = ValidityDomain(
        conditions=(
            FieldFiniteCondition(name="finite_temperature", field="temperature_field"),
            FieldRangeCondition(
                name="temperature_envelope",
                field="temperature_field",
                maximum=Quantity(320.0, "kelvin"),
                requires=("finite_temperature",),
            ),
        )
    )
    assessment = domain.assess({"temperature_field": field})
    assert assessment.status is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
    assert assessment.violated == ("finite_temperature",)
    assert assessment.unknown == ("temperature_envelope",)
    assert (
        assessment.reason_for("temperature_envelope")
        is UnknownReason.PREREQUISITE_NOT_ESTABLISHED
    )


def test_field_structure_checks_components_location_rank_and_support_name():
    vector = _record(components=3, location=FieldLocation.NODE)
    condition = FieldStructureCondition(
        name="vector_structure",
        field="velocity_field",
        components=3,
        spatial_rank=2,
        location=FieldLocation.NODE,
        mesh_id="plate",
        exact_shape=(3, 5, 3),
    )
    assert condition.evaluate(vector) is ValidityStatus.IN_DOMAIN
    assert (
        FieldStructureCondition(
            name="wrong_components", field="velocity_field", components=9
        ).evaluate(vector)
        is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
    )
    assert (
        FieldStructureCondition(
            name="wrong_location", field="velocity_field", location=FieldLocation.CELL
        ).evaluate(vector)
        is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
    )


def test_mesh_resolution_checks_counts_and_physical_spacing():
    mesh = _mesh()
    admitted = MeshResolutionCondition(
        name="mesh_quality",
        mesh="support",
        min_nodes_x=5,
        min_nodes_y=3,
        max_spacing_x=Quantity(0.25, "meter"),
        max_spacing_y=Quantity(250.0, "millimeter"),
    )
    too_coarse = MeshResolutionCondition(
        name="mesh_quality",
        mesh="support",
        max_spacing_x=Quantity(0.2, "meter"),
    )
    assert admitted.evaluate(mesh) is ValidityStatus.IN_DOMAIN
    assert too_coarse.evaluate(mesh) is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN


def test_several_conditions_can_target_one_field_without_context_duplication():
    field = _record()
    mesh = _mesh()
    domain = ValidityDomain(
        conditions=(
            FieldFiniteCondition(name="finite_T", field="T_field"),
            FieldRangeCondition(
                name="range_T",
                field="T_field",
                minimum=Quantity(280.0, "kelvin"),
                maximum=Quantity(320.0, "kelvin"),
                requires=("finite_T",),
            ),
            FieldStructureCondition(
                name="structure_T",
                field="T_field",
                components=1,
                spatial_rank=2,
                location=FieldLocation.NODE,
            ),
            MeshResolutionCondition(
                name="resolution",
                mesh="support",
                min_nodes_x=5,
                min_nodes_y=3,
            ),
        )
    )
    assert domain.context_keys == frozenset({"T_field", "support"})
    assessment = domain.assess({"T_field": field, "support": mesh})
    assert assessment.status is ValidityStatus.IN_DOMAIN
    assert assessment.violated == () and assessment.unknown == ()
    assert set(assessment.satisfied) == {
        "finite_T", "range_T", "structure_T", "resolution"
    }


def test_structured_conditions_survive_validity_domain_serialization():
    domain = ValidityDomain(
        conditions=(
            FieldFiniteCondition(name="finite_T", field="T_field"),
            FieldRangeCondition(
                name="range_T",
                field="T_field",
                minimum=Quantity(280.0, "kelvin"),
                maximum=Quantity(320.0, "kelvin"),
                requires=("finite_T",),
            ),
            FieldStructureCondition(
                name="structure_T", field="T_field", components=3, spatial_rank=2
            ),
            MeshResolutionCondition(
                name="resolution",
                mesh="support",
                min_nodes_x=5,
                max_spacing_y=Quantity(0.25, "meter"),
            ),
        )
    )
    restored = ValidityDomain.from_dict(domain.to_dict())
    assert restored == domain
    assert restored.context_keys == frozenset({"T_field", "support"})
