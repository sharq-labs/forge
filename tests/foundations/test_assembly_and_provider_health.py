"""Big Rocks E/F: product/assembly topology on SystemDefinition; provider health, qualification and probes."""

from __future__ import annotations

import os
import stat

import pytest

from engcore.materials import MaterialIdentity
from engcore.providers import Availability, ProviderCapability, ProviderStatus
from engcore.providers.health import (
    ProviderHealth, ProviderQualification, assess_health, probe_executable, solver_identity_from_probe, status_from_probe,
)
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.twins import TwinReference
from engcore.scientific.units.quantity import Quantity
from engcore.spatial.geometry import Body, FrameDefinition, GeometryModel, MaterialBinding, Region, Shape, Transform
from engcore.systems.assembly import (
    AssemblyRefusal, AssemblyTopology, ConnectionPoint, GeometryOwnership, InstanceLevel, InterfaceDeclaration,
    InterfaceKind, JointDeclaration, JointKind, MaterialOwnership, Placement, ReplaceableSlot, StateOwnership,
)
from engcore.systems.topology import ComponentDefinition, ComponentInstance, SystemDefinition

ALU = MaterialIdentity("aluminium", specification="EN AW-6061", grade="T6")
CFRP = MaterialIdentity("cfrp", specification="T700/epoxy", grade="UD")


def m(v):
    return Quantity(v, "m")


def defs():
    return tuple(ComponentDefinition(c, "1") for c in ("product", "arm_assy", "arm", "motor_a", "motor_b", "hub"))


def system(motor="motor_a"):
    tw = lambda n: TwinReference(f"twin-{n}", "1")  # noqa: E731
    inst = (
        ComponentInstance("root", "product", "1", tw("root")),
        ComponentInstance("arm_assy", "arm_assy", "1", tw("arm_assy"), parent_id="root"),
        ComponentInstance("arm", "arm", "1", tw("arm"), parent_id="arm_assy"),
        ComponentInstance("motor", motor, "1", tw(motor), parent_id="arm_assy"),
        ComponentInstance("hub", "hub", "1", tw("hub"), parent_id="root"),
    )
    return SystemDefinition("rig", "1", tuple(d for d in defs() if d.component_id in {i.definition_id for i in inst}), inst)


def topology(**kw):
    base = dict(
        system=system(),
        levels=(InstanceLevel("root", "system"), InstanceLevel("arm_assy", "assembly"), InstanceLevel("arm", "part"),
                InstanceLevel("motor", "component"), InstanceLevel("hub", "component")),
        placements=(Placement("arm_assy", Transform.from_quantities((m(0.2), m(0), m(0)))),
                    Placement("arm", Transform()), Placement("motor", Transform.from_quantities((m(0.1), m(0), m(0.02)))),
                    Placement("hub", Transform())),
        points=(ConnectionPoint("hub.mount", "hub"), ConnectionPoint("arm.root", "arm"), ConnectionPoint("arm.tip", "arm", Transform.from_quantities((m(0.1), m(0), m(0)))),
                ConnectionPoint("motor.base", "motor")),
        joints=(JointDeclaration("hinge", JointKind.REVOLUTE, "hub.mount", "arm.root", axis=(0, 0, 1),
                                 lower=Quantity(-30, "degree"), upper=Quantity(30, "degree")),
                JointDeclaration("motor_mount", JointKind.FIXED, "arm.tip", "motor.base")),
        interfaces=(InterfaceDeclaration("motor_heat", InterfaceKind.THERMAL, "arm.tip", "motor.base"),),
        materials=(MaterialOwnership("arm", CFRP),),
        states=(StateOwnership("motor.winding_temperature", "motor"),),
        slots=(ReplaceableSlot("motor_slot", "motor", (("motor_a", "1"), ("motor_b", "1")), ("motor.base",)),),
    )
    base.update(kw)
    return AssemblyTopology(**base)


def test_hierarchy_levels_placements_and_world_pose():
    t = topology()
    assert t.root == "root" and t.children("arm_assy") == ("arm", "motor")
    assert t.path("motor") == ("root", "arm_assy", "motor")
    assert t.world_transform("motor").apply((0, 0, 0)) == pytest.approx((0.3, 0, 0.02))
    assert t.point_world("arm.tip").apply((0, 0, 0)) == pytest.approx((0.3, 0, 0))
    assert t.kinematic_dof() == 1 and t.owner_of_state("motor.winding_temperature") == "motor"
    no_pose = topology(placements=(Placement("arm_assy", Transform()),))
    with pytest.raises(AssemblyRefusal, match="UNKNOWN"):
        no_pose.world_transform("motor")


