"""Phase 1 BR2 -- conservative cell mapping by exact intersection.

``CONSERVATIVE_CELL`` used to map nearest-site values and rescale them to the
global integral: globally conserved, locally wrong, and not affine-invariant.
It is now ``T_j = sum_i S_i |A_i n B_j| / |B_j|`` on supported geometry and a
refusal everywhere else.  Expectations below are hand-computed overlap
measures, not values read back from the implementation.

NOT RUN (Phase 1 build phase): docs/work/DEFERRED_VALIDATION.md, DV-33.
"""

from __future__ import annotations

import numpy as np
import pytest

from engcore.data import BulkDataResolver, InMemoryBulkStore
from engcore.data.field import FieldValue
from engcore.data.mesh import UnstructuredMeshData
from engcore.execution.multiphysics import FieldMapper
from engcore.execution.multiphysics.mapping import CONSERVATIVE_METHOD
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.fields import CellType, FieldDefinition, FieldLocation, StructuredMesh
from engcore.scientific.multiphysics import (
    ExtrapolationPolicy, FieldMappingDefinition, FieldMappingMethod, MappingDiagnostics,
)
from engcore.scientific.units.quantity import Quantity


def _m(value):
    return Quantity(value, "m")


def _grid(mesh_id, length, nodes, origin=0.0):
    return StructuredMesh(mesh_id, _m(length), _m(length), nodes, nodes, _m(origin), _m(origin))


def _conservative(round_trip=True):
    return FieldMappingDefinition("map", FieldMappingMethod.CONSERVATIVE_CELL, verify_round_trip=round_trip)


def _cell_field(store, mesh, values, unit="W/m**2", field_id="q"):
    definition = FieldDefinition(field_id, unit, mesh.mesh_id, FieldLocation.CELL)
    record, _ = FieldValue(definition, mesh, np.asarray(values, dtype=float)).store(store)
    return record


def _target(mesh, unit="W/m**2"):
    return FieldDefinition("q_target", unit, mesh.mesh_id, FieldLocation.CELL)


def _map(store, record, source_mesh, target_mesh, definition=None, unit="W/m**2"):
    mapper = FieldMapper(BulkDataResolver(store), store)
    result = mapper.execute(record, source_mesh, _target(target_mesh, unit), target_mesh, definition or _conservative())
    values = FieldValue.from_record(result.record, target_mesh, BulkDataResolver(store)).values
    return values, result.diagnostics


def _triangles(store, mesh_id, points, cells):
    return UnstructuredMeshData(mesh_id, CellType.TRIANGLE, np.asarray(points, float), np.asarray(cells)).store(store)


# ---- structured grids: exact separable overlaps ----------------------------------------------


def test_structured_remap_matches_hand_computed_overlaps():
    store = InMemoryBulkStore()
    source = _grid("fine", 3.0, 4)    # cells [0,1], [1,2], [2,3] per axis
    target = _grid("coarse", 3.0, 3)  # cells [0,1.5], [1.5,3] per axis
    s = np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0], [7.0, 8.0, 9.0]])  # rows are y
    overlap_1d = np.array([[1.0, 0.0], [0.5, 0.5], [0.0, 1.0]])         # source cell x target cell lengths
    expected = overlap_1d.T @ s @ overlap_1d / (1.5 * 1.5)
    values, diagnostics = _map(store, _cell_field(store, source, s), source, target)
    np.testing.assert_allclose(values, expected, rtol=0, atol=1e-13)
    # the total is conserved by construction, not by a rescale
    assert abs(values.sum() * 2.25 - s.sum() * 1.0) <= 1e-12 * s.sum()
    assert diagnostics.conservation_relative_error <= 1e-14
    assert diagnostics.provenance["method"] == CONSERVATIVE_METHOD
    assert diagnostics.provenance["geometry"] == "axis_aligned_rectangles"
    assert diagnostics.provenance["round_trip_norm"] == "measure_weighted_l2"
    assert diagnostics.extrapolated_count == 0 and diagnostics.coverage_fraction == 1.0


def test_structured_remap_between_unequal_cell_counts_per_axis():
    store = InMemoryBulkStore()
    source = StructuredMesh("s", _m(2.0), _m(1.0), 3, 2, _m(0.0), _m(0.0))  # x cells [0,1],[1,2]; y [0,1]
    target = StructuredMesh("t", _m(2.0), _m(1.0), 2, 2, _m(0.0), _m(0.0))  # one cell [0,2] x [0,1]
    values, _ = _map(store, _cell_field(store, source, [[10.0, 30.0]]), source, target)
    np.testing.assert_allclose(values, [[20.0]], rtol=0, atol=1e-13)


def test_a_constant_field_maps_to_the_same_constant():
    store = InMemoryBulkStore()
    source, target = _grid("a", 1.0, 5), _grid("b", 1.0, 4)
    values, _ = _map(store, _cell_field(store, source, np.full(source.cell_shape, 7.25)), source, target)
    np.testing.assert_allclose(values, 7.25, rtol=0, atol=1e-13)


# ---- unstructured 2D: non-uniform measures ---------------------------------------------------


