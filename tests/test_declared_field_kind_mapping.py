"""A-3 adversarial transfer probes, NOT RUN. No physical validation claim."""
from dataclasses import replace

import numpy as np
import pytest

from engcore.data import BulkDataResolver, InMemoryBulkStore
from engcore.data.field import FieldValue
from engcore.data.mesh import UnstructuredMeshData
from engcore.execution.multiphysics.mapping import FieldMapper
from engcore.execution.multiphysics.transfer import TransferEngine
from engcore.numerical.core import NumericalRefusal
from engcore.numerical.field_mapping import map_cells_1d
from engcore.numerical.mesh_adaptation import Grid1D
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.fields import CellType, FieldDefinition, FieldLocation, StructuredMesh
from engcore.scientific.fields.semantics import FieldSemantics, InterfaceConvention
from engcore.scientific.fields.transfer import FieldTransferContract, FieldTransferVerdict, TransferKind, check_field_transfer
from engcore.scientific.multiphysics import CouplingEdge, FieldMappingDefinition, ParticipantSpec, PhysicsGraph, PortDefinition, PortRef
from engcore.scientific.results.uncertainty import UncertaintyKind, Uncertainty
from engcore.scientific.semantics import ConservedQuantity, QuantityRole, QuantitySemantics
from engcore.scientific.units.quantity import Quantity


def semantics(kind="cell_integrated", dimension=1):
    cq = ConservedQuantity("fixture:species_A.amount", "kg")
    if kind == "cell_integrated":
        q = QuantitySemantics("fixture:species_A.amount", "kg", (QuantityRole.INTEGRATED,), cq)
    elif kind == "cell_average_density":
        q = QuantitySemantics("fixture:species_A.density", f"kg/m**{dimension}", (QuantityRole.DENSITY,))
    else:
        q = QuantitySemantics("fixture:temperature", "K", (QuantityRole.INTENSIVE,))
        return FieldSemantics("intensive", q)
    return FieldSemantics(kind, q, f"m**{dimension}", cq)


def mapped(values=(2, 6), source=None, target=None, sem=None, **kwargs):
    source = source or Grid1D((0, 1, 4), "m")
    target = target or Grid1D((0, 2, 4), "m")
    sem = sem or semantics()
    arguments = dict(source_semantics=sem, target_semantics=sem, source_unit=sem.quantity.unit,
                     target_unit=sem.quantity.unit, source_fingerprint=source.digest,
                     target_fingerprint=target.digest, coordinate_frame="fixture:common_axis")
    arguments.update(kwargs)
    return map_cells_1d(values, source, target, **arguments)


def test_integrated_counterexample_is_four_four_and_total_eight():
    result = mapped()
    assert result.values == pytest.approx((4, 4))
    assert sum(result.values) == pytest.approx(8)
    assert result.values != pytest.approx((4, 6))
    assert result.diagnostics.provenance["source_total"] == pytest.approx(8)
    assert result.diagnostics.provenance["target_total"] == pytest.approx(8)
    assert result.uncertainty.kind is UncertaintyKind.UNKNOWN


def test_same_raw_numbers_with_declared_density_are_a_different_physical_field():
    result = mapped(sem=semantics("cell_average_density"))
    assert result.values == pytest.approx((4, 6))
    assert result.diagnostics.provenance["source_total"] == pytest.approx(20)
    assert result.diagnostics.provenance["target_total"] == pytest.approx(20)


def test_unequal_cell_nonconstant_density_and_integrated_amount_agree_only_after_explicit_conversion():
    # Amounts (1,9) on widths (1,3) represent densities (1,3).
    a = mapped((1, 9))
    rho = mapped((1, 3), sem=semantics("cell_average_density"))
    assert a.values == pytest.approx((4, 6))
    assert rho.values == pytest.approx((2, 3))
    assert a.values == pytest.approx(tuple(2*x for x in rho.values))
    with pytest.raises(InvalidScientificProblem, match="kinds or measures differ"):
        mapped(target_semantics=semantics("cell_average_density"))


