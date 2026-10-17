"""Phase 2 BR9 -- the unified field-transfer engine.

* Every transfer is admitted against ``SUPPORTED_TRANSFERS``; anything else is
  refused before a value is read.
* Conservative remap now also covers tetrahedron -> tetrahedron (exact convex
  polytope intersections).  Expectations use decompositions of the unit cube
  whose overlaps are known by construction; nothing is read back from the code.
* The search structures change speed only: the KD-tree nearest site and the
  bucket index are checked against brute-force oracles written here.
* Every method records provenance; bulk values are stored and read as arrays
  with byte-identical digests.

NOT RUN (Phase 2 build phase): docs/work/DEFERRED_VALIDATION.md, DV-51..DV-53.
"""

from __future__ import annotations

import itertools

import numpy as np
import pytest

from engcore.data import BulkDataResolver, InMemoryBulkStore
from engcore.data.field import FieldValue
from engcore.data.mesh import UnstructuredMeshData
from engcore.execution.multiphysics import FieldMapper
from engcore.execution.multiphysics.mapping import SUPPORTED_TRANSFERS, transfer_support
from engcore.execution.multiphysics.spatial_index import BoxIndex, nearest_sites
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.fields import CellType, FieldDefinition, FieldLocation, StructuredMesh
from engcore.scientific.multiphysics import FieldMappingDefinition, FieldMappingMethod
from engcore.scientific.results.data_reference import ScientificDataReference
from engcore.scientific.units.quantity import Quantity

CUBE = np.array([(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)], float)
#: five tetrahedra of the cube in hexahedron vertex order: four corners (1/6) and a centre (1/3)
FIVE = ((0, 1, 3, 4), (1, 2, 3, 6), (1, 4, 5, 6), (3, 4, 6, 7), (1, 3, 4, 6))
FIVE_VOLUMES = (1 / 6, 1 / 6, 1 / 6, 1 / 6, 1 / 3)


def _kuhn():
    """The six Kuhn tetrahedra of the unit cube: (0,0,0) to (1,1,1) along each axis permutation, volume 1/6 each."""
    index = {tuple(map(int, v)): k for k, v in enumerate(CUBE)}
    tets = []
    for axes in itertools.permutations(range(3)):
        point = [0, 0, 0]
        path = [index[tuple(point)]]
        for axis in axes:
            point[axis] = 1
            path.append(index[tuple(point)])
        tets.append(tuple(path))
    return tuple(tets)


def _mesh(store, mesh_id, cells, cell_type=CellType.TETRAHEDRON, points=CUBE):
    return UnstructuredMeshData(mesh_id, cell_type, points, np.array(cells)).store(store)


def _cell_field(store, mesh, values, unit="W/m**3"):
    definition = FieldDefinition("q", unit, mesh.mesh_id, FieldLocation.CELL)
    record, _ = FieldValue(definition, mesh, np.asarray(values, float)).store(store)
    return record


def _map(store, record, source, target, method=FieldMappingMethod.CONSERVATIVE_CELL, location=FieldLocation.CELL):
    definition = FieldMappingDefinition("map", method)
    target_definition = FieldDefinition("q_t", "W/m**3", target.mesh_id, location)
    result = FieldMapper(BulkDataResolver(store), store).execute(record, source, target_definition, target, definition)
    return FieldValue.from_record(result.record, target, BulkDataResolver(store)).values, result.diagnostics


# ---- the supported table --------------------------------------------------------------------------------------


def test_the_supported_table_names_every_method():
    assert {row["method"] for row in SUPPORTED_TRANSFERS} == {m.value for m in FieldMappingMethod}


