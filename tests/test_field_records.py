"""The field declaration layer: a support, regions on it, fields over it, conditions.

Sprint 4, Phase 3 and Phase 13. ``test_field_ir_ceiling.py`` shows what the
scalar IR cannot say; this is what the field records do say, and what they
refuse. Nothing here holds values: these are the O(1) declarations the control
plane carries, and the array lives behind a reference.

The theme of every refusal below is the same one: a field is values *on a
support*, so two things that differ in support are two different fields however
well their lengths line up.
"""

from __future__ import annotations

import pytest

from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.fields import (
    BoundaryEdge,
    FieldBoundaryCondition,
    FieldDefinition,
    FieldInitialCondition,
    FieldLocation,
    FieldRecord,
    FieldSummary,
    FieldTransferVerdict,
    MeshRegion,
    MeshTopology,
    StructuredMesh,
    TransferKind,
    boundary_regions,
    check_field_transfer,
    require_complete_boundary,
)
from engcore.scientific.fields.transfer import FieldTransferContract
from engcore.scientific.ir.conditions import BoundaryKind
from engcore.scientific.results.data_reference import ScientificDataReference
from engcore.scientific.units.quantity import Quantity


def mesh(mesh_id: str = "plate", nx: int = 5, ny: int = 3, lx: float = 1.0, ly: float = 0.5,
         x0: float = 0.0) -> StructuredMesh:
    return StructuredMesh(
        mesh_id=mesh_id,
        length_x=Quantity(lx, "meter"),
        length_y=Quantity(ly, "meter"),
        nodes_x=nx,
        nodes_y=ny,
        origin_x=Quantity(x0, "meter"),
    )


def temperature(mesh_id: str = "plate", **changes) -> FieldDefinition:
    return FieldDefinition(field_id="T", unit=changes.pop("unit", "K"), mesh_id=mesh_id, **changes)


# ---- the support ---------------------------------------------------------------------
def test_a_support_derives_its_spacing_counts_and_shape():
    plate = mesh()
    assert plate.dimensionality == 2
    assert plate.node_count == 15 and plate.cell_count == 8
    assert plate.node_shape == (3, 5) and plate.cell_shape == (2, 4)
    assert plate.spacing_x == Quantity(0.25, "meter")
    assert plate.spacing_y == Quantity(0.25, "meter")
    assert plate.topology is MeshTopology.STRUCTURED_RECTILINEAR
    x, y = plate.axis_coordinates()
    assert x == (0.0, 0.25, 0.5, 0.75, 1.0)
    assert y == (0.0, 0.25, 0.5)


@pytest.mark.parametrize(
    "changes, match",
    [
        ({"lx": 0.0}, "strictly positive"),
        ({"lx": -1.0}, "strictly positive"),
        ({"nx": 1}, "at least 2"),
        ({"ny": 0}, "at least 2"),
    ],
)
def test_a_support_refuses_a_geometry_that_is_not_one(changes, match):
    with pytest.raises(InvalidScientificProblem, match=match):
        mesh(**changes)


def test_a_support_refuses_counts_that_are_not_counts():
    with pytest.raises(InvalidScientificProblem, match="must be an int"):
        StructuredMesh("m", Quantity(1.0, "meter"), Quantity(1.0, "meter"), True, 4)
    with pytest.raises(InvalidScientificProblem, match="must be an int"):
        StructuredMesh("m", Quantity(1.0, "meter"), Quantity(1.0, "meter"), 4.5, 4)


def test_a_support_refuses_an_extent_that_carries_no_unit():
    with pytest.raises(InvalidScientificProblem, match="must be a Quantity"):
        StructuredMesh("m", 1.0, Quantity(1.0, "meter"), 4, 4)


def test_identity_is_the_geometry_and_the_resolution_never_the_name():
    assert mesh("a").fingerprint() == mesh("b").fingerprint(), "a name moves no node"
    assert mesh().fingerprint() != mesh(nx=9).fingerprint(), "resolution is identity"
    assert mesh().fingerprint() != mesh(lx=2.0).fingerprint(), "geometry is identity"
    assert mesh().fingerprint() != mesh(x0=1.0).fingerprint(), "where it sits is identity"
    assert mesh().same_support_as(mesh("other-name"))
    assert not mesh().same_support_as(mesh(ny=9))


