"""Phase 3 BR16 -- mesh validity, adaptation provenance, and no coupling across a changed support.

* ``numerical.mesh_quality``: measures, orientation, inversion, degeneracy and
  shape quality, with closed-form expectations (equilateral triangle and
  regular tetrahedron have quality 1).
* ``numerical.mesh_adaptation`` (EXC-1 A1 slice, defect/provenance fixes
  only): every grid version has a digest; cycles record the grid they
  evaluated and what they marked; superseded grids are named; a round-off
  bisection is skipped, never turned into a non-increasing grid; unsupported
  adaptation combinations are refused.
* Relaxation never mixes two values on different supports of equal shape.

NOT RUN (Phase 3 build phase): docs/work/DEFERRED_VALIDATION.md, DV-77..DV-79.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from engcore.data import BulkDataResolver, InMemoryBulkStore
from engcore.data.field import FieldValue
from engcore.data.mesh import UnstructuredMeshData
from engcore.execution.multiphysics.relaxation import RelaxationController
from engcore.numerical import NumericalRefusal
from engcore.numerical.mesh_adaptation import (
    AdaptationPolicy, Grid1D, adapt_grid, refine, require_supported_adaptation,
)
from engcore.numerical.mesh_quality import (
    MeshQualityPolicy, MeshQualityRefusal, assess_mesh, assess_support, degenerate_cells, inverted_relative_to,
    require_valid_mesh, shape_quality, signed_measures,
)
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.fields import CellType, FieldDefinition, FieldLocation, StructuredMesh
from engcore.scientific.multiphysics import RelaxationKind, RelaxationPolicy
from engcore.scientific.units.quantity import Quantity

EQUILATERAL = np.array([(0.0, 0.0), (1.0, 0.0), (0.5, math.sqrt(3.0) / 2.0)])
REGULAR_TET = np.array([(1.0, 1.0, 1.0), (1.0, -1.0, -1.0), (-1.0, 1.0, -1.0), (-1.0, -1.0, 1.0)])


# ---- measures and quality ----------------------------------------------------------------------------------------


def test_signed_measures_follow_orientation():
    assert signed_measures("triangle", EQUILATERAL, [(0, 1, 2)])[0] == pytest.approx(math.sqrt(3.0) / 4.0)
    assert signed_measures("triangle", EQUILATERAL, [(0, 2, 1)])[0] == pytest.approx(-math.sqrt(3.0) / 4.0)
    square = np.array([(0, 0), (1, 0), (1, 1), (0, 1)], float)
    assert signed_measures("quadrilateral", square, [(0, 1, 2, 3)])[0] == pytest.approx(1.0)
    # regular tetrahedron of edge 2 sqrt(2): volume (2 sqrt 2)^3 / (6 sqrt 2) = 8/3; this vertex order is negative
    assert abs(signed_measures("tetrahedron", REGULAR_TET, [(0, 1, 2, 3)])[0]) == pytest.approx(8.0 / 3.0)
    assert signed_measures("interval", np.array([0.0, 0.25]), [(0, 1)])[0] == pytest.approx(0.25)


def test_quality_is_one_for_the_regular_cells_and_falls_for_a_sliver():
    assert shape_quality("triangle", EQUILATERAL, [(0, 1, 2)])[0] == pytest.approx(1.0)
    assert shape_quality("tetrahedron", REGULAR_TET, [(0, 1, 2, 3)])[0] == pytest.approx(1.0)
    square = np.array([(0, 0), (1, 0), (1, 1), (0, 1)], float)
    assert shape_quality("quadrilateral", square, [(0, 1, 2, 3)])[0] == pytest.approx(1.0)
    sliver = np.array([(0.0, 0.0), (1.0, 0.0), (0.5, 1e-3)])
    # q = 4 sqrt(3) * 5e-4 / (1 + 2 * 0.250001) ~ 2.3e-3
    assert shape_quality("triangle", sliver, [(0, 1, 2)])[0] == pytest.approx(4 * math.sqrt(3) * 5e-4 / (1 + 2 * 0.250001),
                                                                             rel=1e-6)


def test_degenerate_inverted_non_convex_and_low_quality_cells_are_each_named():
    points = np.array([(0, 0), (1, 0), (2, 0), (0, 1), (1, 1), (0.5, 0.01)], float)
    cells = [(0, 1, 3), (1, 0, 4), (0, 1, 2), (0, 1, 5)]  # ok, inverted (clockwise), collinear, sliver
    report = assess_mesh("triangle", points, cells, MeshQualityPolicy(0.1, orientation="positive"))
    defects = dict(report.defects)
    assert defects["degenerate"] == (2,) and defects["inverted"] == (1,) and defects["low_quality"] == (3,)
    assert not report.valid
    with pytest.raises(MeshQualityRefusal):
        require_valid_mesh("triangle", points, cells, MeshQualityPolicy(0.1, orientation="positive"))
    arrow = np.array([(0, 0), (2, 0), (1, 0.2), (1, 2)], float)  # a reflex corner at (1, 0.2)
    quad = dict(assess_mesh("quadrilateral", np.vstack([arrow]), [(0, 1, 3, 2)], MeshQualityPolicy(0.01)).defects)
    assert quad["non_convex"] == (0,)


def test_consistent_orientation_admits_a_uniformly_clockwise_mesh():
    points = np.array([(0, 0), (1, 0), (0, 1), (1, 1)], float)
    report = assess_mesh("triangle", points, [(0, 2, 1), (1, 2, 3)], MeshQualityPolicy(0.1))
    assert dict(report.defects)["inverted"] == ()


@pytest.mark.parametrize("cell_type,coords,cells", [
    ("hexahedron", np.zeros((8, 3)), [tuple(range(8))]),
    ("triangle", EQUILATERAL, [(0, 1, 1)]),
    ("triangle", EQUILATERAL, [(0, 1, 7)]),
    ("triangle", np.array([(0.0, 0.0), (1.0, 0.0), (math.nan, 1.0)]), [(0, 1, 2)]),
])
def test_unsupported_or_malformed_meshes_are_refused(cell_type, coords, cells):
    with pytest.raises(MeshQualityRefusal):
        signed_measures(cell_type, coords, cells)


def test_inversion_relative_to_a_reference_configuration():
    reference = signed_measures("triangle", EQUILATERAL, [(0, 1, 2)])
    flipped = EQUILATERAL.copy()
    flipped[2, 1] = -flipped[2, 1]  # the apex moved through the base
    assert inverted_relative_to(reference, signed_measures("triangle", flipped, [(0, 1, 2)])).tolist() == [0]
    collapsed = EQUILATERAL.copy()
    collapsed[2, 1] = 0.0
    assert degenerate_cells("triangle", collapsed, [(0, 1, 2)]).tolist() == [0]


def test_a_stored_structured_support_is_valid_by_construction():
    mesh = StructuredMesh("s", Quantity(1.0, "m"), Quantity(1.0, "m"), 3, 3)
    assert assess_support(mesh, BulkDataResolver(InMemoryBulkStore()), MeshQualityPolicy(0.5)).valid


# ---- adaptation provenance ---------------------------------------------------------------------------------------


def _policy(**kw):
    base = dict(theta=1.0, tolerance=Quantity(1e-3, "K"), minimum_cell=Quantity(1e-6, "m"), max_cycles=10,
                max_nodes=10_000)
    return AdaptationPolicy(**{**base, **kw})


def test_every_grid_version_is_identified_and_superseded_values_are_named():
    initial = Grid1D(tuple(np.linspace(0.0, 1.0, 3)), "m")
    record = adapt_grid(lambda g: [x * x for x in g.nodes], initial, _policy(), value_unit="K")
    digests = [c.grid_digest for c in record.cycles]
    assert digests[0] == initial.digest and digests[-1] == record.grid.digest
    assert len(set(digests)) == len(digests)  # every cycle evaluated a different grid
    assert record.superseded_grids == tuple(digests[:-1])
    assert record.to_dict()["superseded_grid_digests"] == list(digests[:-1])
    assert all(c.max_neighbour_ratio <= 2.0 + 1e-12 for c in record.cycles)
    assert record.cycles[0].marked == (0, 1)  # theta = 1 marks every cell of a uniform quadratic


def test_equal_grids_share_a_digest_and_different_ones_do_not():
    assert Grid1D((0.0, 0.5, 1.0), "m").digest == Grid1D((0.0, 0.5, 1.0), "meter").digest
    assert Grid1D((0.0, 0.5, 1.0), "m").digest != Grid1D((0.0, 0.5000000001, 1.0), "m").digest


def test_a_bisection_below_float_resolution_is_skipped_not_turned_into_a_bad_grid():
    tiny = Grid1D((1.0, math.nextafter(1.0, 2.0), 2.0), "m")
    refined = refine(tiny, [0, 1], minimum_cell=0.0, max_ratio=1e300)
    assert refined.nodes == (1.0, math.nextafter(1.0, 2.0), 1.5, 2.0)  # cell 0 left alone, cell 1 bisected
    with pytest.raises(NumericalRefusal, match="does not exist"):
        refine(tiny, [5], minimum_cell=0.0, max_ratio=2.0)


@pytest.mark.parametrize("dimension,transient", [(2, False), (3, False), (1, True)])
def test_adaptation_outside_the_admitted_slice_is_refused(dimension, transient):
    with pytest.raises(NumericalRefusal, match="EXC-1"):
        require_supported_adaptation(spatial_dimension=dimension, transient=transient)
    require_supported_adaptation(spatial_dimension=1, transient=False)


# ---- no coupling history across a changed support ----------------------------------------------------------------


def _two_meshes(store):
    cells = np.array([(0, 1, 2)])
    a = UnstructuredMeshData("a", CellType.TRIANGLE, np.array([(0, 0), (1, 0), (0, 1)], float), cells).store(store)
    b = UnstructuredMeshData("b", CellType.TRIANGLE, np.array([(0, 0), (2, 0), (0, 2)], float), cells).store(store)
    return a, b


def _cell_field(store, mesh, value):
    record, _ = FieldValue(FieldDefinition("q", "W/m**2", mesh.mesh_id, FieldLocation.CELL), mesh,
                           np.array([value], float)).store(store)
    return record


def test_relaxation_refuses_to_mix_equal_shapes_on_two_supports():
    store = InMemoryBulkStore()
    a, b = _two_meshes(store)
    controller = RelaxationController(RelaxationPolicy(RelaxationKind.CONSTANT, 0.5, 0.05, 1.0), BulkDataResolver(store),
                                      store, {"a": a, "b": b})
    with pytest.raises(InvalidScientificProblem, match="two supports"):
        controller.relax("e", _cell_field(store, a, 1.0), _cell_field(store, b, 2.0), unit="W/m**2")
    iqn = RelaxationController(RelaxationPolicy(RelaxationKind.IQN_ILS, 0.5, 0.05, 1.0, 3), BulkDataResolver(store),
                               store, {"a": a, "b": b})
    with pytest.raises(InvalidScientificProblem, match="two supports"):
        iqn.relax_joint({"e": (_cell_field(store, a, 1.0), _cell_field(store, b, 2.0), "W/m**2")})
