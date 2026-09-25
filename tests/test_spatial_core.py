"""BIG 7 Field + Mesh core: exact meshes, regions, framed fields, mappings, material binding.

Gmsh runs for real when available; otherwise the Gmsh-specific tests are
skipped with the provider's own reason and a bounded hand-built fixture is used.
Roundtrip/replay agreement is reproducibility only.  Mapped values are not
measurements.  Material data are the illustrative BIG 5 fixtures.
"""

from __future__ import annotations

import importlib.util
import json

import numpy as np
import pytest

from engcore.materials import MaterialState
from engcore.numerical.core import ProviderUnavailable
from engcore.scenarios import NamedQuantity
from engcore.scientific.fields import CellType
from engcore.scientific.units.quantity import Quantity
from engcore.spatial import (
    Conservation, CoordinateFrame, Derivation, Location, PhysicalGroup, Rank, RegionMaterialMap, SpatialField,
    SpatialFieldDefinition, SpatialMesh, SpatialRefusal, gmsh_available, gmsh_two_region_plate,
    interpolate_p1_to_mesh, node_to_cell_average, read_meshio, write_meshio,
)

_spec = importlib.util.spec_from_file_location("materials_fixtures", "tests/test_materials_engine.py")
M = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(M)

GMSH_OK, GMSH_DETAIL = gmsh_available()
needs_gmsh = pytest.mark.skipif(not GMSH_OK, reason=f"Gmsh unavailable: {GMSH_DETAIL}")
FRAME = CoordinateFrame("plate-xy", 2)


def fixture_plate(nx=4, ny=2, lx=0.2, ly=0.1, frame=FRAME):
    """Bounded hand-built structured triangulation with the same groups as the Gmsh plate."""
    xs, ys = np.linspace(0, lx, nx + 1), np.linspace(0, ly, ny + 1)
    coords = np.array([[x, y] for y in ys for x in xs])
    nid = lambda i, j: j * (nx + 1) + i  # noqa: E731
    cells, tags = [], []
    for j in range(ny):
        for i in range(nx):
            a, b, c, d = nid(i, j), nid(i + 1, j), nid(i + 1, j + 1), nid(i, j + 1)
            t = 1 if (i + 0.5) * lx / nx < lx / 2 else 2
            cells += [[a, b, c], [a, c, d]]
            tags += [t, t]
    facets, ftags = [], []
    for j in range(ny):
        facets += [[nid(0, j), nid(0, j + 1)], [nid(nx, j), nid(nx, j + 1)]]
        ftags += [11, 12]
    for i in range(nx):
        facets += [[nid(i, 0), nid(i + 1, 0)], [nid(i, ny), nid(i + 1, ny)]]
        ftags += [13, 14]
    groups = (PhysicalGroup("left_plate", "cells", 1), PhysicalGroup("right_plate", "cells", 2), PhysicalGroup("left", "facets", 11),
              PhysicalGroup("right", "facets", 12), PhysicalGroup("bottom", "facets", 13), PhysicalGroup("top", "facets", 14))
    return SpatialMesh(coordinates=coords, cells=cells, cell_type=CellType.TRIANGLE, frame=frame, cell_tags=tags,
                       facets=facets, facet_tags=ftags, groups=groups)


@pytest.fixture(scope="module")
def plate():
    return gmsh_two_region_plate(length=0.2, height=0.1, split=0.1, size=0.02) if GMSH_OK else fixture_plate()


def temperature(mesh, fn=lambda x, y: 300 + 500 * x):
    d = SpatialFieldDefinition("T", "temperature", "K", Location.NODE, Rank.SCALAR)
    return SpatialField(d, mesh, [fn(x, y) for x, y in mesh.coordinates], Derivation.PRESCRIBED)


# ---- 1. exact mesh with regions and boundaries -------------------------------


@needs_gmsh
def test_gmsh_plate_is_real_exact_and_replayable():
    a = gmsh_two_region_plate(length=0.2, height=0.1, split=0.1, size=0.02)
    b = gmsh_two_region_plate(length=0.2, height=0.1, split=0.1, size=0.02)
    assert a.digest == b.digest and a.provenance.generator == "gmsh"
    finer = gmsh_two_region_plate(length=0.2, height=0.1, split=0.1, size=0.01)
    assert finer.digest != a.digest and finer.cell_count > a.cell_count
    total = a.cell_measures().sum()
    left = a.cell_measures()[a.cell_indices(a.region("left_plate"))].sum()
    assert total == pytest.approx(0.02) and left == pytest.approx(0.01)
    left_nodes = a.coordinates[a.node_indices(a.region("left"))]
    assert np.allclose(left_nodes[:, 0], 0.0)