def test_one_geometry_written_in_two_length_units_is_one_support():
    metric = StructuredMesh("m", Quantity(1.0, "meter"), Quantity(0.5, "meter"), 5, 3)
    millimetres = StructuredMesh("m", Quantity(1000.0, "mm"), Quantity(500.0, "mm"), 5, 3)
    assert metric.fingerprint() == millimetres.fingerprint()


def test_a_node_off_the_support_is_refused():
    with pytest.raises(InvalidScientificProblem, match="is not on mesh"):
        mesh().node_index(5, 0)


def test_a_support_round_trips_and_a_tampered_fingerprint_is_refused():
    payload = mesh().to_dict()
    assert StructuredMesh.from_dict(payload) == mesh()
    payload["nodes_x"] = 9  # the geometry now disagrees with the declared identity
    with pytest.raises(InvalidScientificProblem, match="identity was edited"):
        StructuredMesh.from_dict(payload)


# ---- regions resolve, they do not label ----------------------------------------------
def test_a_region_names_the_nodes_it_is():
    plate = mesh()
    left, right, bottom, top = boundary_regions(plate)
    assert [r.edge for r in (left, right, bottom, top)] == list(BoundaryEdge)
    assert left.node_indices(plate) == (0, 5, 10)
    assert right.node_indices(plate) == (4, 9, 14)
    assert bottom.node_indices(plate) == (0, 1, 2, 3, 4)
    assert top.node_indices(plate) == (10, 11, 12, 13, 14)
    # A corner is on both edges that meet there, and says so.
    assert set(left.node_indices(plate)) & set(bottom.node_indices(plate)) == {0}
    assert left.node_count(plate) == 3 and bottom.node_count(plate) == 5


def test_a_region_refuses_a_support_it_was_not_declared_on():
    region = MeshRegion("edge", "plate", BoundaryEdge.LEFT)
    with pytest.raises(InvalidScientificProblem, match="names no nodes of another"):
        region.node_indices(mesh("other-plate"))


def test_a_region_round_trips():
    region = boundary_regions(mesh())[0]
    assert MeshRegion.from_dict(region.to_dict()) == region


# ---- a field declares where it lives --------------------------------------------------
def test_a_field_states_shape_location_and_support():
    plate = mesh()
    nodes = temperature()
    cells = temperature(location=FieldLocation.CELL)
    vector = temperature(components=2)
    assert nodes.expected_shape(plate) == (3, 5) and nodes.expected_count(plate) == 15
    assert cells.expected_shape(plate) == (2, 4) and cells.expected_count(plate) == 8
    assert vector.expected_shape(plate) == (3, 5, 2) and vector.expected_count(plate) == 30
    assert nodes.unit == "kelvin", "one unit contract, so K and kelvin are one declaration"


def test_a_field_refuses_a_support_that_is_not_its_own():
    with pytest.raises(InvalidScientificProblem, match="is not a field of another"):
        temperature().expected_shape(mesh("other-plate"))


def test_a_field_refuses_a_component_count_that_is_not_one():
    with pytest.raises(InvalidScientificProblem, match="components must be >= 1"):
        temperature(components=0)
    with pytest.raises(InvalidScientificProblem, match="components must be an int"):
        temperature(components=True)


def test_a_field_round_trips():
    definition = temperature(location=FieldLocation.CELL, components=3)
    assert FieldDefinition.from_dict(definition.to_dict()) == definition


# ---- conditions are typed, placed and dimensioned --------------------------------------
def _dirichlet(region_id: str, kelvin: float = 300.0) -> FieldBoundaryCondition:
    return FieldBoundaryCondition(
        name=f"fixed-{region_id}", field_id="T", region_id=region_id,
        kind=BoundaryKind.DIRICHLET, value=Quantity(kelvin, "kelvin"),
    )


def test_a_dirichlet_condition_must_be_a_value_of_its_field():
    plate, region = mesh(), boundary_regions(mesh())[0]
    wrong = FieldBoundaryCondition(
        name="bad", field_id="T", region_id=region.region_id,
        kind=BoundaryKind.DIRICHLET, value=Quantity(5.0, "volt"),
    )
    # Since profiles, the dimension of a prescribed value is checked through
    # the law it becomes, so the refusal is the profile layer's rather than
    # `require_same_dimension`'s. Same fact, stated once for both spellings.
    with pytest.raises(Exception, match="the wrong law"):
        wrong.require_consistent(temperature(), region, plate)

    good = _dirichlet(region.region_id)
    good.require_consistent(temperature(), region, plate)


