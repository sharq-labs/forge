"""Big Rocks B/C/D: provider-neutral geometry, parametric variants and the general Gmsh adapter.

Gmsh-backed tests skip (per test) where Gmsh cannot run; nothing here
fabricates a mesh.
"""

from __future__ import annotations

import hashlib
import math

import numpy as np
import pytest

from engcore.materials import MaterialIdentity, MaterialState
from engcore.numerical.core import ProviderUnavailable
from engcore.scenarios.contracts import NamedQuantity
from engcore.scientific.units.quantity import Quantity
from engcore.spatial.geometry import (
    Body, Boundary, BoundaryBinding, FeatureRef, FeatureSelector, FrameDefinition, GeometryModel, GeometryRefusal, ImportedSource,
    Interface, MaterialBinding, MeshBinding, Region, RoleAssignment, Shape, Transform, region_material_map,
)
from engcore.spatial.parametric import GeometryBuilderRegistry, GeometryParameter, ParameterKind, ParametricGeometry
from engcore.spatial.providers import gmsh_available

GMSH_OK, GMSH_DETAIL = gmsh_available()
needs_gmsh = pytest.mark.skipif(not GMSH_OK, reason=f"Gmsh unavailable: {GMSH_DETAIL}")


def m(v):
    return Quantity(v, "m")


ALU = MaterialIdentity("aluminium", specification="EN AW-6061", grade="T6")
STEEL = MaterialIdentity("steel", specification="EN 10025", grade="S355")
ROOT = FrameDefinition("world")


def plate(length=0.3, *, unit="m", left_material=ALU):
    q = lambda v: Quantity(v * (1000 if unit == "mm" else 1), unit)  # noqa: E731
    left = Body("left", Shape.rectangle(q(length), q(0.1)), "world", part_id="plate_left")
    right = Body("right", Shape.rectangle(q(0.2), q(0.1)), "world", Transform.from_quantities((q(length), q(0), q(0))))
    return GeometryModel(
        "plate", "1", 2, (ROOT,), (left, right),
        regions=(Region("left_plate", ("left",)), Region("right_plate", ("right",))),
        boundaries=(Boundary("hot", (FeatureRef("left", "xmin"),)), Boundary("cold", (FeatureRef("right", "xmax"),)),
                    Boundary("sides", tuple(FeatureRef(b, f) for b in ("left", "right") for f in ("ymin", "ymax")))),
        interfaces=(Interface("joint", "left", "right"),),
        roles=(RoleAssignment("boundary:hot", "thermal", "dirichlet_face"), RoleAssignment("boundary:hot", "structural", "fixed_support"),
               RoleAssignment("boundary:hot", "cfd", "wall")),
        materials=(MaterialBinding("left_plate", left_material), MaterialBinding("right_plate", STEEL)),
        boundary_bindings=(BoundaryBinding("hot", "thermal", "dirichlet", "bc:hot-face-temperature"),),
    )


# --------------------------------------------------------------------------
# B: identity, serialization, refusals
# --------------------------------------------------------------------------


def test_units_are_canonical_and_identity_is_content_derived():
    a, b = plate(), plate(unit="mm")
    assert a.digest == b.digest and a.shape_digest == b.shape_digest
    renamed = GeometryModel(a.model_id, a.version, 2, a.frames, a.bodies, (Region("L", ("left",)), Region("R", ("right",))),
                            a.boundaries, a.interfaces)
    assert renamed.shape_digest == a.shape_digest and renamed.digest != a.digest
    assert plate(0.31).digest != a.digest and plate(left_material=STEEL).digest != a.digest


def test_round_trip_preserves_identity_and_refuses_tampering():
    g = plate()
    payload = g.serialize()
    assert GeometryModel.from_dict(payload).digest == g.digest
    payload["bodies"][0]["shape"]["dimensions_m"]["length"] = 0.4
    with pytest.raises(GeometryRefusal, match="digest"):
        GeometryModel.from_dict(payload)
    # no provider identity leaks into the canonical record
    text = str(g.to_dict())
    assert "gmsh" not in text.lower() and "tag" not in text


