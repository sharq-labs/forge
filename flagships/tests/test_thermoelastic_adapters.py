"""Thermo-elastic plane-stress case record, stress recovery and the CalculiX / Code_Aster deck generators - no executable needed."""

from __future__ import annotations

import hashlib

import numpy as np
import pytest

from engcore.pde.cases import RegionExpansion, RegionMaterial, Restraint, ThermoelasticPlaneStressProblem
from engcore.pde.postprocess import cross_section_force, plane_stress_recovery
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.units.quantity import Quantity
from forge_flagships import thermo_mechanical as tm

forge_calculix = pytest.importorskip("forge_calculix")
forge_code_aster = pytest.importorskip("forge_code_aster")


def problem(temperature=None, restraints=None, nx=4, ny=2):
    mesh = tm.plate_mesh(nx, ny)
    mat = tm.plate_material()
    t = np.full(mesh.node_count, 333.15) if temperature is None else temperature
    return ThermoelasticPlaneStressProblem(
        mesh, (RegionMaterial("plate", mat.youngs, mat.poisson),), (RegionExpansion("plate", mat.expansion),), tm.THICKNESS,
        restraints or (Restraint("left", (0,)), Restraint("bottom", (1,))), tuple(float(v) for v in t), "K", hashlib.sha256(np.asarray(t).tobytes()).hexdigest(), Quantity(tm.T_REF, "K"))


def test_the_case_refuses_missing_supports_missing_or_wrong_temperature_and_unbound_expansion():
    mesh, mat = tm.plate_mesh(4, 2), tm.plate_material()
    common = dict(mesh=mesh, materials=(RegionMaterial("plate", mat.youngs, mat.poisson),), expansions=(RegionExpansion("plate", mat.expansion),), thickness=tm.THICKNESS,
                  temperature_unit="K", temperature_digest=hashlib.sha256(b"t").hexdigest(), reference_temperature=Quantity(tm.T_REF, "K"))
    with pytest.raises(InvalidScientificProblem, match="no restraint"):
        ThermoelasticPlaneStressProblem(restraints=(), temperature=tuple([300.0] * mesh.node_count), **common)
    with pytest.raises(InvalidScientificProblem, match="one value per mesh node"):
        ThermoelasticPlaneStressProblem(restraints=(Restraint("left", (0,)),), temperature=(300.0,), **common)
    with pytest.raises(InvalidScientificProblem, match="non-finite"):
        ThermoelasticPlaneStressProblem(restraints=(Restraint("left", (0,)),), temperature=tuple([float("nan")] * mesh.node_count), **common)
    with pytest.raises(InvalidScientificProblem):
        ThermoelasticPlaneStressProblem(restraints=(Restraint("no_such_group", (0,)),), temperature=tuple([300.0] * mesh.node_count), **common)    # a support is never guessed
    with pytest.raises(InvalidScientificProblem, match="thermal_expansion"):
        RegionExpansion("plate", mat.youngs)                                        # a Young's modulus record is not an expansion coefficient
    with pytest.raises(InvalidScientificProblem):
        Restraint("left", (0, 0))                                                    # each component once


def test_the_problem_identity_moves_with_the_temperature_field_and_the_restraints():
    a, b = problem(), problem(np.full(tm.plate_mesh(4, 2).node_count, 340.0))
    assert a.to_dict()["temperature_digest"] != b.to_dict()["temperature_digest"]
    c = problem(restraints=(Restraint("left", (0,)), Restraint("right", (0,)), Restraint("bottom", (1,))))
    assert c.to_dict()["restraints"] != a.to_dict()["restraints"]