def test_a_neumann_condition_carries_a_flux_the_domain_dimensions():
    """The core checks it is a Quantity; what the flux must be dimensioned in
    depends on what the domain multiplies it by, exactly as the scalar IR reasons."""
    plate, region = mesh(), boundary_regions(mesh())[0]
    flux = FieldBoundaryCondition(
        name="flux", field_id="T", region_id=region.region_id,
        kind=BoundaryKind.NEUMANN, value=Quantity(250.0, "watt/meter**2"),
    )
    flux.require_consistent(temperature(), region, plate)


def test_a_valued_condition_without_a_value_is_refused():
    with pytest.raises(InvalidScientificProblem, match="prescribes a value"):
        FieldBoundaryCondition("bc", "T", "plate:left", BoundaryKind.DIRICHLET)


def test_a_robin_condition_is_its_coefficients():
    with pytest.raises(InvalidScientificProblem, match="coefficients"):
        FieldBoundaryCondition("bc", "T", "plate:left", BoundaryKind.ROBIN)
    representable = FieldBoundaryCondition(
        "bc", "T", "plate:left", BoundaryKind.ROBIN,
        coefficients={"h": Quantity(25.0, "watt/meter**2/kelvin")},
    )
    assert representable.kind is BoundaryKind.ROBIN


def test_a_condition_on_a_region_of_another_support_is_refused():
    plate = mesh()
    regions = boundary_regions(plate)
    stranger = MeshRegion("elsewhere:left", "elsewhere", BoundaryEdge.LEFT)
    with pytest.raises(InvalidScientificProblem, match="not a region of support"):
        require_complete_boundary(
            temperature(), plate, regions,
            [_dirichlet(r.region_id) for r in regions] + [_dirichlet(stranger.region_id)],
        )


def test_two_conditions_on_one_edge_are_refused():
    plate = mesh()
    regions = boundary_regions(plate)
    conditions = [_dirichlet(r.region_id) for r in regions]
    conditions.append(_dirichlet(regions[0].region_id, kelvin=400.0))
    with pytest.raises(InvalidScientificProblem, match="One edge, one condition"):
        require_complete_boundary(temperature(), plate, regions, conditions)


def test_an_edge_with_no_condition_is_refused():
    plate = mesh()
    regions = boundary_regions(plate)
    with pytest.raises(InvalidScientificProblem, match="under-determined"):
        require_complete_boundary(
            temperature(), plate, regions, [_dirichlet(r.region_id) for r in regions[:3]]
        )


def test_conditions_round_trip():
    condition = _dirichlet("plate:left")
    assert FieldBoundaryCondition.from_dict(condition.to_dict()) == condition
    robin = FieldBoundaryCondition(
        "bc", "T", "plate:left", BoundaryKind.ROBIN,
        coefficients={"h": Quantity(25.0, "watt/meter**2/kelvin")},
    )
    assert FieldBoundaryCondition.from_dict(robin.to_dict()) == robin


# ---- an initial field is a start, not a smuggled array ----------------------------------
def test_an_initial_condition_is_a_uniform_value_or_a_field_record_and_not_both():
    uniform = FieldInitialCondition("T", uniform=Quantity(300.0, "kelvin"))
    uniform.require_consistent(temperature())
    with pytest.raises(InvalidScientificProblem, match="exactly one"):
        FieldInitialCondition("T")
    with pytest.raises(Exception, match="not compatible with"):
        FieldInitialCondition("T", uniform=Quantity(5.0, "volt")).require_consistent(temperature())
    assert FieldInitialCondition.from_dict(uniform.to_dict()) == uniform


