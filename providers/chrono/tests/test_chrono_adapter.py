"""Big Rock I: Project Chrono adapter -- identity, translation plan and refusal (provider-free), plus a gated reference run."""

from __future__ import annotations

import math
import sys
import types

import pytest

from engcore.providers import Availability, ProviderRefusal, ProviderStatus, assess_health
from engcore.providers.health import ProviderHealth
from engcore.scientific.twins import TwinReference
from engcore.scientific.units.quantity import Quantity
from engcore.spatial.geometry import Transform
from engcore.systems.assembly import (
    AssemblyRefusal, AssemblyTopology, ConnectionPoint, InstanceLevel, JointDeclaration, JointKind, Placement,
)
from engcore.systems.multibody import GravityDeclaration, MassProperties, MultibodyModel, MultibodyRequest
from engcore.systems.topology import ComponentDefinition, ComponentInstance, SystemDefinition


def m(v):
    return Quantity(v, "m")


def pendulum(length=1.0, mass=2.0, amplitude_deg=5.0):
    a = math.radians(amplitude_deg)
    sx, cz = length * math.sin(a), length * math.cos(a)
    sysdef = SystemDefinition("pendulum", "1", (ComponentDefinition("frame", "1"), ComponentDefinition("bob", "1"), ComponentDefinition("rig", "1")), (
        ComponentInstance("rig", "rig", "1", TwinReference("rig", "1")),
        ComponentInstance("frame", "frame", "1", TwinReference("frame", "1"), parent_id="rig"),
        ComponentInstance("bob", "bob", "1", TwinReference("bob", "1"), parent_id="rig")))
    asm = AssemblyTopology(
        sysdef, (InstanceLevel("rig", "system"), InstanceLevel("frame", "component"), InstanceLevel("bob", "component")),
        placements=(Placement("frame", Transform()), Placement("bob", Transform.from_quantities((m(sx), m(0), m(-cz))))),
        points=(ConnectionPoint("frame.pivot", "frame"), ConnectionPoint("bob.pivot", "bob", Transform.from_quantities((m(-sx), m(0), m(cz))))),
        joints=(JointDeclaration("hinge", JointKind.REVOLUTE, "frame.pivot", "bob.pivot", axis=(0, 1, 0)),))
    small = Quantity(1e-6, "kg*m^2")
    mp = MassProperties("bob", Quantity(mass, "kg"), (m(0), m(0), m(0)), ((small, Quantity(0, "kg*m^2"), Quantity(0, "kg*m^2")),
                                                                         (Quantity(0, "kg*m^2"), small, Quantity(0, "kg*m^2")),
                                                                         (Quantity(0, "kg*m^2"), Quantity(0, "kg*m^2"), small)), "fixture:point-mass")
    g = GravityDeclaration((Quantity(0, "m/s^2"), Quantity(0, "m/s^2"), Quantity(-9.81, "m/s^2")), "scenario:lab-gravity")
    return MultibodyModel(asm, "frame", (mp,), g)


def request(model, **opts):
    return MultibodyRequest(model, Quantity(2.0, "s"), Quantity(1, "ms"), ("body:bob.position_x", "body:bob.position_z"),
                            opts or {"timestepper": "euler_implicit_linearized"})


def test_translation_plan_is_canonical_and_bound_to_the_model():
    from forge_chrono import translation_plan

    plan = translation_plan(request(pendulum()))
    assert plan == translation_plan(request(pendulum()))
    bob = next(b for b in plan["bodies"] if b["instance_id"] == "bob")
    assert bob["position_m"] == pytest.approx([math.sin(math.radians(5)), 0.0, -math.cos(math.radians(5))]) and bob["mass_kg"] == 2.0 and not bob["fixed"]
    hinge = plan["joints"][0]
    w, x, y, z = hinge["frame_quaternion"]
    # +z rotated onto +y: a rotation of -90 deg about x
    assert (w, x, y, z) == pytest.approx((math.sqrt(0.5), -math.sqrt(0.5), 0, 0))
    assert plan["steps"] == 2000 and plan["translation_status"] == "unverified_against_running_provider"
    assert translation_plan(request(pendulum(length=1.5)))["model_digest"] != plan["model_digest"]
    with pytest.raises(ProviderRefusal, match="never used silently"):
        translation_plan(request(pendulum(), solver="x"))