def test_one_entity_carries_many_domain_roles_without_duplication():
    g = plate()
    assert g.roles_of("boundary:hot") == {"thermal": "dirichlet_face", "structural": "fixed_support", "cfd": "wall"}
    assert g.entities_with_role("cfd", "wall") == ("boundary:hot",)
    with pytest.raises(GeometryRefusal, match="one role per domain"):
        GeometryModel("x", "1", 2, (ROOT,), plate().bodies, plate().regions, plate().boundaries,
                      roles=(RoleAssignment("boundary:hot", "cfd", "wall"), RoleAssignment("boundary:hot", "cfd", "inlet")))
    with pytest.raises(GeometryRefusal, match="unknown entity"):
        GeometryModel("x", "1", 2, (ROOT,), plate().bodies, roles=(RoleAssignment("boundary:nowhere", "cfd", "wall"),))


def test_topology_relations_are_explicit():
    rel = {(r.kind, r.source, r.target) for r in plate().relations()}
    assert ("bounded_by", "body:left", "feature:left/xmin") in rel
    assert ("region_contains", "region:left_plate", "body:left") in rel
    assert ("boundary_contains", "boundary:hot", "feature:left/xmin") in rel
    assert ("interface_joins", "interface:joint", "body:right") in rel
    assert ("realizes_part", "body:left", "part:plate_left") in rel
    dims = {e.entity_id: e.dimension for e in plate().entities()}
    assert dims["region:left_plate"] == 2 and dims["boundary:hot"] == 1 and dims["feature:right/ymax"] == 1


@pytest.mark.parametrize("build, match", [
    (lambda: Shape.rectangle(0.3, m(0.1)), "bare number"),
    (lambda: Shape.box(m(1), m(1), Quantity(1, "kg")), "length unit"),
    (lambda: Shape.rectangle(m(0), m(1)), "> 0"),
    (lambda: Transform((0, 0, 0), ((1, 0, 0), (0, 1, 0), (0, 0, -1))), "determinant"),
    (lambda: Transform((0, 0, 0), ((2, 0, 0), (0, 1, 0), (0, 0, 1))), "orthonormal"),
    (lambda: FrameDefinition("w", "", Transform((1, 0, 0))), "root frame"),
    (lambda: Body("b", Shape.rectangle(m(1), m(1)), "world", Transform((0, 0, 1))), "in-plane"),
    (lambda: BoundaryBinding("hot", "thermal", "dirichlet", " "), "never implied"),
    (lambda: ImportedSource("a" * 64, "step", ""), "never guessed"),
    (lambda: ImportedSource("a" * 64, "iges", "mm"), "not supported"),
    (lambda: Transform.from_quantities(angle=Quantity(0.5, "dimensionless")), "angle unit"),
])
def test_geometry_declarations_fail_closed(build, match):
    with pytest.raises(GeometryRefusal, match=match):
        build()


def test_model_level_refusals():
    p = plate()
    with pytest.raises(GeometryRefusal, match="no feature"):
        GeometryModel("x", "1", 2, (ROOT,), p.bodies, boundaries=(Boundary("b", (FeatureRef("left", "zmax"),)),))
    with pytest.raises(GeometryRefusal, match="two different materials"):
        GeometryModel("x", "1", 2, (ROOT,), p.bodies, (Region("a", ("left",)), Region("b", ("left", "right"))),
                      materials=(MaterialBinding("a", ALU), MaterialBinding("b", STEEL)))
    with pytest.raises(GeometryRefusal, match="mixed dimensions"):
        GeometryModel("x", "1", 3, (ROOT,), p.bodies)
    with pytest.raises(GeometryRefusal, match="unknown frame"):
        GeometryModel("x", "1", 2, (ROOT,), (Body("b", Shape.rectangle(m(1), m(1)), "elsewhere"),))
    with pytest.raises(GeometryRefusal, match="void body"):
        GeometryModel("x", "1", 2, (ROOT,), (Body("b", Shape.rectangle(m(1), m(1)), "world", cutouts=("c",)),
                                             Body("c", Shape.disk(m(0.1)), "world")))
    state = MaterialState(STEEL, (NamedQuantity("temperature", Quantity(300, "K")),))
    with pytest.raises(GeometryRefusal, match="another material"):
        MaterialBinding("left_plate", ALU, state)
    assert plate().unbound_material_bodies() == ()
    unbound = GeometryModel("x", "1", 2, (ROOT,), p.bodies, p.regions, materials=(MaterialBinding("left_plate", ALU),))
    assert unbound.unbound_material_bodies() == ("right",)


