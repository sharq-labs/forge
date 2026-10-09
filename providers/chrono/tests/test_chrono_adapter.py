"""Big Rock I: Project Chrono adapter -- identity, translation plan and refusal (provider-free), plus a gated reference run."""

from __future__ import annotations

import math
import sys
import types

import pytest

from engcore.providers import Availability, ProviderRefusal, ProviderStatus, assess_health
from engcore.providers.health import ProviderHealth
from engcore.scientific.units.quantity import Quantity
from engcore.spatial.geometry import Transform
from engcore.systems.assembly import AssemblyRefusal, ConnectionPoint
from engcore.systems.multibody import GravityDeclaration, MassProperties, MultibodyModel, MultibodyRequest


def m(v):
    return Quantity(v, "m")


def pendulum(length=1.0, mass=2.0, amplitude_deg=5.0):
    from forge_chrono.routes import pendulum_model

    return pendulum_model(length, mass, amplitude_deg)


def request(model, **opts):
    return MultibodyRequest(model, Quantity(2.0, "s"), Quantity(1, "ms"), ("body:bob.position_x", "body:bob.position_z"),
                            opts or {"timestepper": "euler_implicit_linearized", "solver": "sparse_qr"})


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
    assert plan["steps"] == 2000 and plan["translation_status"] == "executed_against_chrono_10_reference_route"
    assert translation_plan(request(pendulum(length=1.5)))["model_digest"] != plan["model_digest"]
    with pytest.raises(ProviderRefusal, match="never used silently"):
        translation_plan(request(pendulum(), solver="x"))
    with pytest.raises(ProviderRefusal, match="never used silently"):
        translation_plan(request(pendulum(), timestepper="hht"))  # no solver declared: Chrono's PSOR default is never used
    with pytest.raises(ProviderRefusal, match="did not hold a bilateral joint"):
        translation_plan(request(pendulum(), timestepper="hht", solver="psor"))
    with pytest.raises(ProviderRefusal, match="never dropped silently"):
        translation_plan(request(pendulum(), timestepper="hht", solver="sparse_qr", max_iterations=50))


def test_body_orientation_is_translated_as_a_unit_quaternion():
    from forge_chrono import _rotation_to_quaternion

    for axis, deg in (((0, 0, 1), 30.0), ((1, 0, 0), 179.0), ((0, 1, 0), -120.0), ((1, 1, 1), 250.0)):
        t = Transform.from_quantities(axis=axis, angle=Quantity(deg, "degree"))
        w, x, y, z = _rotation_to_quaternion(t.rotation)
        # rebuild the matrix from the quaternion and compare
        r = ((1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)),
             (2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)),
             (2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)))
        assert w >= 0 and w * w + x * x + y * y + z * z == pytest.approx(1.0)
        for i in range(3):
            assert r[i] == pytest.approx(t.rotation[i], abs=1e-12)


def test_multibody_declarations_fail_closed():
    model = pendulum()
    with pytest.raises(AssemblyRefusal, match="never estimated"):
        MultibodyModel(model.assembly, "frame", (), model.gravity)
    with pytest.raises(AssemblyRefusal, match="source reference"):
        GravityDeclaration((Quantity(0, "m/s^2"),) * 3, "")
    with pytest.raises(AssemblyRefusal, match="not a physical inertia"):
        MassProperties("bob", Quantity(1, "kg"), (m(0),) * 3, ((Quantity(1, "kg*m^2"), Quantity(0, "kg*m^2"), Quantity(0, "kg*m^2")),
                                                               (Quantity(0, "kg*m^2"), Quantity(1, "kg*m^2"), Quantity(0, "kg*m^2")),
                                                               (Quantity(0, "kg*m^2"), Quantity(0, "kg*m^2"), Quantity(3, "kg*m^2"))), "src", ("bob", "1"))
    with pytest.raises(AssemblyRefusal, match="the ground does not move"):
        MultibodyModel(model.assembly, "bob", model.mass_properties, model.gravity)
    with pytest.raises(AssemblyRefusal, match="integer number of steps"):
        MultibodyRequest(model, Quantity(1.0, "s"), Quantity(0.3, "s"), ("body:bob.position_x",))
    with pytest.raises(AssemblyRefusal, match="unknown output"):
        MultibodyRequest(model, Quantity(1.0, "s"), Quantity(0.1, "s"), ("body:frame.position_x",))


def test_joint_points_limits_and_definition_binding_fail_closed():
    import dataclasses

    from forge_chrono import translation_plan

    model = pendulum()
    asm = model.assembly
    frame_pivot = next(p for p in asm.points if p.point_id == "frame.pivot")
    moved = dataclasses.replace(asm, points=(frame_pivot, ConnectionPoint("bob.pivot", "bob", Transform.from_quantities((m(0), m(0), m(0.5))))))
    with pytest.raises(AssemblyRefusal, match="never at one of them"):
        MultibodyModel(moved, "frame", model.mass_properties, model.gravity)
    limited = dataclasses.replace(asm, joints=(dataclasses.replace(asm.joints[0], lower=Quantity(-1, "rad"), upper=Quantity(1, "rad")),))
    with pytest.raises(ProviderRefusal, match="limits"):
        translation_plan(request(MultibodyModel(limited, "frame", model.mass_properties, model.gravity)))
    wrong = dataclasses.replace(model.mass_properties[0], definition=("bob", "2"))
    with pytest.raises(AssemblyRefusal, match="brings its own mass properties"):
        MultibodyModel(asm, "frame", (wrong,), model.gravity)