def test_unsupported_combinations_are_refused_before_any_value_is_read():
    store = InMemoryBulkStore()
    grid = StructuredMesh("g", Quantity(1, "m"), Quantity(1, "m"), 3, 3)
    tets = _mesh(store, "tets", FIVE)
    hexa = _mesh(store, "hex", (tuple(range(8)),), CellType.HEXAHEDRON)
    conservative = FieldMappingDefinition("m", FieldMappingMethod.CONSERVATIVE_CELL)
    bilinear = FieldMappingDefinition("m", FieldMappingMethod.BILINEAR)
    with pytest.raises(InvalidScientificProblem, match="2D support onto a 3D"):
        transfer_support(conservative, grid, tets, FieldLocation.CELL, FieldLocation.CELL)
    with pytest.raises(InvalidScientificProblem, match="not implemented for hexahedron"):
        transfer_support(conservative, hexa, hexa, FieldLocation.CELL, FieldLocation.CELL)
    with pytest.raises(InvalidScientificProblem, match="structured rectilinear"):
        transfer_support(bilinear, tets, tets, FieldLocation.NODE, FieldLocation.NODE)
    with pytest.raises(InvalidScientificProblem, match="cell-centered"):
        transfer_support(conservative, tets, tets, FieldLocation.NODE, FieldLocation.CELL)
    assert transfer_support(conservative, tets, tets, FieldLocation.CELL, FieldLocation.CELL) == \
        "conservative_cell:tetrahedron->tetrahedron"


# ---- 3D tetrahedra -----------------------------------------------------------------------------------------------


def test_a_constant_maps_to_the_same_constant_between_two_tetrahedralizations_of_a_cube():
    store = InMemoryBulkStore()
    source, target = _mesh(store, "kuhn", _kuhn()), _mesh(store, "five", FIVE)
    values, diagnostics = _map(store, _cell_field(store, source, np.full(6, 3.5)), source, target)
    np.testing.assert_allclose(values, 3.5, rtol=0, atol=1e-12)
    assert diagnostics.provenance["geometry"] == "convex_polyhedra_3d_tetrahedra"
    assert diagnostics.provenance["max_target_coverage_deficit"] <= 1e-9


def test_tetrahedral_remap_conserves_the_integral_and_stays_within_the_source_range():
    store = InMemoryBulkStore()
    source, target = _mesh(store, "kuhn", _kuhn()), _mesh(store, "five", FIVE)
    s = np.arange(1.0, 7.0)
    values, diagnostics = _map(store, _cell_field(store, source, s), source, target)
    assert abs(float(np.dot(values, FIVE_VOLUMES)) - s.sum() / 6.0) <= 1e-12
    assert diagnostics.conservation_relative_error <= 1e-12
    # a first-order remap of a covered cell is a convex combination of the cells it overlaps
    assert np.all(values >= s.min() - 1e-12) and np.all(values <= s.max() + 1e-12)


def test_the_same_tetrahedra_in_another_order_map_as_a_permutation():
    store = InMemoryBulkStore()
    order = (4, 2, 0, 3, 1)
    source = _mesh(store, "five", FIVE)
    target = _mesh(store, "five-permuted", tuple(FIVE[k] for k in order))
    s = np.array([10.0, 20.0, 30.0, 40.0, 50.0])
    values, _ = _map(store, _cell_field(store, source, s), source, target)
    np.testing.assert_allclose(values, s[list(order)], rtol=0, atol=1e-12)


def test_a_degenerate_tetrahedron_is_refused():
    store = InMemoryBulkStore()
    flat = _mesh(store, "flat", ((0, 1, 2, 3),))  # four coplanar cube vertices
    target = _mesh(store, "five", FIVE)
    with pytest.raises(InvalidScientificProblem, match="degenerate"):
        _map(store, _cell_field(store, flat, [1.0]), flat, target)


# ---- vector fields ------------------------------------------------------------------------------------------------


def test_a_vector_field_is_remapped_component_by_component():
    store = InMemoryBulkStore()
    source = StructuredMesh("fine", Quantity(3, "m"), Quantity(3, "m"), 4, 4)
    target = StructuredMesh("coarse", Quantity(3, "m"), Quantity(3, "m"), 3, 3)
    a = np.arange(9.0).reshape(3, 3)
    b = (np.arange(9.0) ** 2).reshape(3, 3)
    definition = FieldDefinition("v", "W/m**2", "fine", FieldLocation.CELL, components=2)
    record, _ = FieldValue(definition, source, np.stack([a, b], axis=-1)).store(store)
    target_definition = FieldDefinition("v_t", "W/m**2", "coarse", FieldLocation.CELL, components=2)
    mapper = FieldMapper(BulkDataResolver(store), store)
    result = mapper.execute(record, source, target_definition, target,
                            FieldMappingDefinition("m", FieldMappingMethod.CONSERVATIVE_CELL))
    vector = FieldValue.from_record(result.record, target, BulkDataResolver(store)).values
    for component, scalar in enumerate((a, b)):
        scalar_record = _scalar(store, source, scalar)
        alone, _ = _map(store, scalar_record, source, target)
        np.testing.assert_allclose(vector[..., component], alone, rtol=0, atol=1e-13)


