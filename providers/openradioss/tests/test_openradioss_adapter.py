"""Big Rock H: OpenRadioss adapter -- deterministic decks, parser contracts and refusal (provider-free), plus a gated run.

Text fixtures below are PARSER CONTRACTS: declared strings with the structure
the parsers must accept or refuse.  None of them is, or is presented as, an
OpenRadioss result.
"""

from __future__ import annotations

import pytest

from engcore.providers import Availability, ProviderRefusal, ProviderRegistry, ProviderStatus
from engcore.scientific.fields import CellType
from engcore.scientific.units.quantity import Quantity
from engcore.spatial.mesh import CoordinateFrame, GroupKind, PhysicalGroup, SpatialMesh


def one_tet(scale=0.01):
    return SpatialMesh(coordinates=[[0, 0, 0], [scale, 0, 0], [0, scale, 0], [0, 0, scale]], cells=[[0, 1, 2, 3]],
                       cell_type=CellType.TETRAHEDRON, frame=CoordinateFrame("impact", 3), cell_tags=[1],
                       groups=(PhysicalGroup("body", GroupKind.CELLS, 1),))


def case(**kw):
    from forge_openradioss import ElasticPlasticMaterial, ExplicitImpactCase, RigidWall

    base = dict(
        case_id="bar_impact", mesh=one_tet(),
        material=ElasticPlasticMaterial("al6061", Quantity(2.7, "g/cm^3"), Quantity(69, "GPa"), Quantity(0.33, "dimensionless"),
                                        Quantity(276, "MPa"), Quantity(500, "MPa"), "handbook:asm-al6061-t6"),
        initial_velocity=(Quantity(0, "m/s"), Quantity(0, "m/s"), Quantity(-50, "m/s")),
        wall=RigidWall((Quantity(0, "m"), Quantity(0, "m"), Quantity(-0.001, "m")), (0.0, 0.0, 1.0)),
        end_time=Quantity(0.1, "ms"), output_interval=Quantity(1, "us"), histories=("kinetic_energy", "internal_energy"),
        solver_options={"timestep_scale_factor": 0.67})
    base.update(kw)
    return ExplicitImpactCase(**base)


def test_decks_are_deterministic_si_and_bound_to_content():
    from forge_openradioss import engine_deck, starter_deck

    deck = starter_deck(case())
    assert deck == starter_deck(case())
    assert "/MAT/PLAS_JOHNS/1" in deck and "/TETRA4/1" in deck and "/RWALL/PLANE/1" in deck
    assert "2.7000000000E+03" in deck and "6.9000000000E+10" in deck  # kg/m^3 and Pa, converted from g/cm^3 and GPa
    assert "-5.0000000000E+01" in deck
    assert starter_deck(case(mesh=one_tet(0.02))) != deck
    assert "1.0000000000E-04" in engine_deck(case())


@pytest.mark.parametrize("kw, match", [
    ({"solver_options": {}}, "never used silently"),
    ({"histories": ("plastic_strain",)}, "subset"),
    ({"case_id": "bad id"}, "short identifier"),
    ({"output_interval": Quantity(1, "s")}, "exceeds"),
])
def test_case_refusals(kw, match):
    with pytest.raises(ProviderRefusal, match=match):
        case(**kw)


def test_material_and_mesh_refusals():
    from forge_openradioss import ElasticPlasticMaterial

    with pytest.raises(ProviderRefusal, match="source reference"):
        case(material=ElasticPlasticMaterial("m", Quantity(1, "kg/m^3"), Quantity(1, "GPa"), Quantity(0.3, "dimensionless"),
                                             Quantity(1, "MPa"), Quantity(1, "MPa"), " "))
    with pytest.raises(ProviderRefusal, match="softening"):
        case(material=ElasticPlasticMaterial("m", Quantity(1, "kg/m^3"), Quantity(1, "GPa"), Quantity(0.3, "dimensionless"),
                                             Quantity(1, "MPa"), Quantity(-1, "MPa"), "src"))
    tri = SpatialMesh(coordinates=[[0, 0], [1, 0], [0, 1]], cells=[[0, 1, 2]], cell_type=CellType.TRIANGLE,
                      frame=CoordinateFrame("p", 2), cell_tags=[1], groups=(PhysicalGroup("s", GroupKind.CELLS, 1),))
    with pytest.raises(ProviderRefusal, match="linear-tetrahedron"):
        case(mesh=tri)