def test_refinement_coarsening_and_reverse_preserve_integrated_amount():
    coarse = Grid1D((0, 1, 4), "m")
    fine = Grid1D((0, .5, 1, 2, 4), "m")
    refined = mapped(source=coarse, target=fine)
    assert refined.values == pytest.approx((1, 1, 2, 4))
    coarsened = mapped(refined.values, source=fine, target=coarse)
    assert coarsened.values == pytest.approx((2, 6))
    assert sum(refined.values) == pytest.approx(sum(coarsened.values))


def test_signed_zero_total_uses_l1_scale_without_fake_zero_uncertainty():
    result = mapped((2, -2))
    assert sum(result.values) == pytest.approx(0, abs=1e-12)
    assert result.diagnostics.provenance["scale_l1"] == pytest.approx(4)
    assert result.diagnostics.conservation_relative_error == pytest.approx(0, abs=1e-12)
    assert result.uncertainty.kind is UncertaintyKind.UNKNOWN


@pytest.mark.parametrize("source,target", [((0, 1, 3), (0, 2, 4)), ((0, 1, 4), (0, 2, 3))])
def test_partial_coverage_in_either_direction_never_extrapolates_or_drops(source, target):
    with pytest.raises(InvalidScientificProblem, match="partial coverage"):
        mapped(source=Grid1D(source, "m"), target=Grid1D(target, "m"))


def test_reversed_axis_is_refused_instead_of_implicitly_flipping_sign():
    with pytest.raises(NumericalRefusal, match="strictly increasing"):
        Grid1D((4, 1, 0), "m")


def test_units_and_canonical_geometry_are_explicit():
    result = mapped((2000, 6000), source=Grid1D((0, 100, 400), "cm"), source_unit="g", target_unit="kg")
    assert result.values == pytest.approx((4, 4))
    assert result.diagnostics.provenance["target_total"] == pytest.approx(8)
    with pytest.raises(InvalidScientificProblem, match="value units"):
        mapped(source_unit="J")
    with pytest.raises(InvalidScientificProblem, match="length units"):
        mapped(source=Grid1D((0, 1, 4), "s"))
    with pytest.raises(InvalidScientificProblem, match="support dimension"):
        mapped(sem=semantics(dimension=2))


def test_intensive_overlap_average_has_no_conservation_claim():
    result = mapped((300, 400), sem=semantics("intensive"))
    assert result.values == pytest.approx((350, 400))
    assert result.diagnostics.conservation_relative_error is None
    assert "source_total" not in result.diagnostics.provenance


def test_stale_support_and_unsupported_kind_are_refused():
    with pytest.raises(InvalidScientificProblem, match="stale"):
        mapped(source_fingerprint="0"*64)
    with pytest.raises(InvalidScientificProblem, match="stale"):
        mapped(target_fingerprint="0"*64)
    with pytest.raises(ValueError):
        replace(semantics(), kind="deduce_from_units")
    with pytest.raises(InvalidScientificProblem, match="declared field kind"):
        mapped(source_semantics=None)


@pytest.mark.parametrize("kind", ["normal_flux", "interface"])
@pytest.mark.parametrize("orientation", [-1, 1])
def test_interface_and_flux_conventions_are_structured_but_execution_requires_a4(kind, orientation):
    grid = Grid1D((0, 1, 4), "m")
    convention = InterfaceConvention("face-set", grid.digest, "fixture:axis", orientation, (1.0,))
    q = QuantitySemantics("fixture:flux", "kg/s", (QuantityRole.FLOW,))
    sem = FieldSemantics(kind, q, interface=convention)
    assert FieldSemantics.from_dict(sem.to_dict()) == sem
    with pytest.raises(InvalidScientificProblem, match="A-4"):
        mapped(sem=sem)
    with pytest.raises(InvalidScientificProblem, match="normal and support"):
        FieldSemantics(kind, q)


def test_invalid_normal_orientation_and_support_declarations_refuse():
    for orientation, normal in ((0, (1,)), (True, (1,)), (1, (0,)), (1, (2,))):
        with pytest.raises(InvalidScientificProblem):
            InterfaceConvention("faces", "0"*64, "fixture:axis", orientation, normal)