def test_stress_recovery_reproduces_the_two_exact_uniform_temperature_limits_and_refuses_an_unstated_thermal_load():
    mesh, mat = tm.plate_mesh(4, 2), tm.plate_material()
    E, nu, alpha = mat.youngs.value.value.magnitude, mat.poisson.value.value.magnitude, mat.expansion.value.value.magnitude
    dT = 40.0
    T = np.full(mesh.node_count, tm.T_REF + dT)
    free = alpha * dT * np.asarray(mesh.coordinates)
    s = plane_stress_recovery(mesh, free, E, nu, alpha, T, tm.T_REF)
    assert np.abs(s.sxx).max() < 1e-3 and np.abs(s.syy).max() < 1e-3 and np.abs(s.von_mises).max() < 1e-3       # free growth is stress free
    s = plane_stress_recovery(mesh, np.zeros((mesh.node_count, 2)), E, nu, alpha, T, tm.T_REF)
    assert s.sxx == pytest.approx(-E * alpha * dT / (1 - nu), rel=1e-12)                                          # fully clamped in both directions (biaxial)
    with pytest.raises(InvalidScientificProblem, match="temperature field and the reference"):
        plane_stress_recovery(mesh, free, E, nu, alpha)                                                            # an expansion coefficient needs its temperature
    with pytest.raises(InvalidScientificProblem, match="finite nodal displacements"):
        plane_stress_recovery(mesh, np.full((mesh.node_count, 2), np.nan), E, nu)


def test_the_cross_section_force_of_a_uniform_stress_is_stress_times_the_full_section():
    mesh = tm.plate_mesh(8, 2)
    sxx = np.full(len(mesh.cells), -5.0e7)
    f = cross_section_force(mesh, sxx, 0.5 * tm.LENGTH, tm.THICKNESS.to("m").magnitude, tm.HALF_WIDTH)
    assert f == pytest.approx(-5.0e7 * tm.THICKNESS.to("m").magnitude * 2 * tm.HALF_WIDTH, rel=1e-12)


def test_calculix_deck_carries_the_expansion_law_restraints_and_every_nodal_temperature():
    p = problem()
    deck = forge_calculix.generate_thermoelastic_deck(p, "tag")
    assert "*EXPANSION, ZERO=293.15" in deck and f"{tm.ALPHA!r}" in deck and "*ELASTIC" in deck and "*INITIAL CONDITIONS, TYPE=TEMPERATURE" in deck
    assert "N_RESTRAINT_0, 1, 1, 0.0" in deck and "N_RESTRAINT_1, 2, 2, 0.0" in deck                              # left: u_x, bottom: u_y
    temp_lines = deck.split("*TEMPERATURE\n")[1].split("*NODE PRINT")[0].strip().splitlines()
    assert len(temp_lines) == p.mesh.node_count and all(l.endswith("333.15") for l in temp_lines)
    assert "*CLOAD" not in deck                                                                                    # there is no traction in a thermal case


def test_code_aster_files_carry_the_material_law_the_nodal_field_and_one_node_group_per_restraint():
    p = problem(restraints=(Restraint("left", (0,)), Restraint("right", (0,)), Restraint("bottom", (1,))))
    comm = forge_code_aster.generate_thermoelastic_comm(p, "tag")
    mesh = forge_code_aster.generate_thermoelastic_mesh(p)
    assert "ALPHA=" in comm and "AFFE_VARC=_F(TOUT='OUI', NOM_VARC='TEMP'" in comm and "VALE_REF=293.15" in comm and comm.count("NOM_CMP='TEMP'") == p.mesh.node_count
    assert "GROUP_NO='RESTR_0', DX=0.0" in comm and "GROUP_NO='RESTR_2', DY=0.0" in comm and "SIEF_ELGA" in comm
    assert all(f"GROUP_NO\nRESTR_{i}\n" in mesh for i in range(3)) and "TRIA3" in mesh


def test_code_aster_stress_table_is_parsed_and_an_incomplete_table_is_refused():
    text = "\n".join(["CHAMP PAR ELEMENT", "1 SIXX SIYY SIXY", "        1 -1.0E+06 2.0E+05 3.0E+04", "2 SIXX SIYY SIXY", "        1 -2.0E+06 0.0E+00 0.0E+00"])
    s = forge_code_aster.parse_element_stress(text, 2)
    assert s.shape == (2, 3) and s[0, 0] == pytest.approx(-1.0e6) and s[1, 0] == pytest.approx(-2.0e6)
    with pytest.raises(Exception, match="covers 1 of 2 elements"):
        forge_code_aster.parse_element_stress("\n".join(text.splitlines()[:3]), 2)
