"""A-4 design probes: no providers, tests NOT RUN, no physical validation claim."""
from dataclasses import replace

import numpy as np
import pytest

from engcore.data import BulkDataResolver, InMemoryBulkStore
from engcore.data.field import FieldValue
from engcore.execution.multiphysics import TransferEngine
from engcore.execution.multiphysics.mapping import FieldMapper
from engcore.execution.multiphysics.conjugate_interface import ConjugateHeatTransferInterface, admit_conjugate_interface
from engcore.execution.multiphysics.interface_exchange import admit_dirichlet_neumann_interface, InterfaceContract, InterfaceExchange
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.fields import FieldDefinition, FieldLocation, StructuredMesh, CellType
from engcore.data.mesh import UnstructuredMeshData
from engcore.scientific.fields.interface_transfer import InterfaceTransfer
from engcore.scientific.fields.semantics import FieldSemantics, InterfaceConvention
from engcore.scientific.multiphysics import (
    CouplingEdge, CouplingPlan, ParticipantSpec, PhysicsGraph, PortDefinition, PortRef,
    FieldMappingDefinition, TimePolicy,
)
from engcore.scientific.results.uncertainty import Uncertainty, UncertaintyKind
from engcore.scientific.semantics import ConservedQuantity, QuantityRole, QuantitySemantics
from engcore.scientific.units.quantity import Quantity


def fixture(*, unit="W/m**2", amount_unit="W", meaning="fixture:heat_flux", representation="normal_density",
            normal=(0, 0, -1), orientations=(1, 1), relation="equal_and_opposite_outward", target_length=4):
    a = StructuredMesh("a", Quantity(4, "m"), Quantity(1, "m"), 3, 2)  # cell areas 2,2
    b = StructuredMesh("b", Quantity(target_length, "m"), Quantity(1, "m"), 4, 2)  # areas 4/3 each
    source = InterfaceConvention("a", a.fingerprint(), "fixture:world", orientations[0], (0, 0, 1))
    target = InterfaceConvention("b", b.fingerprint(), "fixture:world", orientations[1], normal)
    cq = ConservedQuantity("fixture:conserved_transfer", amount_unit)
    density = representation == "normal_density"
    q = QuantitySemantics(meaning, unit, (QuantityRole.DENSITY, QuantityRole.FLOW) if density else (QuantityRole.INTEGRATED,),
                          None if density else cq)
    transfer = InterfaceTransfer(source, target, q, cq, representation, relation, "full", "common_plane_rectangles",
                                 (0, 0, 0), (1, 0, 0), (0, 1, 0))
    kind = "normal_flux" if density else "interface"
    fa = FieldDefinition("q", unit, "a", FieldLocation.CELL, semantics=FieldSemantics(kind, q, interface=source))
    fb = FieldDefinition("q", unit, "b", FieldLocation.CELL, semantics=FieldSemantics(kind, q, interface=target))
    return a, b, fa, fb, transfer


def graph_for(a, b, fa, fb, transfer, *, temperature=True, intensive=None):
    intensive = intensive or QuantitySemantics("fixture:temperature", "K", (QuantityRole.INTENSIVE,))
    state = FieldSemantics("intensive", intensive)
    ta = FieldDefinition("t", intensive.unit, "a", FieldLocation.CELL, semantics=state)
    tb = FieldDefinition("t", intensive.unit, "b", FieldLocation.CELL, semantics=state)
    def port(name, direction, field):
        return PortDefinition(name, direction, "field", "declared", field.unit, field, semantics=field.semantics.quantity)
    def spec(name, ports):
        return ParticipantSpec(name, "fixture", "1", "fixture", "1", "fixture", "1", "fixture", "1", tuple(ports))
    a_ports, b_ports = [port("q", "output", fa)], [port("q", "input", fb)]
    edges = [CouplingEdge("flux", PortRef("a", "q"), PortRef("b", "q"),
                         mapping=FieldMappingDefinition("interface", "conservative_cell"), interface_transfer=transfer)]
    if temperature:
        a_ports.append(port("t", "input", ta))
        b_ports.append(port("t", "output", tb))
        edges.append(CouplingEdge("state", PortRef("b", "t"), PortRef("a", "t"),
                                 mapping=FieldMappingDefinition("state", "conservative_cell")))
    return PhysicsGraph("interface", (spec("a", a_ports), spec("b", b_ports)), tuple(edges), supports=(a, b)), intensive