# ---- a record names its values and its support -------------------------------------------
def _record(plate: StructuredMesh | None = None, **changes) -> FieldRecord:
    plate = plate or mesh()
    definition = changes.pop("definition", temperature())
    values = [300.0] * definition.expected_count(plate)
    reference, _ = ScientificDataReference.for_values(
        "T:field", values, unit=changes.pop("unit", definition.unit)
    )
    summary = FieldSummary(
        minimum=Quantity(300.0, "kelvin"), maximum=Quantity(300.0, "kelvin"),
        mean=Quantity(300.0, "kelvin"), l2_norm=Quantity(300.0, "kelvin"),
    )
    return FieldRecord(
        definition=definition,
        mesh_fingerprint=changes.pop("fingerprint", plate.fingerprint()),
        shape=changes.pop("shape", definition.expected_shape(plate)),
        reference=reference,
        summary=summary,
    )


def test_a_record_verifies_against_the_support_it_was_solved_on():
    plate = mesh()
    record = _record(plate)
    record.verify_against(plate)
    assert record.is_finite
    with pytest.raises(InvalidScientificProblem, match="same name, different geometry"):
        record.verify_against(mesh(nx=9))


def test_a_record_whose_shape_and_count_disagree_is_refused():
    with pytest.raises(InvalidScientificProblem, match="describe two different fields"):
        _record(shape=(3, 4))


def test_a_record_whose_values_are_named_in_another_unit_is_refused():
    with pytest.raises(InvalidScientificProblem, match="is declared in"):
        _record(unit="degC")


def test_a_record_refuses_to_hold_the_array_itself():
    with pytest.raises(InvalidScientificProblem, match="ScientificDataReference"):
        FieldRecord(
            definition=temperature(),
            mesh_fingerprint=mesh().fingerprint(),
            shape=(3, 5),
            reference=[300.0] * 15,
            summary=FieldSummary(
                Quantity(1.0, "kelvin"), Quantity(1.0, "kelvin"),
                Quantity(1.0, "kelvin"), Quantity(1.0, "kelvin"),
            ),
        )


def test_a_record_round_trips():
    record = _record()
    assert FieldRecord.from_dict(record.to_dict()) == record


# ---- transfer: what must be declared before a field crosses -------------------------------
def test_the_same_field_on_the_same_support_is_compatible():
    plate = mesh()
    contract = check_field_transfer(temperature(), plate, temperature(), plate)
    assert contract.verdict is FieldTransferVerdict.COMPATIBLE
    assert contract.kind is TransferKind.FIELD_TRANSFER
    assert contract.may_cross_directly
    assert FieldTransferContract.from_dict(contract.to_dict()) == contract


@pytest.mark.parametrize(
    "consumer_kwargs, consumer_mesh_kwargs, verdict",
    [
        ({}, {"nx": 9}, FieldTransferVerdict.REQUIRES_PROJECTION),
        ({"location": FieldLocation.CELL}, {}, FieldTransferVerdict.REQUIRES_PROJECTION),
        ({"unit": "degC"}, {}, FieldTransferVerdict.REQUIRES_UNIT_CONVERSION),
        ({"unit": "volt"}, {}, FieldTransferVerdict.REFUSED),
        ({"components": 2}, {}, FieldTransferVerdict.REFUSED),
        ({}, {"lx": 2.0}, FieldTransferVerdict.REFUSED),
        ({}, {"x0": 1.0}, FieldTransferVerdict.REFUSED),
    ],
)
def test_what_stands_between_a_produced_field_and_a_consumer(
    consumer_kwargs, consumer_mesh_kwargs, verdict
):
    producer_mesh = mesh()
    consumer_mesh = mesh(**consumer_mesh_kwargs)
    contract = check_field_transfer(
        temperature(), producer_mesh, temperature(**consumer_kwargs), consumer_mesh
    )
    assert contract.verdict is verdict, contract.reason
    assert contract.may_cross_directly is (verdict is FieldTransferVerdict.COMPATIBLE)
    assert contract.reason


def test_equal_length_is_not_compatibility():
    """32x16 and 16x32 are 512 values each, and are not the same support."""
    wide = StructuredMesh("wide", Quantity(1.0, "meter"), Quantity(1.0, "meter"), 32, 16)
    tall = StructuredMesh("tall", Quantity(1.0, "meter"), Quantity(1.0, "meter"), 16, 32)
    assert wide.node_count == tall.node_count
    contract = check_field_transfer(
        FieldDefinition("T", "K", "wide"), wide, FieldDefinition("T", "K", "tall"), tall
    )
    assert contract.verdict is FieldTransferVerdict.REQUIRES_PROJECTION
