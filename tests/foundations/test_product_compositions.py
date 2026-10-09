"""Big Rocks P/Q/R: drone, vehicle, motor and HVAC composed from ONE generic product-template contract."""

from __future__ import annotations

import math

import pytest

from engcore.providers import ProviderRegistry, default_registry
from engcore.scientific.units.quantity import Quantity
from engcore.systems.assembly import CompositionLevel
from engcore.systems.products import (
    IN_REPOSITORY, TEMPLATES, ParticipantReadiness, RequiredInput, TemplateRefusal, capability_report, drone_template, hover_screening,
)


@pytest.mark.parametrize("name", sorted(TEMPLATES))
def test_every_product_composes_from_generic_records_with_every_input_unknown(name):
    t = TEMPLATES[name]()
    assert t.assembly.level(t.assembly.root) is CompositionLevel.SYSTEM
    assert set(t.unknown_inputs()) == {i.input_id for i in t.inputs}  # no hidden defaults
    assert t.digest == TEMPLATES[name]().digest
    report = {c.participant_id: c for c in capability_report(t, ProviderRegistry(), in_repository=IN_REPOSITORY)}
    assert all(c.readiness is not ParticipantReadiness.READY or not c.missing_inputs for c in report.values())
    for c in report.values():
        if not t.participants[[p.participant_id for p in t.participants].index(c.participant_id)].providers:
            assert c.readiness is ParticipantReadiness.NO_ADAPTER


def test_capability_report_distinguishes_no_adapter_missing_inputs_and_providers():
    t = TEMPLATES["vehicle"]()
    report = {c.participant_id: c for c in capability_report(t, default_registry(), in_repository=IN_REPOSITORY)}
    assert report["drive_motor_em"].readiness is ParticipantReadiness.NO_ADAPTER
    assert report["body_meshing"].readiness is ParticipantReadiness.READY  # in-repository Gmsh path, no inputs needed
    crash = report["crash"]
    assert crash.readiness in (ParticipantReadiness.BLOCKED_BY_PROVIDER, ParticipantReadiness.BLOCKED_BY_INPUTS)
    assert "available is not qualified" in report["body_meshing"].reason


def test_drone_hover_screening_refuses_unknown_inputs_and_matches_momentum_theory():
    t = drone_template()
    with pytest.raises(TemplateRefusal, match="never defaulted"):
        hover_screening(t)
    declared = t.with_inputs({
        "takeoff_mass": (Quantity(2.0, "kg"), "spec:mass-budget-r3"), "rotor_diameter": (Quantity(10, "inch"), "catalog:prop-10x4.5"),
        "rotor_count": (Quantity(4, "dimensionless"), "template"), "air_density": (Quantity(1.225, "kg/m^3"), "env:isa-sea-level"),
        "gravity": (Quantity(9.80665, "m/s^2"), "env:standard-gravity")})
    r = hover_screening(declared)
    thrust, area = 2.0 * 9.80665, 4 * math.pi * (0.254 / 2) ** 2
    assert r["ideal_induced_power"].magnitude_in("W") == pytest.approx(thrust ** 1.5 / math.sqrt(2 * 1.225 * area))
    assert r["classification"] == "ideal_momentum_theory_lower_bound_not_validated" and r["uncertainty"] == "UNKNOWN"
    with pytest.raises(TemplateRefusal, match="source reference"):
        RequiredInput("x", "drone", "kg", "d", Quantity(1, "kg"))
    with pytest.raises(TemplateRefusal, match="undeclared"):
        t.with_inputs({"wingspan": (Quantity(1, "m"), "s")})


def test_drone_structure_placements_exist_only_when_declared():
    bare = drone_template()
    with pytest.raises(Exception, match="UNKNOWN"):
        bare.assembly.world_transform("arm_1")
    placed = drone_template(arm_length=Quantity(0.25, "m"))
    assert placed.assembly.point_world("arm_2.tip").apply((0, 0, 0)) == pytest.approx((0.0, 0.25, 0.0), abs=1e-12)
    assert placed.assembly.kinematic_dof() == 4  # four rotor revolutes; everything else fixed
    with pytest.raises(TemplateRefusal):
        drone_template(rotor_count=2)


def test_product_names_stay_out_of_generic_layers():
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[2] / "src" / "engcore"
    for pkg in ("scientific", "spatial", "design", "providers"):
        for path in (root / pkg).rglob("*.py"):
            text = path.read_text(encoding="utf-8").lower()
            for word in ("drone", "hvac", "vehicle"):
                assert word not in text, f"{word!r} leaks into generic {path.relative_to(root)}"