def test_listing_parsers_require_explicit_normal_termination():
    from forge_openradioss import parse_engine_listing, parse_starter_listing

    assert parse_starter_listing("...\n NORMAL TERMINATION\n") == (True, "normal termination")
    assert parse_starter_listing(" ERROR ID :     55\n ERROR ID : 55\n NORMAL TERMINATION")[0] is False
    assert parse_starter_listing("truncated")[0] is False
    assert parse_engine_listing("CYCLE 100\n NORMAL TERMINATION\n")[0] is True
    assert parse_engine_listing("CYCLE 3\n ERROR TERMINATION\n")[0] is False
    assert parse_engine_listing("CYCLE 3\n")[0] is False


def test_time_history_parser_contract():
    from forge_openradioss import parse_time_history_csv

    text = "TIME,KE,IE,TE\n0,1.0,0.0,1.0\n5e-5,0.6,0.4,1.0\n1e-4,0.2,0.8,1.0\n"
    out = parse_time_history_csv(text, ("kinetic_energy", "internal_energy"), 1e-4)
    assert out["kinetic_energy"].values == (1.0, 0.6, 0.2) and out["internal_energy"].unit == "J"
    with pytest.raises(ProviderRefusal, match="lacks columns"):
        parse_time_history_csv("TIME,KE\n0,1\n1e-4,1\n", ("internal_energy",), 1e-4)
    with pytest.raises(ProviderRefusal, match="truncated run"):
        parse_time_history_csv(text, ("kinetic_energy",), 2e-4)
    with pytest.raises(ProviderRefusal, match="non-finite"):
        parse_time_history_csv("TIME,KE\n0,nan\n1e-4,1\n", ("kinetic_energy",), 1e-4)
    with pytest.raises(ProviderRefusal, match="non-numeric"):
        parse_time_history_csv("TIME,KE\n0,x\n1e-4,1\n", ("kinetic_energy",), 1e-4)


def _statuses():
    import forge_openradioss.descriptor as d

    reg = ProviderRegistry()
    d.register(reg)
    return reg.status("openradioss_starter"), reg.status("openradioss"), reg.status("openradioss_th_to_csv")


def test_unavailable_openradioss_refuses_rather_than_synthesizing():
    from forge_openradioss import OpenRadiossProvider
    from forge_openradioss.descriptor import ENGINE, STARTER, TH_TO_CSV

    gone = lambda c: ProviderStatus(c, Availability.UNAVAILABLE, reason=f"executable {c.package!r} not found")  # noqa: E731
    provider = OpenRadiossProvider(gone(STARTER), gone(ENGINE), gone(TH_TO_CSV))
    with pytest.raises(ProviderRefusal, match="nothing is synthesized"):
        provider.execute(case())
    with pytest.raises(ProviderRefusal, match="registry status"):
        OpenRadiossProvider(gone(ENGINE), gone(ENGINE), gone(TH_TO_CSV))


@pytest.mark.skipif(not all(s.available for s in _statuses()), reason="OpenRadioss unavailable")
def test_real_impact_run_conserves_energy_before_contact():  # pragma: no cover - needs OpenRadioss
    from forge_openradioss import OpenRadiossProvider

    rec = OpenRadiossProvider(*_statuses()).execute(case(wall=__import__("forge_openradioss").RigidWall(
        (Quantity(0, "m"), Quantity(0, "m"), Quantity(-1.0, "m")), (0.0, 0.0, 1.0))))
    assert rec.succeeded, rec.reason
    ke = rec.series_for("kinetic_energy").values
    assert ke[-1] == pytest.approx(ke[0], rel=1e-3)  # free flight: no work done before the wall is reached