def execute(parts, values=(2, 6), *, graph_path=False, source_unit=None, mapping=None, intensive=None):
    a, b, fa, fb, transfer = parts
    if source_unit is not None:
        fa = replace(fa, unit=source_unit)
    store = InMemoryBulkStore()
    record, _ = FieldValue(fa, a, np.asarray([values], float)).store(store)
    mapping = mapping or FieldMappingDefinition("interface", "conservative_cell")
    if graph_path:
        graph, _ = graph_for(a, b, fa, fb, transfer, intensive=intensive)
        if mapping != graph.edge("flux").mapping:
            graph = replace(graph, edges=tuple(replace(e, mapping=mapping) if e.edge_id == "flux" else e for e in graph.edges))
        result = TransferEngine(graph, resolver=BulkDataResolver(store), store=store).transfer(
            graph.edge("flux"), record, Uncertainty.unknown("unqualified fixture"), instant="0 s")
        assert result.uncertainty.kind is UncertaintyKind.UNKNOWN
        out, diagnostics = result.value, result.mapping
    else:
        result = FieldMapper(BulkDataResolver(store), store).execute(record, a, fb, b,
            mapping, interface_transfer=transfer)
        out, diagnostics = result.record, result.diagnostics
    return FieldValue.from_record(out, b, BulkDataResolver(store)).values.reshape(-1), diagnostics


@pytest.mark.parametrize("graph_path", [False, True])
def test_opposing_normals_are_executed_and_integral_is_equal_and_opposite(graph_path):
    values, diag = execute(fixture(), graph_path=graph_path)
    assert values == pytest.approx((-2, -4, -6))
    p = diag.provenance
    assert p["applied_sign"] == -1
    assert p["source_total_normal_component"] == pytest.approx(16)
    assert p["target_total_normal_component"] == pytest.approx(-16)
    assert p["oriented_integral_absolute_residual"] == pytest.approx(0, abs=1e-12)
    assert p["source_total_normal_component"] + p["target_total_normal_component"] == pytest.approx(0, abs=1e-12)
    assert p["coupled_physical_conservation"].startswith("unknown")
    assert p["experimental_validation"] == "not established"
    # Ignoring the sign would leave a nonzero outward sum despite zero remap residual.
    assert 16 + sum(-values)*4/3 == pytest.approx(32)


@pytest.mark.parametrize("normal,orientations,expected", [
    ((0,0,1), (1,1), (2,4,6)), ((0,0,-1), (1,1), (-2,-4,-6)),
    ((0,0,-1), (1,-1), (2,4,6)), ((0,0,1), (-1,1), (-2,-4,-6)),
])
def test_same_or_reversed_direction_normals_and_explicit_orientation(normal, orientations, expected):
    values, _ = execute(fixture(normal=normal, orientations=orientations, relation="continuous_oriented_flux"))
    assert values == pytest.approx(expected)


def test_the_oriented_integral_residual_is_not_an_orientation_check():
    """Pinned limitation (2026-10-18 remediation C3-1), not a property to rely on.

    Two declarations that differ only in the target orientation execute OPPOSITE fields ((-2,-4,-6) vs (2,4,6),
    the expectations of the parametrized test above), and both report a zero ``oriented_integral_absolute_residual``:
    the residual re-applies the contract's own sign, so it equals the unsigned remap residual and cannot detect a
    wrong declared normal or orientation. Only the receiver's own boundary flux could; until that exists the record
    must keep saying it is a constructed diagnostic.
    """
    plus, plus_diag = execute(fixture(normal=(0, 0, -1), orientations=(1, 1), relation="continuous_oriented_flux"))
    minus, minus_diag = execute(fixture(normal=(0, 0, -1), orientations=(1, -1), relation="continuous_oriented_flux"))
    assert plus == pytest.approx((-2, -4, -6)) and minus == pytest.approx((2, 4, 6))
    for diag in (plus_diag, minus_diag):
        assert diag.provenance["oriented_integral_absolute_residual"] == pytest.approx(0, abs=1e-12)
        assert diag.provenance["notice"].startswith("constructed transfer integral diagnostic")
        assert diag.provenance["coupled_physical_conservation"].startswith("unknown")


def test_same_direction_normals_cannot_claim_equal_and_opposite_outward():
    with pytest.raises(InvalidScientificProblem, match="opposing normals"):
        fixture(normal=(0,0,1))


@pytest.mark.parametrize("graph_path", [False, True])
def test_integrated_surface_amount_uses_source_area_and_not_density_formula(graph_path):
    parts = fixture(unit="W", representation="integrated")
    values, diag = execute(parts, graph_path=graph_path)
    assert values == pytest.approx((-4/3, -8/3, -4))
    assert sum(values) == pytest.approx(-8)
    assert values != pytest.approx((-2, -4, -6))
    assert diag.provenance["source_total_stored_convention"] == pytest.approx(8)
    graph, intensive = graph_for(*parts)
    admission = admit_dirichlet_neumann_interface("integrated", "state", "flux", intensive,
                                                  parts[-1].quantity, graph, plan())
    assert admission.receiver_flux_sign == -1