def test_unequal_triangles_are_weighted_by_their_overlap_area():
    store = InMemoryBulkStore()
    # the unit square fanned from (0.25, 0.25): areas 0.125, 0.375, 0.375, 0.125
    points = [(0, 0), (1, 0), (1, 1), (0, 1), (0.25, 0.25)]
    cells = [(0, 1, 4), (1, 2, 4), (2, 3, 4), (3, 0, 4)]
    source = _triangles(store, "fan", points, cells)
    target = _grid("unit", 1.0, 2)
    s = np.array([1.0, 2.0, 3.0, 4.0])
    values, diagnostics = _map(store, _cell_field(store, source, s), source, target)
    expected = 0.125 * 1.0 + 0.375 * 2.0 + 0.375 * 3.0 + 0.125 * 4.0
    np.testing.assert_allclose(values, [[expected]], rtol=0, atol=1e-13)
    assert diagnostics.provenance["geometry"] == "convex_polygons_2d"


def test_a_signed_field_that_integrates_to_zero_is_conserved_without_division_by_zero():
    store = InMemoryBulkStore()
    source = _triangles(store, "halves", [(0, 0), (1, 0), (1, 1), (0, 1)], [(0, 1, 2), (0, 2, 3)])
    target = _grid("unit", 1.0, 2)
    values, diagnostics = _map(store, _cell_field(store, source, [5.0, -5.0]), source, target)
    np.testing.assert_allclose(values, [[0.0]], rtol=0, atol=1e-13)
    assert diagnostics.conservation_relative_error <= 1e-14
    assert list(diagnostics.provenance["conservation_scale_l1"]) == [pytest.approx(5.0)]


# ---- refusals --------------------------------------------------------------------------------


def test_offset_scale_units_are_refused():
    store = InMemoryBulkStore()
    source, target = _grid("a", 1.0, 3), _grid("b", 1.0, 2)
    record = _cell_field(store, source, np.full(source.cell_shape, 20.0), unit="degC")
    with pytest.raises(InvalidScientificProblem, match="offset-scale"):
        _map(store, record, source, target, unit="degC")


def test_a_target_outside_the_source_support_is_refused():
    store = InMemoryBulkStore()
    source, target = _grid("small", 1.0, 3), _grid("large", 2.0, 3)
    with pytest.raises(InvalidScientificProblem, match="would extrapolate"):
        _map(store, _cell_field(store, source, np.ones(source.cell_shape)), source, target)


def test_a_source_partly_outside_the_target_support_is_refused():
    store = InMemoryBulkStore()
    source, target = _grid("large", 2.0, 3), _grid("small", 1.0, 2)
    with pytest.raises(InvalidScientificProblem, match="cannot conserve"):
        _map(store, _cell_field(store, source, np.ones(source.cell_shape)), source, target)


def test_a_conservative_definition_cannot_extrapolate():
    with pytest.raises(InvalidScientificProblem, match="cannot extrapolate"):
        FieldMappingDefinition("map", FieldMappingMethod.CONSERVATIVE_CELL, ExtrapolationPolicy.NEAREST)


def test_node_fields_are_refused():
    store = InMemoryBulkStore()
    source, target = _grid("a", 1.0, 3), _grid("b", 1.0, 2)
    definition = FieldDefinition("q", "W/m**2", "a", FieldLocation.NODE)
    record, _ = FieldValue(definition, source, np.ones(source.node_shape)).store(store)
    mapper = FieldMapper(BulkDataResolver(store), store)
    with pytest.raises(InvalidScientificProblem, match="cell-centered"):
        mapper.execute(record, source, _target(target), target, _conservative())


def test_three_dimensional_cells_are_refused():
    store = InMemoryBulkStore()
    tet = UnstructuredMeshData("tet", CellType.TETRAHEDRON, np.array([(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)], float),
                               np.array([(0, 1, 2, 3)])).store(store)
    other = UnstructuredMeshData("tet2", CellType.TETRAHEDRON, np.array([(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)], float),
                                 np.array([(0, 1, 2, 3)])).store(store)
    with pytest.raises(InvalidScientificProblem, match="2D only"):
        _map(store, _cell_field(store, tet, [1.0]), tet, other)


def test_a_non_convex_quadrilateral_is_refused():
    store = InMemoryBulkStore()
    dart = UnstructuredMeshData("dart", CellType.QUADRILATERAL, np.array([(0, 0), (2, 1), (0, 2), (0.5, 1)], float),
                                np.array([(0, 1, 2, 3)])).store(store)
    target = _grid("box", 2.0, 2)
    with pytest.raises(InvalidScientificProblem, match="convex"):
        _map(store, _cell_field(store, dart, [1.0]), dart, target)


# ---- record identity ---------------------------------------------------------------------------


def test_diagnostics_without_provenance_keep_their_serialized_form():
    diagnostics = MappingDiagnostics("m", 4, 4, 0, 1.0, 0.01, None)
    assert "provenance" not in diagnostics.to_dict()
    assert MappingDiagnostics.from_dict(diagnostics.to_dict()) == diagnostics


def test_provenance_round_trips():
    diagnostics = MappingDiagnostics("m", 4, 1, 0, 1.0, None, 0.0, {"method": CONSERVATIVE_METHOD, "geometry": "g"})
    assert MappingDiagnostics.from_dict(diagnostics.to_dict()).provenance == {"method": CONSERVATIVE_METHOD, "geometry": "g"}