def test_multibody_declarations_fail_closed():
    model = pendulum()
    with pytest.raises(AssemblyRefusal, match="never estimated"):
        MultibodyModel(model.assembly, "frame", (), model.gravity)
    with pytest.raises(AssemblyRefusal, match="source reference"):
        GravityDeclaration((Quantity(0, "m/s^2"),) * 3, "")
    with pytest.raises(AssemblyRefusal, match="not a physical inertia"):
        MassProperties("bob", Quantity(1, "kg"), (m(0),) * 3, ((Quantity(1, "kg*m^2"), Quantity(0, "kg*m^2"), Quantity(0, "kg*m^2")),
                                                               (Quantity(0, "kg*m^2"), Quantity(1, "kg*m^2"), Quantity(0, "kg*m^2")),
                                                               (Quantity(0, "kg*m^2"), Quantity(0, "kg*m^2"), Quantity(3, "kg*m^2"))), "src")
    with pytest.raises(AssemblyRefusal, match="the ground does not move"):
        MultibodyModel(model.assembly, "bob", model.mass_properties, model.gravity)
    with pytest.raises(AssemblyRefusal, match="integer number of steps"):
        MultibodyRequest(model, Quantity(1.0, "s"), Quantity(0.3, "s"), ("body:bob.position_x",))
    with pytest.raises(AssemblyRefusal, match="unknown output"):
        MultibodyRequest(model, Quantity(1.0, "s"), Quantity(0.1, "s"), ("body:frame.position_x",))


def test_a_same_named_package_is_not_project_chrono(monkeypatch):
    import forge_chrono.descriptor as d

    impostor = types.ModuleType("pychrono")
    impostor.Timer = object  # the PyPI 'pychrono' timing library exposes timing helpers, not ChSystemNSC
    assert "not Project Chrono" in d.identity_problem(impostor)
    monkeypatch.setitem(sys.modules, "pychrono", impostor)
    monkeypatch.setattr(d, "python_package_probe", lambda *a, **k: (lambda: ProviderStatus(
        d.CAPABILITY, Availability.AVAILABLE, "1.1.0", "e" * 64, "/site-packages/pychrono")))
    status = d.probe()
    assert not status.available and status.found_but_refused
    assert assess_health(status).health is ProviderHealth.BROKEN
    real_like = types.SimpleNamespace(**{s: object for s in d.IDENTITY_SYMBOLS})
    real_like.GetChronoVersion = lambda: "8.0.0"
    assert "outside the supported API major version" in d.identity_problem(real_like)


def test_unavailable_chrono_refuses_rather_than_synthesizing():
    from forge_chrono import ChronoProvider
    from forge_chrono.descriptor import CAPABILITY

    provider = ChronoProvider(ProviderStatus(CAPABILITY, Availability.UNAVAILABLE, reason="python module 'pychrono' is not installed"))
    with pytest.raises(ProviderRefusal, match="no trajectory is synthesized"):
        provider.execute(request(pendulum()))


def _chrono_status():
    from engcore.providers import ProviderRegistry

    import forge_chrono.descriptor as d

    reg = ProviderRegistry()
    d.register(reg)
    return reg.status("chrono")


@pytest.mark.skipif(not _chrono_status().available, reason="Project Chrono unavailable")
def test_pendulum_small_amplitude_period_matches_the_analytic_reference():  # pragma: no cover - needs Project Chrono
    """Qualification route for this adapter: a declared analytic reference, not a validation of any product."""
    import numpy as np

    from forge_chrono import ChronoProvider, reference_pendulum_period

    rec = ChronoProvider(_chrono_status()).execute(request(pendulum(length=1.0)))
    assert rec.succeeded, rec.reason
    x = np.array(rec.series_for("body:bob.position_x").values)
    t = np.array(rec.series_for("body:bob.position_x").times_s)
    crossings = t[1:][np.diff(np.sign(x)) != 0]
    period = 2 * float(np.mean(np.diff(crossings)))
    assert period == pytest.approx(reference_pendulum_period(m(1.0), Quantity(9.81, "m/s^2")).magnitude, rel=0.02)