def test_transforms_compose_and_invert():
    t = Transform.from_quantities((m(1), m(2), m(3)), axis=(0, 0, 1), angle=Quantity(90, "degree"))
    assert t.apply((1, 0, 0)) == pytest.approx((1, 3, 3))
    assert t.inverse().apply(t.apply((0.3, -0.2, 0.7))) == pytest.approx((0.3, -0.2, 0.7))
    child = FrameDefinition("child", "world", t)
    grand = FrameDefinition("grand", "child", Transform.from_quantities((m(1), m(0), m(0))))
    g = GeometryModel("f", "1", 3, (ROOT, child, grand), (Body("b", Shape.box(m(1), m(1), m(1)), "grand"),))
    assert g.body_to_root("b").apply((0, 0, 0)) == pytest.approx((1, 3, 3))
    with pytest.raises(GeometryRefusal, match="cycle"):
        GeometryModel("f", "1", 3, (ROOT, FrameDefinition("a", "b"), FrameDefinition("b", "a")), (Body("x", Shape.box(m(1), m(1), m(1)), "world"),))


# --------------------------------------------------------------------------
# C: parametric variants
# --------------------------------------------------------------------------


def _slab_template():
    reg = GeometryBuilderRegistry()

    def build(v):
        return GeometryModel("slab", "1", 3, (ROOT,), (Body("slab", Shape.box(v["length"], v["width"], v["thickness"]), "world"),),
                             regions=(Region("solid", ("slab",)),),
                             boundaries=(Boundary("hot", (FeatureRef("slab", "zmin"),)), Boundary("cold", (FeatureRef("slab", "zmax"),))))
    reg.register("slab_builder", "1", build)
    tpl = ParametricGeometry("slab", "1", (
        GeometryParameter("length", ParameterKind.LENGTH, m(0.05), m(0.5)),
        GeometryParameter("width", ParameterKind.WIDTH, m(0.05), m(0.5)),
        GeometryParameter("thickness", ParameterKind.THICKNESS, Quantity(1, "mm"), Quantity(50, "mm")),
    ), "slab_builder", "1")
    return tpl, reg


def test_variant_identity_binds_template_values_and_result():
    tpl, reg = _slab_template()
    vals = {"length": m(0.2), "width": Quantity(100, "mm"), "thickness": Quantity(10, "mm")}
    model, variant = tpl.instantiate(vals, reg)
    _, again = tpl.instantiate({"length": Quantity(200, "mm"), "width": m(0.1), "thickness": m(0.01)}, reg)
    assert variant.variant_id == again.variant_id and variant.geometry_digest == model.digest
    _, other = tpl.instantiate(dict(vals, thickness=Quantity(12, "mm")), reg)
    assert other.geometry_digest != variant.geometry_digest and other.variant_id != variant.variant_id
    assert variant.receipt.input_digests["template"] == tpl.digest
    assert variant.verify(tpl, reg).digest == model.digest
    import dataclasses

    with pytest.raises(GeometryRefusal, match="shape_digest"):  # a stored shape identity that the replay does not give
        dataclasses.replace(variant, shape_digest="0" * 64).verify(tpl, reg)
    assert [v.name for v in tpl.design_variables("slab.")] == ["slab.length", "slab.thickness", "slab.width"]


