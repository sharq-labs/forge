"""Proof D + E + H(material): real CalculiX (process) vs FEniCSx on the same BIG 7 mesh and BIG 5 material records.

Same mesh, same linear triangles, same resolved Young's modulus / Poisson ratio
per region, same clamped edge and edge traction.  Agreement between the two
independent implementations is SOLVER CORROBORATION, not validation.
"""

from __future__ import annotations

import importlib.util

import numpy as np
import pytest

from engcore.materials import MaterialState
from engcore.providers import ComparisonDeclaration, OutputSelection, ProviderRegistry, compare_providers
from engcore.scenarios import NamedQuantity
from engcore.scientific.units.quantity import Quantity
from engcore.spatial import RegionMaterialMap, gmsh_available
from forge_calculix import CalculixProvider, PlaneStressProblem, RegionMaterial, descriptor

REG = ProviderRegistry()
descriptor.register(REG)
CCX = REG.status("calculix").available
try:
    from forge_fenicsx import FenicsxProvider, fenicsx_available
    FENICS = fenicsx_available()[0] and gmsh_available()[0]
except Exception:  # FEniCSx absent: the CalculiX-only parts still run elsewhere
    FENICS = False
pytestmark = pytest.mark.skipif(not (CCX and FENICS), reason="CalculiX or FEniCSx/Gmsh unavailable")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _case():
    P = _load("pde_fixtures_ccx", "providers/fenicsx/tests/test_pde_fenicsx.py")
    mesh = P.plate()
    sets = P.elastic_property_sets()
    room = NamedQuantity("temperature", Quantity(293.15, "K"))
    states = ((mesh.region("left_plate"), MaterialState(P.M.ALLOY, (room,), "solid")), (mesh.region("right_plate"), MaterialState(P.M.BOARD, (room,))))
    binding = RegionMaterialMap(mesh, states)
    E, rE = binding.property_field(sets, "youngs_modulus", "Pa", "E")
    nu, rnu = binding.property_field(sets, "poisson_ratio", "dimensionless", "nu")
    return P, mesh, E, nu, rE, rnu


def test_proof_d_e_calculix_and_fenicsx_corroborate_plane_stress_displacement():
    from engcore.pde import (PLANE_STRESS_ELASTICITY, BCKind, BoundaryCondition, CoefficientBinding, DiscretizationSpec, PDEProblem,
                             PhysicalModel, SourcedQuantity)
    from engcore.spatial import Location, Rank, SpatialFieldDefinition
    P, mesh, E, nu, rE, rnu = _case()
    thickness = Quantity(5, "mm")
    traction = (Quantity(1e4, "Pa"), Quantity(0, "Pa"))
    # CalculiX material cards are generated from the SAME resolved BIG 5 records (not re-typed constants)
    mats = tuple(RegionMaterial(region, e, n) for region, e, n in zip(("left_plate", "right_plate"), rE, rnu))
    ccx = CalculixProvider(REG).execute(PlaneStressProblem(mesh, mats, thickness, "left", "right", traction))
    assert ccx.succeeded, ccx.reason
    deck = ccx.artifacts["job.inp"]
    assert "*ELASTIC" in deck and repr(float(rE[1].value.value.to("Pa").magnitude)) in deck and ccx.process_digest
    sq = lambda q, why: SourcedQuantity(q, "prescribed", {"declared": why})  # noqa: E731
    free = sq(Quantity(0, "Pa"), "traction-free")
    fx = FenicsxProvider().execute(PDEProblem(
        "plate-elastic-p1", mesh, PhysicalModel("solid.linear_elastic_plane_stress", "1", "small-strain isotropic plane stress"),
        PLANE_STRESS_ELASTICITY, SpatialFieldDefinition("u", "displacement", "m", Location.NODE, Rank.VECTOR, frame_id="plate-xy"),
        (CoefficientBinding("youngs_modulus", field=E), CoefficientBinding("poisson_ratio", field=nu),
         CoefficientBinding("thickness", constant=sq(thickness, "plate thickness"))),
        (BoundaryCondition(BCKind.DIRICHLET, "left", sq(Quantity(0, "m"), "clamped")),
         BoundaryCondition(BCKind.NEUMANN, "right", sq(traction[0], "uniform tension"), vector_value=traction),
         BoundaryCondition(BCKind.NEUMANN, "top", free, vector_value=(Quantity(0, "Pa"), Quantity(0, "Pa"))),
         BoundaryCondition(BCKind.NEUMANN, "bottom", free, vector_value=(Quantity(0, "Pa"), Quantity(0, "Pa")))),
        P.ROLES, P.DiscretizationSpec(degree=1), P.SOLVER))
    assert fx.succeeded
    u_ccx = np.asarray(ccx.arrays["displacement"][1])
    u_fx = np.asarray(fx.field.values)
    right = np.isclose(mesh.coordinates[:, 0], mesh.coordinates[:, 0].max())
    decl = ComparisonDeclaration("x-displacement of the loaded (right) edge nodes", "m",
                                 "identity: both solvers use the same mesh nodes (P1 / CPS3 on one BIG 7 mesh)",
                                 Quantity(1e-9, "m"), 0.02, f"plane stress, mesh {mesh.digest[:12]}, 10 kPa edge traction")
    edge = OutputSelection(rows=tuple(int(i) for i in np.flatnonzero(right)), component=0)
    cmp = compare_providers(decl, fx, "displacement", ccx, "displacement", a_select=edge, b_select=edge)
    assert cmp.max_absolute == float(np.abs(u_fx[right, 0] - u_ccx[right, 0]).max())  # the records' own values
    print("PROOF_E", cmp.to_dict(), "metrics", dict(ccx.metrics))
    assert cmp.to_dict()["classification"] == "solver_corroboration_not_validation"
    assert cmp.within_tolerance, cmp.to_dict()
    # a changed case (thickness) changes the generated deck and therefore the execution identity
    thicker = PlaneStressProblem(mesh, mats, Quantity(2 * thickness.to("m").magnitude, "m"), "left", "right", traction)
    assert CalculixProvider(REG).execute(thicker).identity.digest != ccx.identity.digest


def test_calculix_stale_dat_in_the_workspace_is_never_the_result():
    _, mesh, _, _, rE, rnu = _case()
    mats = tuple(RegionMaterial(r, e, n) for r, e, n in zip(("left_plate", "right_plate"), rE, rnu))
    stale = "displacements (vx,vy,vz) for set N_ALL and time  0.1000000E+01\n\n" + "".join(
        f"{i + 1} 9.9E+09 9.9E+09 0.0\n" for i in range(mesh.node_count))
    # the solver fails (clamped group missing -> refused before launch) ...
    with pytest.raises(Exception):
        CalculixProvider(REG).execute(PlaneStressProblem(mesh, mats, Quantity(5, "mm"), "no_such_group", "right", (Quantity(1, "Pa"), Quantity(0, "Pa"))))
    # ... and a job that runs with a pre-existing foreign job.dat only admits the file ccx itself rewrote
    rec = CalculixProvider(REG).execute(PlaneStressProblem(mesh, mats, Quantity(5, "mm"), "left", "right", (Quantity(1e4, "Pa"), Quantity(0, "Pa"))),
                                        preexisting={"job.dat": stale.encode()})
    assert rec.succeeded and np.abs(np.asarray(rec.arrays["displacement"][1])).max() < 1.0  # not the 9.9E+09 stale values