def test_a_same_named_package_is_not_project_chrono(monkeypatch):
    import forge_chrono.descriptor as d

    impostor = types.ModuleType("pychrono")
    impostor.Timer = object  # the PyPI 'pychrono' timing library exposes timing helpers, not ChSystemNSC
    assert "not Project Chrono" in d.identity_problem(impostor, "1.1.0")
    monkeypatch.setitem(sys.modules, "pychrono", impostor)
    monkeypatch.setattr(d, "conda_record", lambda prefix=None: None)  # a pip install: no conda record
    monkeypatch.setattr(d, "python_package_probe", lambda *a, **k: (lambda: ProviderStatus(
        d.CAPABILITY, Availability.AVAILABLE, "1.1.0", "e" * 64, "/site-packages/pychrono")))
    status = d.probe()
    assert not status.available and status.found_but_refused
    assert assess_health(status).health is ProviderHealth.BROKEN
    real_like = types.SimpleNamespace(**{s: object for s in d.IDENTITY_SYMBOLS})
    assert "outside the supported API major version" in d.identity_problem(real_like, "9.0.1")
    assert d.identity_problem(real_like, "10.0.0") == ""


def test_conda_identity_binds_the_package_record_and_refuses_a_shadowing_module(tmp_path, monkeypatch):
    import importlib.machinery
    import json

    import forge_chrono.descriptor as d

    prefix = tmp_path / "env"
    (prefix / "conda-meta").mkdir(parents=True)
    pkg = prefix / "lib" / "pychrono"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    rec = {"name": "pychrono", "version": "10.0.0", "build": "b0", "sha256": "f" * 64, "files": ["lib/pychrono/__init__.py"]}
    (prefix / "conda-meta" / "pychrono-10.0.0-b0.json").write_text(json.dumps(rec))
    (prefix / "conda-meta" / "chrono-10.0.0-b0.json").write_text(json.dumps({"name": "chrono", "version": "10.0.0", "build": "b0", "sha256": "a" * 64}))
    real_like = types.ModuleType("pychrono")
    for s in d.IDENTITY_SYMBOLS:
        setattr(real_like, s, object)
    monkeypatch.setitem(sys.modules, "pychrono", real_like)
    spec = importlib.machinery.ModuleSpec("pychrono", None, origin=str(pkg / "__init__.py"))
    monkeypatch.setattr(d.importlib.util, "find_spec", lambda name: spec)
    status = d._conda_probe(d.conda_record(str(prefix)), str(prefix))
    assert status.available and status.version == "10.0.0" and status.dependencies[0][0] == d.CONDA_ENVIRONMENT
    # a different chrono (shared library) package changes the identity even with the same pychrono record
    (prefix / "conda-meta" / "chrono-10.0.0-b0.json").write_text(json.dumps({"name": "chrono", "version": "10.0.0", "build": "b1", "sha256": "b" * 64}))
    assert d._conda_probe(d.conda_record(str(prefix)), str(prefix)).digest != status.digest
    # a module imported from outside the record's files is not the recorded package
    elsewhere = tmp_path / "checkout" / "pychrono"
    elsewhere.mkdir(parents=True)
    (elsewhere / "__init__.py").write_text("")
    monkeypatch.setattr(d.importlib.util, "find_spec", lambda name: importlib.machinery.ModuleSpec("pychrono", None, origin=str(elsewhere / "__init__.py")))
    shadow = d._conda_probe(d.conda_record(str(prefix)), str(prefix))
    assert not shadow.available and shadow.found_but_refused and "is not a file of the conda package" in shadow.reason


def test_execution_rediscovers_and_refuses_a_changed_identity(monkeypatch):
    import forge_chrono.descriptor as d
    from forge_chrono import ChronoProvider

    discovered = ProviderStatus(d.CAPABILITY, Availability.AVAILABLE, "10.0.0", "1" * 64, "/nowhere")
    monkeypatch.setattr(d, "probe", lambda: ProviderStatus(d.CAPABILITY, Availability.AVAILABLE, "10.0.0", "2" * 64, "/nowhere"))
    with pytest.raises(ProviderRefusal, match="changed since discovery"):
        ChronoProvider(discovered).execute(request(pendulum()))
    monkeypatch.setattr(d, "probe", lambda: ProviderStatus(d.CAPABILITY, Availability.UNAVAILABLE, reason="python module 'pychrono' is not installed"))
    with pytest.raises(ProviderRefusal, match="changed since discovery"):
        ChronoProvider(discovered).execute(request(pendulum()))


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
@pytest.mark.parametrize("timestepper", ["euler_implicit_linearized", "hht"])
def test_pendulum_period_matches_the_analytic_reference(timestepper):  # pragma: no cover - needs Project Chrono
    """The adapter's declared reference ROUTE on the discovered build: a check of the translation, not validation.

    Also checks the revolute joint's length drift to 1e-6 m, which the route's period alone would not see."""
    import numpy as np

    from forge_chrono import ChronoProvider
    from forge_chrono.routes import pendulum_request, run_pendulum_route
    from engcore.providers.qualification import RouteOutcome

    status = _chrono_status()
    run = run_pendulum_route(status, timestepper)
    assert run.outcome is RouteOutcome.PASSED, run.to_dict()
    assert run.provider_version == status.version and run.provider_digest == status.digest
    rec = ChronoProvider(status).execute(pendulum_request(timestepper))
    x = np.array(rec.series_for("body:bob.position_x").values)
    z = np.array(rec.series_for("body:bob.position_z").values)
    assert float(np.max(np.abs(np.hypot(x, z) - 1.0))) < 1e-6
