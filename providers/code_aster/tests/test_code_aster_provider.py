"""Second-wave provider: real Code_Aster on the same BIG 7 plate / BIG 5 records as CalculiX and FEniCSx (three-way corroboration)."""

from __future__ import annotations

import importlib.util

import numpy as np
import pytest

from engcore.materials import MaterialState
from engcore.pde.cases import PlaneStressProblem, RegionMaterial
from engcore.providers import ComparisonDeclaration, OutputSelection, ProviderRegistry, compare_providers
from engcore.scenarios import NamedQuantity
from engcore.scientific.units.quantity import Quantity
from engcore.spatial import RegionMaterialMap, gmsh_available
from forge_code_aster import CodeAsterProvider, descriptor

REG = ProviderRegistry()
descriptor.register(REG)
OK = REG.status("code_aster").available and gmsh_available()[0]
pytestmark = pytest.mark.skipif(not OK, reason="Code_Aster or Gmsh unavailable")


def _case():
    spec = importlib.util.spec_from_file_location("pde_fx_ca", "providers/fenicsx/tests/test_pde_fenicsx.py")
    P = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(P)
    mesh = P.plate()
    room = NamedQuantity("temperature", Quantity(293.15, "K"))
    binding = RegionMaterialMap(mesh, ((mesh.region("left_plate"), MaterialState(P.M.ALLOY, (room,), "solid")),
                                       (mesh.region("right_plate"), MaterialState(P.M.BOARD, (room,)))))
    sets = P.elastic_property_sets()
    _, rE = binding.property_field(sets, "youngs_modulus", "Pa", "E")
    _, rnu = binding.property_field(sets, "poisson_ratio", "dimensionless", "nu")
    mats = tuple(RegionMaterial(r, e, n) for r, e, n in zip(("left_plate", "right_plate"), rE, rnu))
    return PlaneStressProblem(mesh, mats, Quantity(5, "mm"), "left", "right", (Quantity(1e4, "Pa"), Quantity(0, "Pa")))


def test_code_aster_executes_and_corroborates_calculix_on_the_same_records():
    problem = _case()
    ca = CodeAsterProvider(REG).execute(problem)
    assert ca.succeeded, ca.reason
    assert "C_PLAN" in ca.artifacts["case.comm"] and "GROUP_NO" in ca.artifacts["mesh.mail"]
    try:
        from forge_calculix import CalculixProvider, descriptor as ccd
    except ImportError:
        pytest.skip("CalculiX adapter not on the path")
    reg = ProviderRegistry()
    ccd.register(reg)
    if not reg.status("calculix").available:
        pytest.skip("CalculiX unavailable")
    cc = CalculixProvider(reg).execute(problem)
    right = np.isclose(problem.mesh.coordinates[:, 0], problem.mesh.coordinates[:, 0].max())
    decl = ComparisonDeclaration("x-displacement of the loaded (right) edge nodes", "m", "identity: same mesh nodes", Quantity(1e-9, "m"), 0.02,
                                 f"plane stress, mesh {problem.mesh.digest[:12]}, 10 kPa edge traction")
    edge = OutputSelection(rows=tuple(int(i) for i in np.flatnonzero(right)), component=0)
    cmp = compare_providers(decl, ca, "displacement", cc, "displacement", a_select=edge, b_select=edge)
    print("PROOF_E_CA_CCX", cmp.to_dict(), dict(ca.metrics))
    assert cmp.within_tolerance