def test_round_trip_and_variant_identity():
    t = topology()
    assert AssemblyTopology.from_dict(t.to_dict()).digest == t.digest
    swapped = t.replace("motor_slot", ComponentDefinition("motor_b", "1"), TwinReference("twin-motor_b", "1"))
    assert swapped.digest != t.digest and swapped.instance("motor").definition_id == "motor_b"
    assert t.instance("motor").definition_id == "motor_a"  # the original variant is unchanged
    assert swapped.joints == t.joints and swapped.interfaces == t.interfaces
    with pytest.raises(AssemblyRefusal, match="not allowed"):
        t.replace("motor_slot", ComponentDefinition("hub", "1"), TwinReference("x", "1"))


@pytest.mark.parametrize("kw, match", [
    ({"levels": (InstanceLevel("root", "system"), InstanceLevel("arm_assy", "part"), InstanceLevel("arm", "part"),
                 InstanceLevel("motor", "component"), InstanceLevel("hub", "component"))}, "deepen"),
    ({"levels": (InstanceLevel("root", "assembly"), InstanceLevel("arm_assy", "part"), InstanceLevel("arm", "part"),
                 InstanceLevel("motor", "part"), InstanceLevel("hub", "part"))}, "SYSTEM"),
    ({"levels": (InstanceLevel("root", "system"),)}, "exactly one composition level"),
    ({"placements": (Placement("root", Transform.from_quantities((m(1), m(0), m(0)))),)}, "identity"),
    ({"joints": (JointDeclaration("j", JointKind.FIXED, "hub.mount", "nowhere"),)}, "unknown connection point"),
    ({"joints": (JointDeclaration("a", JointKind.FIXED, "hub.mount", "arm.root"), JointDeclaration("b", JointKind.FIXED, "motor.base", "arm.root"))},
     "closed kinematic loops"),
    ({"joints": (JointDeclaration("j", JointKind.FIXED, "arm.root", "arm.tip"),)}, "to itself"),
    ({"states": (StateOwnership("s", "ghost"),)}, "unknown instance"),
    ({"slots": (ReplaceableSlot("s", "motor", (("motor_b", "1"),)),)}, "current definition"),
    ({"slots": (ReplaceableSlot("s", "motor", (("motor_a", "1"),), ("motor.shaft",)),)}, "requires points"),
])
def test_assembly_refusals(kw, match):
    with pytest.raises(AssemblyRefusal, match=match):
        topology(**kw)


@pytest.mark.parametrize("build, match", [
    (lambda: JointDeclaration("j", JointKind.REVOLUTE, "a", "b"), "needs an axis"),
    (lambda: JointDeclaration("j", JointKind.PRISMATIC, "a", "b", axis=(0, 0, 2)), "unit 3-vector"),
    (lambda: JointDeclaration("j", JointKind.PRISMATIC, "a", "b", axis=(0, 0, 1), lower=Quantity(1, "degree")), "joint coordinate"),
    (lambda: JointDeclaration("j", JointKind.COMPLIANT, "a", "b"), "never defaulted"),
    (lambda: JointDeclaration("j", JointKind.FIXED, "a", "b", compliance_ref="k"), "only a compliant"),
    (lambda: JointDeclaration("j", JointKind.SPHERICAL, "a", "b", axis=(0, 0, 1)), "takes no axis"),
])
def test_joint_declarations_fail_closed(build, match):
    with pytest.raises(AssemblyRefusal, match=match):
        build()


def test_compliant_joint_makes_dof_unknown_not_zero():
    t = topology(joints=(JointDeclaration("bushing", JointKind.COMPLIANT, "hub.mount", "arm.root", compliance_ref="model:bushing-k"),))
    assert t.kinematic_dof() is None


def test_geometry_and_material_ownership_cross_checked():
    g = GeometryModel("arm", "1", 3, (FrameDefinition("world"),), (Body("tube", Shape.cylinder(m(0.01), m(0.2)), "world"),),
                      regions=(Region("tube", ("tube",)),), materials=(MaterialBinding("tube", ALU),))
    t = topology(geometry=(GeometryOwnership("arm", g.digest, ("tube",)),))
    with pytest.raises(AssemblyRefusal, match="declares cfrp"):
        t.validate_geometry({g.digest: g})
    with pytest.raises(AssemblyRefusal, match="was not supplied"):
        t.validate_geometry({})
    with pytest.raises(AssemblyRefusal, match="owned by both"):
        topology(geometry=(GeometryOwnership("arm", g.digest, ("tube",)), GeometryOwnership("hub", g.digest, ("tube",))))