def test_identity_is_content_not_names(plate):
    again = SpatialMesh.from_dict(json.loads(json.dumps(plate.to_dict())))
    assert again.digest == plate.digest and again.mesh_id == plate.mesh_id
    moved = plate.coordinates.copy()
    moved[0, 0] += 1e-9
    p = plate.to_dict()
    shifted = SpatialMesh(coordinates=moved, cells=plate.cells, cell_type=plate.cell_type, frame=plate.frame, cell_tags=plate.cell_tags,
                          facets=plate.facets, facet_tags=plate.facet_tags, groups=plate.groups)
    assert shifted.digest != plate.digest
    retag = plate.cell_tags.copy()
    retag[0] = 2 if retag[0] == 1 else 1
    retagged = SpatialMesh(coordinates=plate.coordinates, cells=plate.cells, cell_type=plate.cell_type, frame=plate.frame, cell_tags=retag,
                           facets=plate.facets, facet_tags=plate.facet_tags, groups=plate.groups)
    assert retagged.digest != plate.digest
    p["digest"] = "0" * 64
    with pytest.raises(SpatialRefusal, match="digest"):
        SpatialMesh.from_dict(p)
    # the Core support shares the content fingerprint and a content-derived id
    assert plate.core_support().fingerprint() == plate.core_fingerprint


def test_region_from_another_mesh_is_refused(plate):
    other = fixture_plate(nx=6)
    with pytest.raises(SpatialRefusal, match="different mesh"):
        plate.cell_indices(other.region("left_plate"))
    with pytest.raises(SpatialRefusal, match="boundary, not a cell region"):
        plate.cell_indices(plate.region("left"))
    with pytest.raises(SpatialRefusal, match="no region"):
        plate.region("middle")


def test_invalid_mesh_inputs_are_refused():
    base = fixture_plate()
    with pytest.raises(SpatialRefusal, match="not a facet of any cell"):
        SpatialMesh(coordinates=base.coordinates, cells=base.cells, cell_type=CellType.TRIANGLE, frame=FRAME, cell_tags=base.cell_tags,
                    facets=[[0, 7]], facet_tags=[11], groups=())
    with pytest.raises(SpatialRefusal, match="no cells carries|which no"):
        SpatialMesh(coordinates=base.coordinates, cells=base.cells, cell_type=CellType.TRIANGLE, frame=FRAME, cell_tags=base.cell_tags,
                    groups=(PhysicalGroup("ghost", "cells", 9),))
    with pytest.raises(SpatialRefusal, match="dimension"):
        SpatialMesh(coordinates=base.coordinates, cells=base.cells, cell_type=CellType.TRIANGLE, frame=CoordinateFrame("f3", 3), cell_tags=base.cell_tags)


# ---- 2. scalar temperature field ---------------------------------------------


def test_unit_aware_temperature_field_and_core_bridge(plate):
    t = temperature(plate)
    core = t.to_core()
    assert core.unit == "kelvin" and core.shape == (plate.node_count,)
    assert core.to_unit("degC").values.max() == pytest.approx(300 + 500 * plate.coordinates[:, 0].max() - 273.15)
    again = SpatialField.from_dict(json.loads(json.dumps(t.to_dict())), plate)
    assert again.digest == t.digest
    with pytest.raises(SpatialRefusal, match="expects shape"):
        SpatialField(t.definition, plate, t.values[:-1], Derivation.PRESCRIBED)
    with pytest.raises(SpatialRefusal, match="non-finite"):
        SpatialField(t.definition, plate, np.full(plate.node_count, np.nan), Derivation.PRESCRIBED)
    with pytest.raises(SpatialRefusal, match="different mesh"):
        SpatialField.from_dict(t.to_dict(), fixture_plate(nx=6))
    edge = SpatialField(SpatialFieldDefinition("q", "heat_flux_normal", "W/m^2", Location.FACET, Rank.SCALAR), plate,
                        np.ones(len(plate.facets)), Derivation.PRESCRIBED)
    with pytest.raises(SpatialRefusal, match="node and cell"):
        edge.to_core()


# ---- 3. vector field bound to a frame ----------------------------------------


def test_vector_field_requires_matching_frame(plate):
    d = SpatialFieldDefinition("u", "velocity", "m/s", Location.NODE, Rank.VECTOR, frame_id="plate-xy")
    v = SpatialField(d, plate, np.tile([1.0, 0.5], (plate.node_count, 1)), Derivation.PRESCRIBED)
    assert v.to_core().definition.components == 2
    with pytest.raises(SpatialRefusal, match="frame"):
        SpatialFieldDefinition("u", "velocity", "m/s", Location.NODE, Rank.VECTOR)
    with pytest.raises(SpatialRefusal, match="frame"):
        SpatialField(SpatialFieldDefinition("u", "velocity", "m/s", Location.NODE, Rank.VECTOR, frame_id="rotated"), plate,
                     np.zeros((plate.node_count, 2)), Derivation.PRESCRIBED)
    with pytest.raises(SpatialRefusal, match="expects shape"):
        SpatialField(d, plate, np.zeros((plate.node_count, 3)), Derivation.PRESCRIBED)
    with pytest.raises(SpatialRefusal, match="affine"):
        SpatialFieldDefinition("g", "gradient", "degC", Location.NODE, Rank.VECTOR, frame_id="plate-xy")


# ---- 4. explicit mappings ------------------------------------------------------