@pytest.mark.parametrize("length", [3, 5])
def test_partial_interface_coverage_refuses_both_directions(length):
    with pytest.raises(InvalidScientificProblem, match="partial interface coverage"):
        execute(fixture(target_length=length))


def test_missing_normal_orientation_and_oblique_projection_refuse():
    parts = fixture()
    transfer = parts[-1]
    with pytest.raises(InvalidScientificProblem, match="normal and orientation"):
        replace(transfer, source=None)
    with pytest.raises(TypeError):
        InterfaceConvention("a", parts[0].fingerprint(), "world", normal=(0,0,1))
    with pytest.raises(InvalidScientificProblem, match="orientation"):
        replace(transfer.source, orientation=0)
    with pytest.raises(InvalidScientificProblem, match="oblique"):
        replace(transfer, target=replace(transfer.target, normal=(1,0,0)))
    with pytest.raises(InvalidScientificProblem, match="frame projection"):
        replace(transfer, target=replace(transfer.target, coordinate_frame="other"))


def test_unsupported_geometry_vector_representation_and_method_refuse():
    a, b, fa, fb, transfer = fixture()
    store = InMemoryBulkStore()
    mesh = UnstructuredMeshData("a", CellType.TRIANGLE,
        np.array([[0.,0.],[1.,0.],[0.,1.]]), np.array([[0,1,2]])).store(store)
    with pytest.raises(InvalidScientificProblem, match="structured planar rectangles"):
        transfer.admit(fa, mesh, fb, b, FieldMappingDefinition("m", "conservative_cell"))
    with pytest.raises(InvalidScientificProblem, match="scalar normal"):
        transfer.admit(replace(fa, components=3), a, fb, b, FieldMappingDefinition("m", "conservative_cell"))
    with pytest.raises(InvalidScientificProblem, match="full-coverage"):
        transfer.admit(fa, a, fb, b, FieldMappingDefinition("m", "nearest"))
    with pytest.raises(ValueError):
        replace(transfer, coverage="silently_extrapolate")


def test_unqualified_direct_mapper_escape_and_stale_support_refuse():
    a, b, fa, fb, transfer = fixture()
    store = InMemoryBulkStore()
    record, _ = FieldValue(fa, a, np.array([[2.,6.]])).store(store)
    with pytest.raises(InvalidScientificProblem, match="A-4"):
        FieldMapper(BulkDataResolver(store), store).execute(record, a, fb, b, FieldMappingDefinition("m", "conservative_cell"))
    with pytest.raises(InvalidScientificProblem, match="support identity"):
        transfer.admit(fa, a, fb, replace(b, length_x=Quantity(5,"m")), FieldMappingDefinition("m", "conservative_cell"))


def test_same_dimension_different_meaning_and_units_refuse():
    a, b, fa, fb, transfer = fixture()
    wrong = replace(fb.semantics.quantity, meaning_id="fixture:unrelated_surface_quantity")
    with pytest.raises(InvalidScientificProblem, match="meaning, kind or convention"):
        transfer.admit(fa, a, replace(fb, semantics=replace(fb.semantics, quantity=wrong)), b,
                       FieldMappingDefinition("m", "conservative_cell"))
    with pytest.raises(InvalidScientificProblem, match="dimensions disagree"):
        replace(transfer, conserved_quantity=ConservedQuantity("fixture:charge", "C"))
    with pytest.raises(InvalidScientificProblem, match="dimension"):
        replace(fb, unit="kg")


def test_surface_support_identity_is_material_and_schema_cannot_downgrade():
    parts = fixture()
    graph, _ = graph_for(*parts)
    edge = graph.edge("flux")
    payload = edge.to_dict()
    assert payload["schema"] == "multiphysics_coupling_edge/3"
    assert CouplingEdge.from_dict(payload) == edge
    assert InterfaceTransfer.from_dict(parts[-1].to_dict()) == parts[-1]
    assert PhysicsGraph.from_dict(graph.to_dict()).fingerprint() == graph.fingerprint()
    for schema in ("multiphysics_coupling_edge/1", "multiphysics_coupling_edge/2"):
        with pytest.raises(InvalidScientificProblem, match="explicit edge /3"):
            CouplingEdge.from_dict({**payload, "schema": schema})
    with pytest.raises(InvalidScientificProblem, match="requires interface_transfer"):
        CouplingEdge.from_dict({k:v for k,v in payload.items() if k != "interface_transfer"})
    changed = (*parts[:-1], replace(parts[-1], plane_origin_m=(0,0,1)))
    altered, _ = graph_for(*changed)
    assert altered.fingerprint() != graph.fingerprint()