def test_parametric_refusals():
    tpl, reg = _slab_template()
    with pytest.raises(GeometryRefusal, match="missing"):
        tpl.instantiate({"length": m(0.2), "width": m(0.1)}, reg)
    with pytest.raises(GeometryRefusal, match="outside"):
        tpl.instantiate({"length": m(0.2), "width": m(0.1), "thickness": m(0.2)}, reg)
    with pytest.raises(GeometryRefusal, match="bounded away from zero"):
        GeometryParameter("t", ParameterKind.THICKNESS, m(0), m(1))
    with pytest.raises(GeometryRefusal, match="angle unit"):
        GeometryParameter("a", ParameterKind.ANGLE, Quantity(0, "dimensionless"), Quantity(1, "dimensionless"))
    with pytest.raises(GeometryRefusal, match="none is substituted"):
        ParametricGeometry("slab", "1", tpl.parameters, "slab_builder", "2").instantiate(
            {"length": m(0.2), "width": m(0.1), "thickness": m(0.01)}, reg)
    # a builder that changed without a version bump is caught on replay
    _, variant = tpl.instantiate({"length": m(0.2), "width": m(0.1), "thickness": m(0.01)}, reg)
    drift = GeometryBuilderRegistry()
    drift.register("slab_builder", "1", lambda v: GeometryModel("slab", "2", 3, (ROOT,), (Body("slab", Shape.box(m(1), m(1), m(1)), "world"),)))
    with pytest.raises(GeometryRefusal, match="version bump"):
        variant.verify(tpl, drift)


# --------------------------------------------------------------------------
# D: Gmsh adapter
# --------------------------------------------------------------------------


@needs_gmsh
def test_gmsh_2d_plate_maps_every_declared_entity_and_is_deterministic():
    from engcore.spatial.gmsh_adapter import GmshMeshRequest, facet_measure, mesh_geometry, mesh_measure

    g = plate()
    r = mesh_geometry(g, GmshMeshRequest(size=m(0.02)))
    mesh = r.mesh
    assert {gr.name for gr in mesh.groups} == {"left_plate", "right_plate", "hot", "cold", "sides", "joint"}
    assert mesh_measure(mesh) == pytest.approx(0.05, rel=1e-12)
    assert facet_measure(mesh, mesh.facet_indices(mesh.region("sides"))) == pytest.approx(1.0, rel=1e-12)
    assert facet_measure(mesh, mesh.facet_indices(mesh.region("joint"))) == pytest.approx(0.1, rel=1e-12)
    joint_nodes = mesh.coordinates[mesh.node_indices(mesh.region("joint"))]
    assert np.allclose(joint_nodes[:, 0], 0.3)
    assert r.binding.geometry_digest == g.digest and r.receipt.output_digests["mesh"] == mesh.digest
    # provider tags live only in the entity map
    assert r.entity_map.provider_entities_of("feature:left/xmin") and "gmsh" not in str(g.to_dict())
    again = mesh_geometry(g, GmshMeshRequest(size=m(0.02)))
    assert again.mesh.digest == mesh.digest and again.receipt.digest == r.receipt.digest
    finer = mesh_geometry(g, GmshMeshRequest(size=m(0.01)))
    assert finer.mesh.digest != mesh.digest and finer.receipt.options["size_m"] == 0.01
    # binding refuses a foreign mesh and a foreign geometry
    with pytest.raises(GeometryRefusal, match="another mesh"):
        r.binding.validate(g, finer.mesh, r.receipt)
    with pytest.raises(GeometryRefusal, match="another geometry"):
        r.binding.validate(plate(0.31), mesh, r.receipt)
    assert MeshBinding.from_dict(r.binding.to_dict()) == r.binding


@needs_gmsh
def test_gmsh_3d_cutout_and_interface_measures():
    from engcore.spatial.gmsh_adapter import GmshMeshRequest, facet_measure, mesh_geometry, mesh_measure

    box = Body("block", Shape.box(m(0.1), m(0.1), m(0.05)), "world", cutouts=("hole",))
    hole = Body("hole", Shape.cylinder(m(0.02), m(0.05)), "world", Transform.from_quantities((m(0.05), m(0.05), m(0))), void=True)
    lid = Body("lid", Shape.box(m(0.1), m(0.1), m(0.01)), "world", Transform.from_quantities((m(0), m(0), m(0.05))))
    g = GeometryModel("blk", "1", 3, (ROOT,), (box, hole, lid), regions=(Region("block", ("block",)), Region("lid", ("lid",))),
                      boundaries=(Boundary("bore", (FeatureRef("hole", "side"),)), Boundary("base", (FeatureRef("block", "zmin"),)),
                                  Boundary("top", (FeatureRef("lid", "zmax"),))),
                      interfaces=(Interface("contact", "block", "lid"),))
    r = mesh_geometry(g, GmshMeshRequest(size=m(0.01)))
    M = r.mesh
    assert M.cell_type.value == "tetrahedron"
    # planar, uncurved faces are exact; curved ones are a polygonal discretization (stated, not hidden)
    assert facet_measure(M, M.facet_indices(M.region("top"))) == pytest.approx(0.01, rel=1e-12)
    exact_base = 0.01 - math.pi * 0.02 ** 2
    assert facet_measure(M, M.facet_indices(M.region("base"))) == pytest.approx(exact_base, rel=0.02)
    assert facet_measure(M, M.facet_indices(M.region("bore"))) == pytest.approx(2 * math.pi * 0.02 * 0.05, rel=0.02)
    assert facet_measure(M, M.facet_indices(M.region("contact"))) == pytest.approx(exact_base, rel=0.02)
    assert mesh_measure(M) == pytest.approx(0.1 * 0.1 * 0.06 - math.pi * 0.02 ** 2 * 0.05, rel=0.01)