def _scalar(store, mesh, values):
    definition = FieldDefinition("s", "W/m**3", mesh.mesh_id, FieldLocation.CELL)
    record, _ = FieldValue(definition, mesh, values).store(store)
    return record


# ---- search structures against brute force ------------------------------------------------------------------


def _brute_nearest(source, target):
    out = []
    for point in target:
        delta = source - point
        out.append(int(np.argmin(np.einsum("ij,ij->i", delta, delta))))
    return np.array(out)


def test_kd_tree_nearest_reproduces_the_exhaustive_rule_including_exact_ties():
    xs = np.linspace(0.0, 1.0, 5)
    source = np.array([(x, y) for y in xs for x in xs])
    centres = (xs[:-1] + xs[1:]) / 2
    target = np.array([(x, y) for y in centres for x in centres] + [(0.3, 0.7), (1.2, -0.1)])
    np.testing.assert_array_equal(nearest_sites(source, target), _brute_nearest(source, target))


def test_kd_tree_nearest_matches_brute_force_on_scattered_points():
    rng = np.random.default_rng(20261017)
    source, target = rng.random((300, 3)), rng.random((200, 3))
    np.testing.assert_array_equal(nearest_sites(source, target), _brute_nearest(source, target))


def test_the_box_index_returns_a_superset_of_every_intersecting_box_in_ascending_order():
    rng = np.random.default_rng(7)
    lower = rng.random((400, 2))
    upper = lower + rng.random((400, 2)) * 0.1
    index = BoxIndex(lower, upper)
    for _ in range(100):
        q_lower = rng.random(2)
        q_upper = q_lower + rng.random(2) * 0.2
        truth = np.flatnonzero(np.all(lower <= q_upper, axis=1) & np.all(upper >= q_lower, axis=1))
        found = index.query_box(q_lower, q_upper)
        assert set(truth) <= set(found)
        assert list(found) == sorted(found)


# ---- provenance and the data plane ----------------------------------------------------------------------------


def test_an_interpolation_records_its_supports_and_that_it_is_not_conservative():
    store = InMemoryBulkStore()
    source = StructuredMesh("a", Quantity(1, "m"), Quantity(1, "m"), 5, 5)
    target = StructuredMesh("b", Quantity(1, "m"), Quantity(1, "m"), 3, 3)
    definition = FieldDefinition("t", "K", "a", FieldLocation.NODE)
    record, _ = FieldValue(definition, source, np.full(source.node_shape, 300.0)).store(store)
    result = FieldMapper(BulkDataResolver(store), store).execute(
        record, source, FieldDefinition("t_b", "K", "b", FieldLocation.NODE), target,
        FieldMappingDefinition("m", FieldMappingMethod.BILINEAR))
    provenance = result.diagnostics.provenance
    assert provenance["conservative"] is False
    assert provenance["source_support"] == source.fingerprint() and provenance["target_support"] == target.fingerprint()


def test_array_storage_has_the_digest_of_the_list_encoding():
    store = InMemoryBulkStore()
    mesh = StructuredMesh("m", Quantity(1, "m"), Quantity(1, "m"), 4, 3)
    values = np.linspace(-2.0, 7.0, mesh.node_count).reshape(mesh.node_shape)
    record, reference = FieldValue(FieldDefinition("t", "K", "m"), mesh, values).store(store)
    expected, _ = ScientificDataReference.for_values("t:field", values.reshape(-1).tolist(), unit=reference.unit)
    assert reference.digest == expected.digest
    resolver = BulkDataResolver(store)
    np.testing.assert_array_equal(resolver.resolve_array(reference), np.array(resolver.resolve(reference)))