def plan():
    return CouplingPlan("fixture", "explicit", "serial",
        TimePolicy(Quantity(0,"s"), Quantity(1,"s"), Quantity(1,"s")), ("a","b"))


def test_thermal_cht_is_instance_of_neutral_executed_contract():
    parts = fixture()
    graph, temperature = graph_for(*parts)
    interface = ConjugateHeatTransferInterface("wall", "a", "b", "state", "flux", "outward_normal_of:a")
    admission = admit_conjugate_interface(interface, graph, plan(), temperature_semantics=temperature,
                                          heat_flux_semantics=parts[-1].quantity)
    assert admission.receiver_flux_sign == -1
    assert admission.to_dict()["execution"]["graph_fingerprint"] == graph.fingerprint()
    assert "already applies sign" in admission.to_dict()["conditions"]["heat_flux_balance"]
    with pytest.raises(InvalidScientificProblem, match="legacy migration"):
        admit_conjugate_interface(interface, graph, plan())


def test_nonthermal_charge_flux_uses_same_execution_without_thermal_assumptions():
    parts = fixture(unit="A/m**2", amount_unit="A", meaning="fixture:charge_flux")
    potential = QuantitySemantics("fixture:electric_potential", "V", (QuantityRole.POTENTIAL, QuantityRole.INTENSIVE))
    graph, intensive = graph_for(*parts, intensive=potential)
    admission = admit_dirichlet_neumann_interface("charge-interface", "state", "flux", intensive,
                                                  parts[-1].quantity, graph, plan())
    values, diag = execute(parts, graph_path=True, intensive=potential)
    assert values == pytest.approx((-2,-4,-6))
    assert admission.receiver_flux_sign == -1
    assert diag.provenance["conservation_unit"] == parts[-1].conserved_quantity.unit


@pytest.mark.parametrize("graph_path", [False, True])
def test_roundtrip_limit_is_enforced_after_interface_remapping(graph_path):
    mapping = FieldMappingDefinition("limited", "conservative_cell", verify_round_trip=True, relative_error_limit=0)
    with pytest.raises(InvalidScientificProblem, match="round-trip error"):
        execute(fixture(), graph_path=graph_path, mapping=mapping)
    values, diag = execute(fixture(), graph_path=graph_path)
    assert diag.round_trip_relative_l2 > 0
    assert values == pytest.approx((-2,-4,-6))


def test_disabled_roundtrip_cannot_silently_ignore_requested_limit():
    with pytest.raises(InvalidScientificProblem, match="requires roundtrip"):
        execute(fixture(), mapping=FieldMappingDefinition("bad", "conservative_cell", verify_round_trip=False,
                                                         relative_error_limit=0))


def test_successful_density_unit_scaling_is_applied_before_integral_diagnostic():
    values, diag = execute(fixture(), values=(.002, .006), source_unit="kW/m**2", graph_path=True)
    assert values == pytest.approx((-2,-4,-6))
    assert diag.provenance["source_total_stored_convention"] == pytest.approx(16)


def test_identity_mapping_still_applies_opposed_normal_sign():
    a, _, fa, fb, transfer = fixture()
    target = replace(transfer.target, support_id="a", support_fingerprint=a.fingerprint())
    transfer = replace(transfer, target=target)
    fb = replace(fb, mesh_id="a", semantics=replace(fb.semantics, interface=target))
    store = InMemoryBulkStore()
    record, _ = FieldValue(fa, a, np.array([[2.,6.]])).store(store)
    result = FieldMapper(BulkDataResolver(store), store).execute(record, a, fb, a,
        FieldMappingDefinition("same", "identity"), interface_transfer=transfer)
    values = FieldValue.from_record(result.record, a, BulkDataResolver(store)).values
    assert values.reshape(-1) == pytest.approx((-2,-6))


def test_legacy_prose_interface_cannot_authorize_a_typed_execution():
    graph, _ = graph_for(*fixture())
    contract = InterfaceContract("old", (InterfaceExchange("flux", "flux_density", "outward_normal_of:a"),), two_way=False)
    with pytest.raises(InvalidScientificProblem, match="typed migration"):
        contract.check(graph)


def test_same_quantity_with_wrong_field_kind_cannot_bypass_interface_admission():
    a, b, fa, fb, transfer = fixture()
    # Keep the quantity declaration unchanged: only the field-kind discriminator changes.
    bad = replace(fb, semantics=replace(fb.semantics, kind="interface"))
    with pytest.raises(InvalidScientificProblem, match="meaning, kind or convention"):
        transfer.admit(fa, a, bad, b, FieldMappingDefinition("m", "conservative_cell"))