@needs_gmsh
def test_gmsh_refuses_rather_than_guessing():
    from engcore.spatial.gmsh_adapter import GmshMeshRequest, mesh_geometry

    req = GmshMeshRequest(size=m(0.05))
    a = Body("a", Shape.box(m(1), m(1), m(1)), "world")
    b = Body("b", Shape.box(m(1), m(1), m(1)), "world", Transform.from_quantities((m(0.5), m(0), m(0))))
    with pytest.raises(GeometryRefusal, match="overlap"):
        mesh_geometry(GeometryModel("o", "1", 3, (ROOT,), (a, b), (Region("a", ("a",)), Region("b", ("b",)))), req)
    far = Body("b", Shape.box(m(1), m(1), m(1)), "world", Transform.from_quantities((m(3), m(0), m(0))))
    with pytest.raises(GeometryRefusal, match="share no face"):
        mesh_geometry(GeometryModel("o", "1", 3, (ROOT,), (a, far), (Region("a", ("a",)), Region("b", ("b",))),
                                    interfaces=(Interface("i", "a", "b"),)), req)
    with pytest.raises(GeometryRefusal, match="belong to no region"):
        mesh_geometry(GeometryModel("o", "1", 3, (ROOT,), (a, far), (Region("a", ("a",)),)), req)
    tool = Body("t", Shape.cylinder(m(0.1), m(1)), "world", Transform.from_quantities((m(5), m(5), m(0))), void=True)
    cut = Body("a", Shape.box(m(1), m(1), m(1)), "world", cutouts=("t",))
    with pytest.raises(GeometryRefusal, match="matches no provider entity"):
        mesh_geometry(GeometryModel("o", "1", 3, (ROOT,), (cut, tool), (Region("a", ("a",)),),
                                    boundaries=(Boundary("bore", (FeatureRef("t", "side"),)),)), req)


@needs_gmsh
def test_region_material_map_follows_geometry_bindings():
    from engcore.spatial.gmsh_adapter import GmshMeshRequest, mesh_geometry

    g = plate()
    r = mesh_geometry(g, GmshMeshRequest(size=m(0.05)))
    hot = MaterialState(ALU, (NamedQuantity("temperature", Quantity(350, "K")),))
    cold = MaterialState(STEEL, (NamedQuantity("temperature", Quantity(300, "K")),))
    rmm = region_material_map(g, r.mesh, r.binding, r.receipt, {"left_plate": hot, "right_plate": cold})
    cells = r.mesh.cell_indices(r.mesh.region("left_plate"))
    assert rmm.state_of_cell(int(cells[0])) == hot
    with pytest.raises(GeometryRefusal, match="never defaulted"):
        region_material_map(g, r.mesh, r.binding, r.receipt, {"left_plate": hot})
    with pytest.raises(GeometryRefusal, match="another material"):
        region_material_map(g, r.mesh, r.binding, r.receipt, {"left_plate": cold, "right_plate": cold})