def meshes(store):
    # Unequal source cell areas 1 and 3; target areas 2 and 2.
    source = UnstructuredMeshData("source", CellType.QUADRILATERAL,
        np.array([[0, 0], [1, 0], [4, 0], [0, 1], [1, 1], [4, 1]], float),
        np.array([[0, 1, 4, 3], [1, 2, 5, 4]])).store(store)
    target = StructuredMesh("target", Quantity(4, "m"), Quantity(1, "m"), 3, 2)
    return source, target


@pytest.mark.parametrize("source_unit,values", [("kg", (2, 6)), ("g", (2000, 6000))])
def test_authoritative_fieldmapper_uses_integrated_operator_on_unequal_areas(source_unit, values):
    store = InMemoryBulkStore()
    source, target = meshes(store)
    sem = semantics(dimension=2)
    a = FieldDefinition("amount", source_unit, source.mesh_id, FieldLocation.CELL, semantics=sem)
    b = FieldDefinition("amount", "kg", target.mesh_id, FieldLocation.CELL, semantics=sem)
    record, _ = FieldValue(a, source, np.array(values, float)).store(store)
    mapper = FieldMapper(BulkDataResolver(store), store)
    result = mapper.execute(record, source, b, target, FieldMappingDefinition("map", "conservative_cell"))
    values = FieldValue.from_record(result.record, target, BulkDataResolver(store)).values
    assert values.reshape(-1) == pytest.approx((4, 4))
    assert result.diagnostics.provenance["source_total"] == pytest.approx([8])
    assert result.diagnostics.provenance["target_total"] == pytest.approx([8])
    assert result.record.definition.semantics == sem


def test_authoritative_density_unit_conversion_preserves_amount_units():
    store = InMemoryBulkStore()
    source, target = meshes(store)
    sem = semantics("cell_average_density", dimension=2)
    a = FieldDefinition("density", "g/cm**2", source.mesh_id, FieldLocation.CELL, semantics=sem)
    b = FieldDefinition("density", "kg/m**2", target.mesh_id, FieldLocation.CELL, semantics=sem)
    record, _ = FieldValue(a, source, np.array([.2, .2])).store(store)  # 2 kg/m2
    result = FieldMapper(BulkDataResolver(store), store).execute(record, source, b, target,
        FieldMappingDefinition("map", "conservative_cell"))
    values = FieldValue.from_record(result.record, target, BulkDataResolver(store)).values
    assert values.reshape(-1) == pytest.approx((2, 2))
    assert result.diagnostics.provenance["source_total"] == pytest.approx([8])
    assert result.diagnostics.provenance["conservation_unit"] == sem.conserved_quantity.unit


def field_graph(source, target, a, b):
    def participant(pid, field, direction):
        port = PortDefinition("q", direction, "field", "declared", field.unit, field,
                              semantics=field.semantics.quantity)
        return ParticipantSpec(pid, "fixture", "1", "fixture", "1", "fixture", "1", "fixture", "1", (port,))
    edge = CouplingEdge("e", PortRef("a", "q"), PortRef("b", "q"),
                        mapping=FieldMappingDefinition("map", "conservative_cell"))
    return PhysicsGraph("field", (participant("a", a, "output"), participant("b", b, "input")),
                        (edge,), supports=(source, target))


def test_typed_energy_field_graph_uses_meaning_and_kind_without_energy_prose():
    store = InMemoryBulkStore()
    source, target = meshes(store)
    cq = ConservedQuantity("fixture:energy", "J")
    q = QuantitySemantics("fixture:energy", "J", (QuantityRole.INTEGRATED,), cq)
    sem = FieldSemantics("cell_integrated", q, "m**2", cq)
    a = FieldDefinition("energy", "J", source.mesh_id, FieldLocation.CELL, semantics=sem)
    b = FieldDefinition("energy", "J", target.mesh_id, FieldLocation.CELL, semantics=sem)
    graph = field_graph(source, target, a, b)
    assert not graph.edge("e").transport_declaration
    assert PhysicsGraph.from_dict(graph.to_dict()).fingerprint() == graph.fingerprint()
    changed = replace(q, meaning_id="fixture:other_energy")
    changed_sem = replace(sem, quantity=changed)
    altered = field_graph(source, target, replace(a, semantics=changed_sem), replace(b, semantics=changed_sem))
    assert altered.fingerprint() != graph.fingerprint()