def test_node_to_cell_and_mesh_to_mesh_mapping(plate):
    t = temperature(plate)
    cell_t, rec = node_to_cell_average(t)
    assert cell_t.derivation is Derivation.MAPPED and rec.conservation is Conservation.EXACT_FOR_P1_INTERPOLANT
    assert rec.source_integral == pytest.approx(rec.target_integral)
    target = fixture_plate(nx=5, ny=3)
    mapped, rec2 = interpolate_p1_to_mesh(t, target)
    exact = 300 + 500 * target.coordinates[:, 0]
    assert np.allclose(mapped.values, exact)  # linear field: P1 reproduces it
    assert rec2.conservation is Conservation.NOT_CONSERVATIVE and rec2.to_dict()["classification"] == "mapped_interpolation_not_measurement"
    assert rec2.digest in mapped.provenance and t.digest in mapped.provenance
    curved, rec3 = interpolate_p1_to_mesh(temperature(plate, lambda x, y: 300 + 2e4 * x * x), target)
    assert rec3.source_integral != pytest.approx(rec3.target_integral, rel=1e-12)  # reported, not "fixed"


def test_mapping_refuses_extrapolation_and_frame_mismatch(plate):
    t = temperature(plate)
    bigger = fixture_plate(lx=0.3)
    with pytest.raises(SpatialRefusal, match="outside the source mesh"):
        interpolate_p1_to_mesh(t, bigger)
    rotated = fixture_plate(frame=CoordinateFrame("other-xy", 2))
    with pytest.raises(SpatialRefusal, match="different coordinate frames"):
        interpolate_p1_to_mesh(t, rotated)
    with pytest.raises(SpatialRefusal, match="MAPPED|mapped"):
        SpatialField(t.definition, plate, t.values, Derivation.MAPPED)


def test_meshio_roundtrip_preserves_identity(plate, tmp_path):
    path = str(tmp_path / "plate.msh")
    write_meshio(plate, path)
    back = read_meshio(path, frame=FRAME)
    assert back.digest == plate.digest and back.provenance.generator == "meshio"


# ---- 5. material binding -------------------------------------------------------


def test_regions_bound_to_exact_materials_feed_a_resolved_field(plate):
    props, _ = M._alloy_set()
    board = M._board_set()
    hot = MaterialState(M.ALLOY, (NamedQuantity("temperature", Quantity(450, "K")),), "solid")
    wet = MaterialState(M.BOARD, (NamedQuantity("moisture_content", Quantity(0.05, "dimensionless")),
                                  NamedQuantity("temperature", Quantity(293.15, "K"))))
    binding = RegionMaterialMap(plate, ((plate.region("left_plate"), hot), (plate.region("right_plate"), wet)))
    k, resolved = binding.property_field({M.ALLOY.digest: props, M.BOARD.digest: board}, "thermal_conductivity", "W/(m*K)", "k")
    left = plate.cell_indices(plate.region("left_plate"))
    right = plate.cell_indices(plate.region("right_plate"))
    assert np.allclose(k.values[left], 215.0) and np.allclose(k.values[right], 0.045)
    assert k.derivation is Derivation.RESOLVED and all(r.digest in k.provenance for r in resolved)
    # the resolved field changes a computation: conductance-weighted mean differs by region
    assert (k.values * plate.cell_measures()).sum() != pytest.approx(215.0 * plate.cell_measures().sum())


def test_material_binding_refusals(plate):
    hot = MaterialState(M.ALLOY, (NamedQuantity("temperature", Quantity(450, "K")),), "solid")
    with pytest.raises(SpatialRefusal, match="boundary"):
        RegionMaterialMap(plate, ((plate.region("left"), hot),))
    with pytest.raises(SpatialRefusal, match="overlaps"):
        RegionMaterialMap(plate, ((plate.region("left_plate"), hot), (plate.region("left_plate"), hot)))
    with pytest.raises(SpatialRefusal, match="different mesh"):
        RegionMaterialMap(plate, ((fixture_plate(nx=6).region("left_plate"), hot),))
    half = RegionMaterialMap(plate, ((plate.region("left_plate"), hot),))
    assert half.state_of_cell(int(plate.cell_indices(plate.region("right_plate"))[0])) is None
    props, _ = M._alloy_set()
    with pytest.raises(SpatialRefusal, match="no bound material"):
        half.property_field({M.ALLOY.digest: props}, "thermal_conductivity", "W/(m*K)", "k")
    too_hot = MaterialState(M.ALLOY, (NamedQuantity("temperature", Quantity(900, "K")),), "solid")
    whole = RegionMaterialMap(plate, ((plate.region("left_plate"), too_hot), (plate.region("right_plate"), too_hot)))
    with pytest.raises(SpatialRefusal, match="UNKNOWN"):
        whole.property_field({M.ALLOY.digest: props}, "thermal_conductivity", "W/(m*K)", "k")


def test_gmsh_unavailable_is_explicit(monkeypatch):
    import engcore.spatial.providers as prov
    monkeypatch.setattr(prov, "gmsh_available", lambda: (False, "OSError: simulated"))
    with pytest.raises(ProviderUnavailable, match="simulated"):
        prov.gmsh_two_region_plate(length=1, height=1, split=0.5, size=0.5)