@needs_gmsh
def test_imported_geometry_requires_and_checks_declared_units(tmp_path):
    import gmsh

    from engcore.spatial.gmsh_adapter import GmshMeshRequest, facet_measure, mesh_geometry, mesh_measure, step_length_unit

    gmsh.initialize(readConfigFiles=False)
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("x")
        gmsh.model.occ.addBox(0, 0, 0, 20, 10, 5)
        gmsh.model.occ.synchronize()
        gmsh.write(str(tmp_path / "box.step"))
        gmsh.write(str(tmp_path / "box.brep"))
    finally:
        gmsh.finalize()
    step = (tmp_path / "box.step").read_bytes()
    assert step_length_unit(step) == "mm"
    for fmt in ("step", "brep"):
        data = (tmp_path / f"box.{fmt}").read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        src = ImportedSource(digest, fmt, "mm")
        top = FeatureSelector("top", (-1, -1, 0.0049), (1, 1, 0.0051))
        body = Body("part", Shape.imported(src, (top,)), "world")
        g = GeometryModel("imp", "1", 3, (ROOT,), (body,), (Region("solid", ("part",)),), (Boundary("top", (FeatureRef("part", "top"),)),))
        r = mesh_geometry(g, GmshMeshRequest(size=m(0.004), files={digest: str(tmp_path / f"box.{fmt}")}))
        assert mesh_measure(r.mesh) == pytest.approx(0.02 * 0.01 * 0.005, rel=1e-9)
        assert facet_measure(r.mesh, r.mesh.facet_indices(r.mesh.region("top"))) == pytest.approx(0.02 * 0.01, rel=1e-9)
        assert r.receipt.input_digests["file:part"] == digest
    wrong = ImportedSource(hashlib.sha256(step).hexdigest(), "step", "m")
    with pytest.raises(GeometryRefusal, match="the declaration says m"):
        mesh_geometry(GeometryModel("imp", "1", 3, (ROOT,), (Body("p", Shape.imported(wrong), "world"),), (Region("s", ("p",)),)),
                      GmshMeshRequest(size=m(0.004), files={wrong.file_digest: str(tmp_path / "box.step")}))
    with pytest.raises(GeometryRefusal, match="sha256"):
        mesh_geometry(GeometryModel("imp", "1", 3, (ROOT,), (Body("p", Shape.imported(wrong), "world"),), (Region("s", ("p",)),)),
                      GmshMeshRequest(size=m(0.004), files={wrong.file_digest: str(tmp_path / "box.brep")}))
    assert step_length_unit(b"no units here") is None


def test_gmsh_unavailable_is_refused_not_synthesized(monkeypatch):
    import engcore.spatial.gmsh_adapter as ga

    monkeypatch.setattr(ga, "gmsh_available", lambda: (False, "ImportError: no gmsh"))
    with pytest.raises(ProviderUnavailable, match="no gmsh"):
        ga.mesh_geometry(plate(), ga.GmshMeshRequest(size=m(0.02)))


# --------------------------------------------------------------------------
# Review round 1 (geometry/provider identity boundary) regressions
# --------------------------------------------------------------------------


@needs_gmsh
def test_review_h1_swapped_or_foreign_mesh_binding_is_refused():
    from engcore.spatial.gmsh_adapter import GmshMeshRequest, mesh_geometry

    g = plate()
    r = mesh_geometry(g, GmshMeshRequest(size=m(0.05)))
    swapped = dict(r.binding.groups, **{"region:left_plate": "right_plate", "region:right_plate": "left_plate"})
    with pytest.raises(GeometryRefusal, match="swapped or renamed"):
        MeshBinding(g.digest, r.mesh.digest, swapped, r.entity_map.digest, r.receipt.digest)
    # a binding that names the geometry G2 but a mesh produced from another shape G1 (same group names)
    g1 = plate(0.4)
    r1 = mesh_geometry(g1, GmshMeshRequest(size=m(0.05)))
    forged = MeshBinding(g.digest, r1.mesh.digest, r1.binding.groups, r1.entity_map.digest, r1.receipt.digest)
    with pytest.raises(GeometryRefusal, match="another shape"):
        forged.validate(g, r1.mesh, r1.receipt)
    with pytest.raises(GeometryRefusal, match="not backed by the receipt"):
        r.binding.validate(g, r.mesh, r1.receipt)
    tampered = r.binding.serialize()
    tampered["entity_map_digest"] = "0" * 64
    with pytest.raises(GeometryRefusal, match="digest"):
        MeshBinding.from_dict(tampered)