def test_transfer_refuses_same_shape_units_record_substituted_for_declared_source():
    store = InMemoryBulkStore()
    source, target = meshes(store)
    sem = semantics(dimension=2)
    a = FieldDefinition("amount", "kg", source.mesh_id, FieldLocation.CELL, semantics=sem)
    b = FieldDefinition("amount", "kg", target.mesh_id, FieldLocation.CELL, semantics=sem)
    graph = field_graph(source, target, a, b)
    record, _ = FieldValue(replace(a, field_id="substituted"), source, np.array([2., 6.])).store(store)
    engine = TransferEngine(graph, resolver=BulkDataResolver(store), store=store)
    with pytest.raises(InvalidScientificProblem, match="declared source port"):
        engine.transfer(graph.edge("e"), record, Uncertainty.unknown("fixture"), instant="0 s")


def test_legacy_conservative_and_mixed_typing_refuse_without_automatic_migration():
    store = InMemoryBulkStore()
    source, target = meshes(store)
    legacy = FieldDefinition("amount", "kg", source.mesh_id, FieldLocation.CELL)
    record, _ = FieldValue(legacy, source, np.array([2., 6.])).store(store)
    mapper = FieldMapper(BulkDataResolver(store), store)
    mapping = FieldMappingDefinition("map", "conservative_cell")
    b = FieldDefinition("amount", "kg", target.mesh_id, FieldLocation.CELL)
    with pytest.raises(InvalidScientificProblem, match="legacy migration"):
        mapper.execute(record, source, b, target, mapping)
    with pytest.raises(InvalidScientificProblem, match="mixed typed/untyped"):
        mapper.execute(record, source, replace(b, semantics=semantics(dimension=2)), target, mapping)


def test_definition_schema_and_unit_conversion_preserve_semantic_identity():
    mesh = StructuredMesh("mesh", Quantity(1, "m"), Quantity(1, "m"), 3, 2)
    field = FieldDefinition("amount", "kg", "mesh", FieldLocation.CELL, semantics=semantics(dimension=2))
    payload = field.to_dict()
    assert payload["schema"] == "field_definition/2"
    assert FieldDefinition.from_dict(payload) == field
    for bad in ({**payload, "schema": "field_definition/1"}, {k: v for k, v in payload.items() if k != "semantics"}):
        with pytest.raises(InvalidScientificProblem):
            FieldDefinition.from_dict(bad)
    legacy = replace(field, semantics=None)
    assert legacy.to_dict()["schema"] == "field_definition/1" and "semantics" not in legacy.to_dict()
    converted = FieldValue(field, mesh, np.array([[2., 6.]])).to_unit("g")
    assert converted.definition.semantics == field.semantics
    assert converted.values.reshape(-1) == pytest.approx((2000, 6000))
    with pytest.raises(InvalidScientificProblem, match="ratio scale|length, area or volume"):
        replace(semantics(dimension=2), measure_unit="s")


def test_contract_cannot_bless_kind_substitution_or_mixed_typing():
    mesh = StructuredMesh("mesh", Quantity(1, "m"), Quantity(1, "m"), 3, 2)
    a = FieldDefinition("amount", "kg", "mesh", FieldLocation.CELL, semantics=semantics(dimension=2))
    b = replace(a, semantics=None)
    assert check_field_transfer(a, mesh, b, mesh).verdict is FieldTransferVerdict.REFUSED
    with pytest.raises(InvalidScientificProblem, match="permit no more"):
        FieldTransferContract(a, mesh.fingerprint(), b, mesh.fingerprint(), TransferKind.FIELD_TRANSFER,
                              FieldTransferVerdict.COMPATIBLE, "caller says safe")