# --------------------------------------------------------------------------
# F: provider health
# --------------------------------------------------------------------------

CAP = ProviderCapability("demo", "structural", "process", "demo", ("linear_elasticity",))
DIGEST = "a" * 64


def _status(**kw):
    base = dict(capability=CAP, availability=Availability.AVAILABLE, version="2.1", digest=DIGEST, location="/opt/demo")
    base.update(kw)
    return ProviderStatus(**base)


def test_installed_is_not_qualified():
    q = ProviderQualification("demo", "2.1", DIGEST, ("linear_static",), ("bench:nafems-le1",), "nafems-le-suite", "qa-team")
    assert assess_health(_status()).health is ProviderHealth.AVAILABLE
    assert assess_health(_status(), scope=("linear_static",)).health is ProviderHealth.UNQUALIFIED
    assert assess_health(_status(), qualifications=(q,), scope=("linear_static",)).health is ProviderHealth.QUALIFIED
    assert assess_health(_status(), qualifications=(q,), scope=("explicit_dynamics",)).health is ProviderHealth.UNQUALIFIED
    other_build = assess_health(_status(digest="b" * 64), qualifications=(q,), scope=("linear_static",))
    assert other_build.health is ProviderHealth.UNQUALIFIED and "does not transfer" in other_build.reason
    assert assess_health(_status(availability=Availability.UNAVAILABLE, version="", digest="", location="",
                                 reason="executable 'demo' not found")).health is ProviderHealth.NOT_INSTALLED
    broken = _status(availability=Availability.UNAVAILABLE, version="", digest="", reason="version probe of /opt/demo exited 3")
    assert assess_health(broken).health is ProviderHealth.BROKEN and not assess_health(broken).executable
    with pytest.raises(InvalidScientificProblem, match="assertion"):
        ProviderQualification("demo", "2.1", DIGEST, ("x",), (), "route", "me")
    with pytest.raises(InvalidScientificProblem, match="scope"):
        ProviderQualification("demo", "2.1", DIGEST, (), ("ref",), "route", "me")


def _script(tmp_path, name, body, mode=0o755):
    p = tmp_path / name
    p.write_text("#!/bin/sh\n" + body + "\n")
    os.chmod(p, mode)
    return str(tmp_path)


@pytest.mark.skipif(os.name != "posix", reason="probe script fixture is a POSIX shell script")
def test_probe_receipt_records_everything_and_gates_solver_identity(tmp_path):
    parse = lambda text: (__import__("re").search(r"Demo (\d+\.\d+)", text) or [None, ""])[1]  # noqa: E731
    ok = probe_executable("demo", ("--version",), parse, search_path=_script(tmp_path, "demo", 'echo "Demo 2.1"'))
    assert ok.succeeded and ok.parsed_version == "2.1" and ok.exit_code == 0 and len(ok.executable_digest) == 64
    ident = solver_identity_from_probe(ok, "demo")
    assert ident.version == "2.1" and ident.backend.endswith(ok.executable_digest)
    status = status_from_probe(CAP, ok)
    assert status.available and assess_health(status, probe=ok).probe_digest == ok.digest

    d2 = tmp_path / "b"
    d2.mkdir()
    bad = probe_executable("demo", ("--version",), parse, search_path=_script(d2, "demo", 'echo "Demo 2.1"; exit 3'))
    assert not bad.succeeded and bad.failure == "exit_code_3"
    assert assess_health(status_from_probe(CAP, bad)).health is ProviderHealth.BROKEN
    with pytest.raises(InvalidScientificProblem, match="valid probe"):
        solver_identity_from_probe(bad, "demo")
    d3 = tmp_path / "c"
    d3.mkdir()
    garbled = probe_executable("demo", (), parse, search_path=_script(d3, "demo", "echo hello"))
    assert garbled.failure == "version_unparsed" and not status_from_probe(CAP, garbled).available
    d4 = tmp_path / "d"
    d4.mkdir()
    slow = probe_executable("demo", (), parse, search_path=_script(d4, "demo", "while :; do :; done"), timeout_s=0.3)
    assert slow.timed_out and slow.failure == "timeout"
    missing = probe_executable("demo-absent", (), parse, search_path=str(tmp_path / "nowhere"))
    assert missing.failure == "not_found"
    assert assess_health(status_from_probe(CAP, missing)).health is ProviderHealth.NOT_INSTALLED
    assert stat.S_IMODE(os.stat(ok.resolved_path).st_mode) & 0o100