@needs_gmsh
def test_review_h2_flush_faces_of_other_bodies_and_internal_faces_are_not_boundaries():
    from engcore.spatial.gmsh_adapter import GmshMeshRequest, facet_measure, mesh_geometry

    # a shaft in a clearance bore, its end flush with the housing's xmin plane
    housing = Body("housing", Shape.box(m(0.1), m(0.1), m(0.1)), "world", cutouts=("bore",))
    bore = Body("bore", Shape.cylinder(m(0.02), m(0.1)), "world",
                Transform.from_quantities((m(0), m(0.05), m(0.05)), axis=(0, 1, 0), angle=Quantity(90, "degree")), void=True)
    shaft = Body("shaft", Shape.cylinder(m(0.015), m(0.1)), "world",
                 Transform.from_quantities((m(0), m(0.05), m(0.05)), axis=(0, 1, 0), angle=Quantity(90, "degree")))
    g = GeometryModel("flush", "1", 3, (ROOT,), (housing, bore, shaft), (Region("housing", ("housing",)), Region("shaft", ("shaft",))),
                      (Boundary("housing_face", (FeatureRef("housing", "xmin"),)),))
    r = mesh_geometry(g, GmshMeshRequest(size=m(0.01)))
    area = facet_measure(r.mesh, r.mesh.facet_indices(r.mesh.region("housing_face")))
    assert area == pytest.approx(0.01 - math.pi * 0.02 ** 2, rel=0.02)  # the flush shaft end (pi*0.015^2) is NOT included
    # a face shared by two meshed bodies declared as a boundary is refused
    box = Body("block", Shape.box(m(0.1), m(0.1), m(0.05)), "world")
    lid = Body("lid", Shape.box(m(0.1), m(0.1), m(0.01)), "world", Transform.from_quantities((m(0), m(0), m(0.05))))
    bad = GeometryModel("blk", "1", 3, (ROOT,), (box, lid), (Region("block", ("block",)), Region("lid", ("lid",))),
                        (Boundary("top", (FeatureRef("block", "zmax"),)),))
    with pytest.raises(GeometryRefusal, match="declared as an Interface"):
        mesh_geometry(bad, GmshMeshRequest(size=m(0.02)))


@needs_gmsh
def test_review_m1_m6_thin_bodies_and_foreign_frames_are_refused():
    from engcore.spatial.gmsh_adapter import GmshMeshRequest, mesh_geometry

    foil = GeometryModel("foil", "1", 3, (ROOT,), (Body("foil", Shape.box(m(100), m(100), Quantity(0.05, "mm")), "world"),),
                         (Region("foil", ("foil",)),))
    with pytest.raises(GeometryRefusal, match="aspect ratio"):
        mesh_geometry(foil, GmshMeshRequest(size=m(10)))
    with pytest.raises(GeometryRefusal, match="root frame"):
        mesh_geometry(plate(), GmshMeshRequest(size=m(0.05), frame_id="body"))
    assert mesh_geometry(plate(), GmshMeshRequest(size=m(0.05))).mesh.frame.frame_id == "world"


def test_review_m3_m5_ambiguous_step_units_and_non_angle_parameters_are_refused():
    from engcore.spatial.gmsh_adapter import step_length_unit

    mil = (b"#1=( LENGTH_UNIT() NAMED_UNIT(*) SI_UNIT(.MILLI.,.METRE.) );\n"
           b"#2=LENGTH_MEASURE_WITH_UNIT(LENGTH_MEASURE(0.0254),#1);\n"
           b"#3=( CONVERSION_BASED_UNIT('MIL',#2) LENGTH_UNIT() NAMED_UNIT(*) );\n")
    assert step_length_unit(mil) is None
    p = GeometryParameter("tilt", ParameterKind.ANGLE, Quantity(0, "degree"), Quantity(45, "degree"))
    with pytest.raises(GeometryRefusal, match="angle unit"):
        p.admit(Quantity(0.5, "dimensionless"))
    assert p.admit(Quantity(30, "degree")).magnitude == pytest.approx(math.radians(30))