@pytest.mark.parametrize("target_length", [3, 5])
def test_authoritative_mapper_refuses_partial_coverage_both_directions(target_length):
    store = InMemoryBulkStore()
    source, _ = meshes(store)
    target = StructuredMesh("target", Quantity(target_length, "m"), Quantity(1, "m"), 3, 2)
    sem = semantics(dimension=2)
    a = FieldDefinition("amount", "kg", source.mesh_id, FieldLocation.CELL, semantics=sem)
    b = FieldDefinition("amount", "kg", target.mesh_id, FieldLocation.CELL, semantics=sem)
    record, _ = FieldValue(a, source, np.array([2., 6.])).store(store)
    with pytest.raises(InvalidScientificProblem, match="extrapolate|partly outside"):
        FieldMapper(BulkDataResolver(store), store).execute(record, source, b, target,
            FieldMappingDefinition("map", "conservative_cell"))


def test_interface_identity_copy_is_not_an_a4_execution_escape():
    store = InMemoryBulkStore()
    mesh = StructuredMesh("mesh", Quantity(1, "m"), Quantity(1, "m"), 3, 2)
    convention = InterfaceConvention("mesh", mesh.fingerprint(), "fixture:plane", -1, (1, 0))
    q = QuantitySemantics("fixture:normal_flux", "kg/s", (QuantityRole.FLOW,))
    sem = FieldSemantics("normal_flux", q, interface=convention)
    definition = FieldDefinition("flux", "kg/s", "mesh", FieldLocation.CELL, semantics=sem)
    record, _ = FieldValue(definition, mesh, np.array([[2., 6.]])).store(store)
    with pytest.raises(InvalidScientificProblem, match="A-4"):
        FieldMapper(BulkDataResolver(store), store).execute(record, mesh, definition, mesh,
            FieldMappingDefinition("identity", "identity"))
    changed_mesh = replace(mesh, length_x=Quantity(2, "m"))
    with pytest.raises(InvalidScientificProblem, match="support identity"):
        definition.require_support(changed_mesh)


def test_offset_conserved_unit_and_wrong_location_refuse():
    cq = ConservedQuantity("fixture:absolute_quantity", "K")
    q = QuantitySemantics("fixture:absolute_quantity", "K", (QuantityRole.INTEGRATED,), cq)
    sem = FieldSemantics("cell_integrated", q, "m**2", cq)
    with pytest.raises(InvalidScientificProblem, match="ratio-scale"):
        FieldDefinition("bad", "degC", "mesh", FieldLocation.CELL, semantics=sem)
    with pytest.raises(InvalidScientificProblem, match="CELL location"):
        FieldDefinition("bad", "K", "mesh", FieldLocation.NODE, semantics=sem)


def test_intensive_affine_conversion_is_an_average_not_energy_conservation():
    result = mapped((0, 100), sem=semantics("intensive"), source_unit="degC", target_unit="K")
    assert result.values == pytest.approx((323.15, 373.15))
    assert result.diagnostics.conservation_relative_error is None


def test_declared_integrated_tetrahedra_with_unequal_volumes_map_as_amounts():
    store = InMemoryBulkStore()
    # Disjoint tetrahedra of volumes 1/6 and 1/3. Target reverses their ordering.
    coordinates = np.array([[0,0,0], [1,0,0], [0,1,0], [0,0,1],
                            [3,0,0], [5,0,0], [3,1,0], [3,0,1]], float)
    cells = np.array([[0,1,2,3], [4,5,6,7]])
    source = UnstructuredMeshData("source", CellType.TETRAHEDRON, coordinates, cells).store(store)
    target = UnstructuredMeshData("target", CellType.TETRAHEDRON, coordinates, cells[::-1]).store(store)
    sem = semantics(dimension=3)
    a = FieldDefinition("amount", "kg", source.mesh_id, FieldLocation.CELL, semantics=sem)
    b = FieldDefinition("amount", "kg", target.mesh_id, FieldLocation.CELL, semantics=sem)
    record, _ = FieldValue(a, source, np.array([2., 6.])).store(store)
    result = FieldMapper(BulkDataResolver(store), store).execute(record, source, b, target,
        FieldMappingDefinition("map", "conservative_cell"))
    values = FieldValue.from_record(result.record, target, BulkDataResolver(store)).values
    assert values == pytest.approx((6, 2))
    assert result.diagnostics.provenance["target_total"] == pytest.approx([8])
