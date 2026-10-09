"""Big Rock G: OpenVSP adapter -- canonical translation and refusal (provider-free), plus a gated real build."""

from __future__ import annotations

import pytest

from engcore.providers import Availability, ProviderRefusal, ProviderRegistry, ProviderStatus
from engcore.scientific.units.quantity import Quantity


def q(v, u="m"):
    return Quantity(v, u)


def aircraft(span=q(10.0), unit="m"):
    from forge_openvsp import BodyOfRevolution, LiftingSurface, Position, VSPModelRequest

    s = 1000.0 if unit == "mm" else 1.0
    L = lambda v: Quantity(v * s, unit)  # noqa: E731
    origin = Position(L(0), L(0), L(0))
    return VSPModelRequest("uav", (
        BodyOfRevolution("fuselage", L(4.0), L(0.5), origin),
        LiftingSurface("wing", span if unit == "m" else Quantity(span.magnitude * s, unit), L(1.2), L(0.6), q(5, "degree"), q(3, "degree"),
                       q(0.12, "dimensionless"), Position(L(1.5), L(0), L(0.1))),
        LiftingSurface("fin", L(1.0), L(0.8), L(0.4), q(30, "degree"), q(0, "degree"), q(0.10, "dimensionless"),
                       Position(L(3.6), L(0), L(0.2)), vertical=True, symmetric=False),
        BodyOfRevolution("pod", L(0.8), L(0.2), Position(L(1.5), L(1.5), L(-0.2)), role="pod"),
    ))


def test_operation_list_is_deterministic_unit_canonical_and_identity_bearing():
    from forge_openvsp import operations, translation_digest

    ops = operations(aircraft())
    assert ops == operations(aircraft())
    assert translation_digest(aircraft()) == translation_digest(aircraft(unit="mm"))
    assert translation_digest(aircraft(span=q(11.0))) != translation_digest(aircraft())
    assert ops[0] == ["VSPRenew"] and ops[-1][0] == "ExportFile"
    assert ["SetParmVal", "wing", "Span", "XSec_1", 5.0] in ops  # symmetric: half span per side
    assert ["SetParmVal", "fuselage", "FineRatio", "Design", 8.0] in ops
    assert ["SetParmVal", "fin", "X_Rel_Rotation", "XForm", 90.0] in ops
    assert ["SetParmVal", "wing", "Sweep", "XSec_1", pytest.approx(5.0)] in ops


@pytest.mark.parametrize("change, match", [
    (lambda F: F.BodyOfRevolution("b", q(1), q(2), F.Position(q(0), q(0), q(0))), "smaller than length"),
    (lambda F: F.LiftingSurface("w", q(10), q(1), q(2), q(0, "degree"), q(0, "degree"), q(0.1, "dimensionless"), F.Position(q(0), q(0), q(0))),
     "tip chord larger"),
    (lambda F: F.LiftingSurface("w", q(10), q(1), q(0.5), q(0.1, "dimensionless"), q(0, "degree"), q(0.1, "dimensionless"),
                                F.Position(q(0), q(0), q(0))), "angle Quantity"),
    (lambda F: F.LiftingSurface("w", q(10), q(1), q(0.5), q(80, "degree"), q(0, "degree"), q(0.1, "dimensionless"),
                                F.Position(q(0), q(0), q(0))), "declared range"),
    (lambda F: F.BodyOfRevolution("b", 4.0, q(0.5), F.Position(q(0), q(0), q(0))), "length Quantity"),
])
def test_translation_refuses_out_of_scope_declarations(change, match):
    import forge_openvsp as F

    with pytest.raises(ProviderRefusal, match=match):
        F.operations(F.VSPModelRequest("x", (change(F),)))


def _status():
    import forge_openvsp.descriptor as d

    reg = ProviderRegistry()
    d.register(reg)
    return reg.status("openvsp")


def test_unavailable_openvsp_refuses_and_unitless_output_is_refused(tmp_path):
    from forge_openvsp import OpenVSPProvider
    from forge_openvsp.descriptor import CAPABILITY

    provider = OpenVSPProvider(ProviderStatus(CAPABILITY, Availability.UNAVAILABLE, reason="python module 'openvsp' is not installed"))
    with pytest.raises(ProviderRefusal, match="no geometry is synthesized"):
        provider.build(aircraft())
    with pytest.raises(ProviderRefusal, match="no STEP file"):
        provider._result(aircraft(), str(tmp_path / "absent.stp"))
    (tmp_path / "bare.stp").write_text("ISO-10303-21;\nDATA;\nENDSEC;\n")
    with pytest.raises(ProviderRefusal, match="never guessed"):
        provider._result(aircraft(), str(tmp_path / "bare.stp"))


@pytest.mark.skipif(not _status().available, reason="OpenVSP unavailable")
def test_real_openvsp_build_meshes_through_the_gmsh_adapter(tmp_path):  # pragma: no cover - needs OpenVSP + Gmsh
    from forge_openvsp import OpenVSPProvider

    from engcore.spatial import Body, FrameDefinition, GeometryModel, GmshMeshRequest, Region, Shape, mesh_geometry

    result = OpenVSPProvider(_status()).build(aircraft(), str(tmp_path))
    assert result.source.declared_length_unit in ("m", "mm") and result.receipt.provider_id == "openvsp"
    model = GeometryModel("uav", "1", 3, (FrameDefinition("world"),), (Body("airframe", Shape.imported(result.source), "world"),),
                          (Region("airframe", ("airframe",)),))
    meshed = mesh_geometry(model, GmshMeshRequest(size=q(0.2), frame_id="body", files={result.source.file_digest: result.step_path}))
    assert meshed.mesh.cell_count > 0
